"""Singing Voice Synthesis (SVS) wrapper module.

Wraps DiffSinger for phoneme-level singing synthesis with F0 conditioning and
speaker embeddings.  Provides graceful fallback when DiffSinger is unavailable.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SVS_SR = 44100          # DiffSinger output sample rate
_F0_FRAME_RATE = 100     # F0 frames per second (10 ms hop)
_MIN_PHONEME_DUR_S = 0.05  # minimum duration per phoneme in seconds

# Energy scale factors by section type (relative to verse = 1.0)
_SECTION_ENERGY: dict[str, float] = {
    "intro": 0.7,
    "verse": 1.0,
    "pre-chorus": 1.15,
    "chorus": 1.35,
    "bridge": 0.9,
    "outro": 0.75,
}

# Simple phoneme duration heuristics (seconds per phoneme at 120 BPM)
_BASE_PHONEME_DUR_S = 0.12  # ~5 phonemes per beat at 120 BPM


class SingingVoiceSynthesizer:
    """Synthesise singing audio using DiffSinger.

    Parameters
    ----------
    model_path:
        Path to the DiffSinger checkpoint directory (or HuggingFace repo).
    device:
        ``'cuda'`` or ``'cpu'``.
    """

    def __init__(self, model_path: str, device: str = "cuda") -> None:
        self.model_path = model_path
        self.device = device
        self._model = None
        self._model_available = False

        self._load_model()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Attempt to load the DiffSinger model; set flag if unavailable."""
        try:
            from models.diffsinger.model import DiffSinger  # type: ignore[import]

            logger.info("Loading DiffSinger checkpoint from %s", self.model_path)
            self._model = DiffSinger.load_from_checkpoint(
                self.model_path, map_location=self.device
            )
            self._model.eval()
            self._model.to(self.device)
            self._model_available = True
            logger.info("DiffSinger loaded successfully")
        except ImportError:
            logger.warning(
                "DiffSinger (models.diffsinger.model) is not available. "
                "Synthesis will return placeholder audio."
            )
        except FileNotFoundError:
            logger.warning(
                "DiffSinger checkpoint not found at '%s'. "
                "Synthesis will return placeholder audio.",
                self.model_path,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to load DiffSinger (%s). "
                "Synthesis will return placeholder audio.",
                exc,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def synthesize(
        self,
        lyrics: str,
        f0_contour: np.ndarray,
        speaker_embedding: np.ndarray,
        duration: float,
        bpm: float,
    ) -> np.ndarray:
        """Synthesise singing audio for the given lyrics and F0 contour.

        Parameters
        ----------
        lyrics:
            Plain text lyrics for the section (no markers).
        f0_contour:
            Fundamental frequency contour in Hz, shape ``(T,)`` at
            :data:`_F0_FRAME_RATE` frames/second.  Unvoiced frames should be
            ``0`` or ``NaN``.
        speaker_embedding:
            Speaker identity embedding (float32 vector), extracted upstream
            from the user's reference vocal recording.
        duration:
            Target audio duration in seconds.
        bpm:
            Beats per minute (used for phoneme alignment).

        Returns
        -------
        np.ndarray
            Mono waveform at :data:`_SVS_SR` Hz, dtype ``float32``.
        """
        phonemes = self._text_to_phonemes(lyrics)
        if not phonemes:
            return self._placeholder_audio(duration)

        # Derive per-phoneme durations scaled by BPM
        duration_per_phoneme = self._estimate_phoneme_durations(
            phonemes, duration, bpm
        )

        # Align phonemes to F0 contour frames
        target_frames = int(duration * _F0_FRAME_RATE)
        f0_resampled = self._resample_f0(f0_contour, float(_F0_FRAME_RATE), target_frames)

        aligned_phonemes, aligned_f0 = self._align_phonemes_to_f0(
            phonemes, f0_resampled, duration_per_phoneme
        )

        if not self._model_available:
            logger.debug("DiffSinger not available; returning placeholder audio.")
            return self._placeholder_audio(duration)

        return self._run_diffsinger(
            aligned_phonemes, aligned_f0, speaker_embedding, duration
        )

    def synthesize_section(
        self,
        section_lyrics: str,
        section_f0: np.ndarray,
        speaker_embedding: np.ndarray,
        bpm: float,
        section_type: str,
    ) -> np.ndarray:
        """Synthesise a single song section with section-appropriate dynamics.

        Parameters
        ----------
        section_lyrics:
            Lyrics text for this section.
        section_f0:
            F0 contour for this section.
        speaker_embedding:
            Speaker identity vector.
        bpm:
            Tempo.
        section_type:
            Section identifier (e.g. ``'chorus'``).

        Returns
        -------
        np.ndarray
            Mono waveform at :data:`_SVS_SR` Hz.
        """
        # Estimate duration from F0 length
        duration = len(section_f0) / _F0_FRAME_RATE

        audio = self.synthesize(
            lyrics=section_lyrics,
            f0_contour=section_f0,
            speaker_embedding=speaker_embedding,
            duration=duration,
            bpm=bpm,
        )

        # Apply section energy scaling
        energy = _SECTION_ENERGY.get(section_type.lower(), 1.0)
        audio = audio * energy

        # Soft clip to prevent clipping after gain
        audio = np.tanh(audio)

        return audio.astype(np.float32)

    def synthesize_full_song(
        self,
        structure: list,
        speaker_embedding: np.ndarray,
        bpm: float,
    ) -> np.ndarray:
        """Synthesise all sections and concatenate them.

        Parameters
        ----------
        structure:
            List of :class:`~core.generation.structure.SongSection` objects
            with ``section_type``, ``lyrics``, and ``f0_contour`` attributes.
        speaker_embedding:
            Speaker identity vector.
        bpm:
            Tempo.

        Returns
        -------
        np.ndarray
            Full mono waveform at :data:`_SVS_SR` Hz.
        """
        if not structure:
            raise ValueError("Structure list must not be empty.")

        segments: list[np.ndarray] = []

        for i, section in enumerate(structure):
            sec_type = getattr(section, "section_type", "verse")
            lyrics = getattr(section, "lyrics", "")
            f0 = getattr(section, "f0_contour", None)

            if f0 is None:
                # Derive a flat F0 placeholder from section duration
                start = getattr(section, "start_time", 0.0)
                end = getattr(section, "end_time", start + 30.0)
                dur = max(end - start, 1.0)
                n_frames = int(dur * _F0_FRAME_RATE)
                f0 = np.zeros(n_frames, dtype=np.float32)

            logger.info(
                "Synthesising section %d/%d: '%s'", i + 1, len(structure), sec_type
            )

            seg = self.synthesize_section(
                section_lyrics=lyrics,
                section_f0=f0,
                speaker_embedding=speaker_embedding,
                bpm=bpm,
                section_type=sec_type,
            )
            segments.append(seg)

        return np.concatenate(segments).astype(np.float32)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _text_to_phonemes(self, text: str) -> list[str]:
        """Convert text to a phoneme list using phonemizer (espeak backend).

        Parameters
        ----------
        text:
            Input text string.

        Returns
        -------
        list[str]
            List of IPA phoneme tokens.  Falls back to character-level
            decomposition if phonemizer is unavailable.
        """
        if not text or not text.strip():
            return []

        try:
            from phonemizer import phonemize  # type: ignore[import]
            from phonemizer.backend import EspeakBackend  # type: ignore[import]

            phoneme_str: str = phonemize(
                text,
                backend="espeak",
                language="en-us",
                with_stress=True,
                njobs=1,
            )
            # Split on whitespace and filter empty tokens
            phonemes = [p for p in phoneme_str.split() if p.strip()]
            return phonemes

        except ImportError:
            logger.warning(
                "phonemizer not available; falling back to character-level G2P."
            )
            return self._char_level_g2p(text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Phonemizer failed (%s); using character fallback.", exc)
            return self._char_level_g2p(text)

    def _char_level_g2p(self, text: str) -> list[str]:
        """Naive character-level grapheme-to-phoneme fallback."""
        # Keep only alphabetic characters and spaces; split into characters
        import re

        cleaned = re.sub(r"[^a-zA-Z\s]", "", text).lower().strip()
        phonemes = [ch for ch in cleaned if ch != " "]
        return phonemes if phonemes else ["sp"]  # "sp" = silence phoneme

    def _estimate_phoneme_durations(
        self,
        phonemes: list[str],
        total_duration: float,
        bpm: float,
    ) -> list[float]:
        """Distribute total duration uniformly across phonemes, scaled by BPM.

        Parameters
        ----------
        phonemes:
            Phoneme list.
        total_duration:
            Total section duration in seconds.
        bpm:
            Tempo (affects default phoneme speed).

        Returns
        -------
        list[float]
            Duration (seconds) for each phoneme.
        """
        if not phonemes:
            return []

        # Equal split, then enforce a minimum duration per phoneme
        equal_dur = total_duration / len(phonemes)
        base = max(equal_dur, _MIN_PHONEME_DUR_S * (120.0 / max(bpm, 1.0)))

        # Normalise so the sum equals total_duration
        raw = [base] * len(phonemes)
        raw_sum = sum(raw)
        scale = total_duration / raw_sum
        return [d * scale for d in raw]

    def _align_phonemes_to_f0(
        self,
        phonemes: list[str],
        f0: np.ndarray,
        duration_per_phoneme: list[float],
    ) -> tuple[list[str], np.ndarray]:
        """Align a phoneme sequence to an F0 contour by frame assignment.

        Each phoneme is assigned a range of F0 frames proportional to its
        duration.  The returned F0 array has the same length as *f0* but with
        values smoothed per-phoneme segment.

        Parameters
        ----------
        phonemes:
            Ordered list of phoneme strings.
        f0:
            F0 contour, shape ``(T,)``.
        duration_per_phoneme:
            Duration in seconds for each phoneme (len == len(phonemes)).

        Returns
        -------
        tuple[list[str], np.ndarray]
            ``(aligned_phonemes, aligned_f0)`` where *aligned_phonemes* maps
            each F0 frame to its phoneme label and *aligned_f0* is the (T,)
            F0 array (possibly smoothed).
        """
        total_frames = len(f0)
        aligned_phonemes: list[str] = ["sp"] * total_frames
        aligned_f0 = f0.copy()

        if not phonemes or total_frames == 0:
            return aligned_phonemes, aligned_f0

        total_dur = sum(duration_per_phoneme)
        frame_cursor = 0

        for ph, dur in zip(phonemes, duration_per_phoneme):
            n_frames = max(1, int(round(dur / total_dur * total_frames)))
            end_frame = min(frame_cursor + n_frames, total_frames)

            for fi in range(frame_cursor, end_frame):
                aligned_phonemes[fi] = ph

            # Smooth F0 within this phoneme segment (replace zeros with mean)
            segment = aligned_f0[frame_cursor:end_frame]
            voiced = segment[segment > 0]
            if len(voiced) > 0:
                mean_f0 = voiced.mean()
                # Fill unvoiced frames with the segment mean for smoother synthesis
                segment_smooth = np.where(segment == 0, 0.0, segment)
                aligned_f0[frame_cursor:end_frame] = segment_smooth

            frame_cursor = end_frame
            if frame_cursor >= total_frames:
                break

        return aligned_phonemes, aligned_f0

    def _resample_f0(
        self,
        f0: np.ndarray,
        source_sr: float,
        target_frames: int,
    ) -> np.ndarray:
        """Resample an F0 contour to a target number of frames.

        Uses linear interpolation for smooth resampling.

        Parameters
        ----------
        f0:
            Source F0 contour, shape ``(T,)``.
        source_sr:
            Frame rate of the source (frames per second).  Unused in the
            interpolation math but kept for API clarity.
        target_frames:
            Desired output frame count.

        Returns
        -------
        np.ndarray
            Resampled F0 contour, shape ``(target_frames,)``.
        """
        if len(f0) == 0:
            return np.zeros(target_frames, dtype=np.float32)

        if len(f0) == target_frames:
            return f0.astype(np.float32)

        source_indices = np.linspace(0, len(f0) - 1, num=target_frames)
        resampled = np.interp(source_indices, np.arange(len(f0)), f0)
        return resampled.astype(np.float32)

    def _run_diffsinger(
        self,
        phonemes: list[str],
        f0: np.ndarray,
        speaker_embedding: np.ndarray,
        duration: float,
    ) -> np.ndarray:
        """Forward pass through DiffSinger model.

        Parameters
        ----------
        phonemes:
            Frame-aligned phoneme list (length == len(f0)).
        f0:
            Resampled F0 contour, shape ``(T,)``.
        speaker_embedding:
            Speaker identity vector.
        duration:
            Target audio duration (used to trim/pad the output).

        Returns
        -------
        np.ndarray
            Mono waveform at :data:`_SVS_SR` Hz.
        """
        import torch  # type: ignore[import]

        # Build a unique phoneme vocabulary from the aligned sequence
        vocab: dict[str, int] = {"sp": 0, "AP": 1}  # silence / aspiration
        for ph in set(phonemes):
            if ph not in vocab:
                vocab[ph] = len(vocab)

        phoneme_ids = torch.tensor(
            [vocab.get(ph, 0) for ph in phonemes], dtype=torch.long
        ).unsqueeze(0).to(self.device)  # (1, T)

        f0_tensor = torch.from_numpy(f0).unsqueeze(0).to(self.device)  # (1, T)

        spk_tensor = torch.from_numpy(speaker_embedding.astype(np.float32))
        spk_tensor = spk_tensor.unsqueeze(0).to(self.device)  # (1, D)

        with torch.no_grad():
            waveform = self._model.synthesize(
                phoneme_ids=phoneme_ids,
                f0=f0_tensor,
                speaker_embedding=spk_tensor,
            )

        # Convert to numpy mono
        if isinstance(waveform, torch.Tensor):
            waveform = waveform.squeeze().cpu().numpy()

        waveform = waveform.astype(np.float32)

        # Trim or zero-pad to exact duration
        target_samples = int(duration * _SVS_SR)
        if len(waveform) > target_samples:
            waveform = waveform[:target_samples]
        elif len(waveform) < target_samples:
            waveform = np.pad(waveform, (0, target_samples - len(waveform)))

        return waveform

    def _placeholder_audio(self, duration: float) -> np.ndarray:
        """Return silent placeholder audio of the given duration.

        Used when DiffSinger is not available so the rest of the pipeline can
        continue running without crashing.

        Parameters
        ----------
        duration:
            Desired audio length in seconds.

        Returns
        -------
        np.ndarray
            Zero-valued mono waveform at :data:`_SVS_SR` Hz.
        """
        n_samples = max(1, int(duration * _SVS_SR))
        logger.debug("Returning %.2f s of placeholder (silent) audio.", duration)
        return np.zeros(n_samples, dtype=np.float32)
