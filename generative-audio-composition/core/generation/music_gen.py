"""MusicGen instrumental generation module.

Wraps Facebook's MusicGen (via the ``audiocraft`` library) with helpers for
section-by-section generation, melody conditioning, and cross-fading.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SR = 32000  # MusicGen native sample rate
_MAX_SINGLE_GENERATION_SECONDS = 30  # audiocraft hard limit per call
_CROSSFADE_DURATION_S = 0.5  # default cross-fade between sections

# Text prompt templates keyed by section type
_SECTION_PROMPTS: dict[str, str] = {
    "intro": (
        "{genre} instrumental intro, {key}, {bpm} BPM, atmospheric, building tension, "
        "clean production"
    ),
    "verse": (
        "{genre} instrumental verse, {key}, {bpm} BPM, {mood}melodic, moderate energy, "
        "clear rhythm section"
    ),
    "pre-chorus": (
        "{genre} instrumental pre-chorus, {key}, {bpm} BPM, building energy, rising tension"
    ),
    "chorus": (
        "{genre} instrumental chorus, {key}, {bpm} BPM, {mood}high energy, full arrangement, "
        "catchy hook, powerful"
    ),
    "bridge": (
        "{genre} instrumental bridge, {key}, {bpm} BPM, contrasting section, "
        "emotional shift, stripped back"
    ),
    "outro": (
        "{genre} instrumental outro, {key}, {bpm} BPM, fading energy, "
        "resolution, calm, concluding"
    ),
}


class InstrumentalGenerator:
    """Generate instrumental tracks using Facebook's MusicGen model.

    Parameters
    ----------
    model_path:
        HuggingFace model ID or local path. Defaults to
        ``'facebook/musicgen-large'``.
    device:
        ``'cuda'`` or ``'cpu'``.
    """

    def __init__(
        self,
        model_path: str = "facebook/musicgen-large",
        device: str = "cuda",
    ) -> None:
        self.model_path = model_path
        self.device = device
        self._model = None
        self._load_model()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Load the MusicGen model from audiocraft."""
        try:
            from audiocraft.models import MusicGen  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'audiocraft' package is required. "
                "Install it with: pip install audiocraft"
            ) from exc

        logger.info("Loading MusicGen model: %s", self.model_path)
        self._model = MusicGen.get_pretrained(self.model_path)
        self._model.to(self.device)
        logger.info("MusicGen model loaded on device: %s", self.device)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        description: str,
        duration: float,
        key: str,
        bpm: float,
        melody_audio: Optional[np.ndarray] = None,
        sr: int = _DEFAULT_SR,
    ) -> np.ndarray:
        """Generate an instrumental track.

        Parameters
        ----------
        description:
            Free-text prompt describing the desired sound.
        duration:
            Target duration in seconds.
        key:
            Musical key, e.g. ``'C major'`` or ``'A minor'``.
        bpm:
            Beats per minute.
        melody_audio:
            Optional mono waveform (float32, shape ``(N,)``) at *sr* Hz to use
            as melody conditioning.  When provided, the model uses MusicGen's
            melody-conditioning mode.
        sr:
            Sample rate of *melody_audio* (ignored when *melody_audio* is
            ``None``).

        Returns
        -------
        np.ndarray
            Mono audio waveform at :data:`_DEFAULT_SR` Hz, dtype ``float32``.
        """
        if self._model is None:
            raise RuntimeError("Model not loaded.")

        if duration <= _MAX_SINGLE_GENERATION_SECONDS:
            return self._generate_chunk(description, duration, melody_audio, sr)

        # Long-form: generate in overlapping segments
        return self._generate_long_form(description, duration, melody_audio, sr)

    def generate_section(
        self,
        section_type: str,
        duration: float,
        key: str,
        bpm: float,
        prev_audio: Optional[np.ndarray] = None,
        genre: str = "pop",
        mood: str = "",
    ) -> np.ndarray:
        """Generate a single song section with continuity awareness.

        Parameters
        ----------
        section_type:
            One of ``'intro'``, ``'verse'``, ``'pre-chorus'``, ``'chorus'``,
            ``'bridge'``, ``'outro'``.
        duration:
            Section duration in seconds.
        key:
            Musical key string.
        bpm:
            Beats per minute.
        prev_audio:
            Optional tail of the previously generated section used for context
            (currently passed as melody conditioning if short enough).
        genre:
            Musical genre string for prompt construction.
        mood:
            Optional mood adjective appended to the prompt (e.g. ``'dark '``).

        Returns
        -------
        np.ndarray
            Mono waveform at :data:`_DEFAULT_SR` Hz.
        """
        prompt = self._build_prompt(section_type, key, bpm, genre, mood)
        logger.debug("Section '%s' prompt: %s", section_type, prompt)

        # Use a short tail of the previous section as melody conditioning
        melody_input: Optional[np.ndarray] = None
        if prev_audio is not None:
            tail_samples = int(min(10, duration * 0.3) * _DEFAULT_SR)
            melody_input = prev_audio[-tail_samples:]

        return self.generate(
            description=prompt,
            duration=duration,
            key=key,
            bpm=bpm,
            melody_audio=melody_input,
            sr=_DEFAULT_SR,
        )

    def generate_full_arrangement(
        self,
        structure: list,
        key: str,
        bpm: float,
        melody_audio: np.ndarray,
        genre: str,
    ) -> np.ndarray:
        """Generate a full track section by section with smooth cross-fades.

        Parameters
        ----------
        structure:
            List of :class:`~core.generation.structure.SongSection` objects (or
            any objects with ``.section_type`` and a duration derivable from
            ``.start_time`` / ``.end_time`` attributes).
        key:
            Musical key.
        bpm:
            Tempo in beats per minute.
        melody_audio:
            Reference melody from the user's humming (mono float32 at 32 kHz).
        genre:
            Genre string used in text prompts.

        Returns
        -------
        np.ndarray
            Full arrangement as a mono waveform at :data:`_DEFAULT_SR` Hz.
        """
        if not structure:
            raise ValueError("Structure list must not be empty.")

        segments: list[np.ndarray] = []
        prev_audio: Optional[np.ndarray] = None

        for i, section in enumerate(structure):
            sec_type = getattr(section, "section_type", str(section))
            duration = getattr(section, "end_time", 30.0) - getattr(
                section, "start_time", 0.0
            )
            if duration <= 0:
                duration = 30.0

            logger.info(
                "Generating section %d/%d: '%s' (%.1f s)",
                i + 1,
                len(structure),
                sec_type,
                duration,
            )

            # Use user's melody for the first non-intro section only
            melody: Optional[np.ndarray] = None
            if i == 1 and melody_audio is not None and len(melody_audio) > 0:
                melody = melody_audio

            audio = self.generate_section(
                section_type=sec_type,
                duration=duration,
                key=key,
                bpm=bpm,
                prev_audio=prev_audio,
                genre=genre,
            )

            segments.append(audio)
            prev_audio = audio

        # Cross-fade and concatenate all segments
        result = segments[0]
        for seg in segments[1:]:
            result = self._crossfade(result, seg, _CROSSFADE_DURATION_S)

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        section_type: str,
        key: str,
        bpm: float,
        genre: str,
        mood: Optional[str] = None,
    ) -> str:
        """Build a MusicGen text prompt for a given section type.

        Parameters
        ----------
        section_type:
            Section identifier (e.g. ``'chorus'``).
        key:
            Musical key string.
        bpm:
            Tempo.
        genre:
            Genre string.
        mood:
            Optional mood prefix (with trailing space if non-empty).

        Returns
        -------
        str
            Formatted text prompt.
        """
        template = _SECTION_PROMPTS.get(
            section_type.lower(),
            "{genre} instrumental, {key}, {bpm} BPM, {mood}professional production",
        )
        mood_str = f"{mood} " if mood else ""
        return template.format(
            genre=genre,
            key=key,
            bpm=int(bpm),
            mood=mood_str,
        )

    def _generate_chunk(
        self,
        description: str,
        duration: float,
        melody_audio: Optional[np.ndarray],
        sr: int,
    ) -> np.ndarray:
        """Generate a single chunk (up to 30 s) via audiocraft."""
        import torch  # type: ignore[import]

        self._model.set_generation_params(duration=duration)

        if melody_audio is not None:
            # Melody conditioning: reshape to (batch, channels, samples)
            melody_tensor = torch.from_numpy(melody_audio).float()
            if melody_tensor.ndim == 1:
                melody_tensor = melody_tensor.unsqueeze(0).unsqueeze(0)  # (1, 1, N)
            elif melody_tensor.ndim == 2:
                melody_tensor = melody_tensor.unsqueeze(0)  # (1, C, N)

            melody_tensor = melody_tensor.to(self.device)
            output = self._model.generate_with_chroma(
                descriptions=[description],
                melody_wavs=melody_tensor,
                melody_sample_rate=sr,
            )
        else:
            output = self._model.generate(descriptions=[description])

        # output shape: (batch, channels, samples)
        audio_np = output[0].cpu().numpy()  # (channels, samples)
        if audio_np.ndim == 2:
            audio_np = audio_np.mean(axis=0)  # mix to mono

        return audio_np.astype(np.float32)

    def _generate_long_form(
        self,
        description: str,
        duration: float,
        melody_audio: Optional[np.ndarray],
        sr: int,
    ) -> np.ndarray:
        """Generate audio longer than the model's single-call limit.

        Splits the target duration into overlapping chunks, generates each
        individually, and cross-fades them together.

        Parameters
        ----------
        description:
            Text prompt.
        duration:
            Total desired duration in seconds.
        melody_audio:
            Optional melody conditioning (used only on the first chunk).
        sr:
            Sample rate of *melody_audio*.

        Returns
        -------
        np.ndarray
            Concatenated and cross-faded audio at :data:`_DEFAULT_SR` Hz.
        """
        chunk_dur = float(_MAX_SINGLE_GENERATION_SECONDS)
        overlap = _CROSSFADE_DURATION_S

        n_chunks = math.ceil(duration / (chunk_dur - overlap))
        segments: list[np.ndarray] = []

        for i in range(n_chunks):
            # Only use melody on the first chunk
            mel = melody_audio if i == 0 else None
            chunk = self._generate_chunk(description, chunk_dur, mel, sr)
            segments.append(chunk)

        # Cross-fade all chunks together
        result = segments[0]
        for seg in segments[1:]:
            result = self._crossfade(result, seg, overlap)

        # Trim to exact requested duration
        target_samples = int(duration * _DEFAULT_SR)
        if len(result) > target_samples:
            result = result[:target_samples]

        return result

    def _crossfade(
        self,
        audio1: np.ndarray,
        audio2: np.ndarray,
        fade_duration: float = _CROSSFADE_DURATION_S,
    ) -> np.ndarray:
        """Cross-fade two mono audio arrays.

        The tail of *audio1* fades out while the head of *audio2* fades in
        over *fade_duration* seconds.  The overlapping region is summed.

        Parameters
        ----------
        audio1:
            First audio segment (float32, mono).
        audio2:
            Second audio segment (float32, mono).
        fade_duration:
            Cross-fade duration in seconds.

        Returns
        -------
        np.ndarray
            Seamlessly joined audio.
        """
        fade_samples = int(fade_duration * _DEFAULT_SR)
        fade_samples = min(fade_samples, len(audio1), len(audio2))

        if fade_samples <= 0:
            return np.concatenate([audio1, audio2])

        fade_out = np.linspace(1.0, 0.0, fade_samples, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, fade_samples, dtype=np.float32)

        # Overlap region
        overlap_1 = audio1[-fade_samples:] * fade_out
        overlap_2 = audio2[:fade_samples] * fade_in
        overlap = overlap_1 + overlap_2

        return np.concatenate([
            audio1[:-fade_samples],
            overlap,
            audio2[fade_samples:],
        ])
