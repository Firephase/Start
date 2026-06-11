"""
Automatic Speech Recognition (ASR) Module
==========================================
Wraps OpenAI Whisper to provide transcription with word-level timestamps,
segment metadata, and confidence scores for vocal recordings.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WHISPER_TARGET_SR: int = 16_000   # Whisper's native sample rate
WHISPER_CHUNK_DURATION: float = 30.0  # seconds – Whisper's context window
WHISPER_CHUNK_OVERLAP: float = 2.0   # seconds – overlap between chunks

_SUPPORTED_MODEL_SIZES = {
    "tiny", "base", "small", "medium",
    "large", "large-v2", "large-v3",
}


class WhisperASR:
    """
    High-level wrapper around OpenAI Whisper for speech recognition.

    Features
    --------
    * Automatic long-audio chunking with overlap to prevent boundary artefacts.
    * Word-level timestamps via Whisper's ``word_timestamps=True`` option.
    * Confidence scores aggregated from log-probability values.
    * Language detection (or forced language decoding).

    Parameters
    ----------
    model_size : str
        Whisper model variant.  One of ``tiny``, ``base``, ``small``,
        ``medium``, ``large``, ``large-v2``, ``large-v3``.
    device : str
        PyTorch device string (``'cuda'`` / ``'cpu'`` / ``'mps'``).
    language : str or None
        ISO-639-1 language code (e.g. ``'en'``).  ``None`` enables
        automatic language detection.
    """

    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        language: Optional[str] = "en",
    ) -> None:
        if model_size not in _SUPPORTED_MODEL_SIZES:
            raise ValueError(
                f"Unknown Whisper model size '{model_size}'. "
                f"Choose from: {sorted(_SUPPORTED_MODEL_SIZES)}"
            )

        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available – falling back to CPU.")
            device = "cpu"

        self.device = device
        self.language = language
        self.model_size = model_size

        try:
            import whisper  # openai-whisper
        except ImportError as exc:
            raise ImportError(
                "openai-whisper is required for ASR. "
                "Install it with: pip install openai-whisper"
            ) from exc

        logger.info("Loading Whisper model '%s' on %s…", model_size, device)
        self._model = whisper.load_model(model_size, device=device)
        self._whisper = whisper
        logger.info("Whisper model loaded.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def transcribe(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """
        Transcribe a vocal recording.

        Long recordings (> 30 s) are split into overlapping chunks and the
        results are merged.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo waveform at sample rate *sr*.
        sr : int
            Sample rate of *audio*.

        Returns
        -------
        dict with keys:
            ``text`` : str
                Full transcription.
            ``segments`` : list[dict]
                Each segment has keys ``start``, ``end``, ``text``, ``words``.
            ``language`` : str
                Detected or forced language code.
            ``confidence`` : float
                Mean token log-probability converted to [0, 1] range.
        """
        mono_16k = self._preprocess(audio, sr)
        duration = len(mono_16k) / WHISPER_TARGET_SR

        if duration <= WHISPER_CHUNK_DURATION + WHISPER_CHUNK_OVERLAP:
            return self._transcribe_array(mono_16k)

        logger.info(
            "Audio duration %.1f s exceeds chunk window; processing in chunks.", duration
        )
        return self._transcribe_chunked(mono_16k)

    def transcribe_file(self, path: str) -> dict[str, Any]:
        """
        Load an audio file from *path* and transcribe it.

        Parameters
        ----------
        path : str
            Path to any audio format supported by torchaudio / ffmpeg.

        Returns
        -------
        dict
            Same structure as :meth:`transcribe`.
        """
        try:
            import torchaudio
        except ImportError as exc:
            raise ImportError(
                "torchaudio is required to load audio files. "
                "Install it with: pip install torchaudio"
            ) from exc

        path = str(Path(path).resolve())
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Audio file not found: {path}")

        waveform, sr = torchaudio.load(path)
        audio = waveform.mean(dim=0).numpy()   # stereo → mono
        return self.transcribe(audio, sr)

    def extract_lyrics_with_timing(
        self, audio: np.ndarray, sr: int
    ) -> list[dict[str, Any]]:
        """
        Return word-level timecodes for the entire recording.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo waveform.
        sr : int
            Sample rate of *audio*.

        Returns
        -------
        list[dict]
            Each entry has keys:
            ``word`` : str, ``start`` : float, ``end`` : float,
            ``probability`` : float.
        """
        result = self.transcribe(audio, sr)
        words: list[dict[str, Any]] = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                words.append(
                    {
                        "word": w.get("word", "").strip(),
                        "start": float(w.get("start", 0.0)),
                        "end": float(w.get("end", 0.0)),
                        "probability": float(w.get("probability", 0.0)),
                    }
                )
        return words

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _preprocess(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Resample to 16 kHz mono float32 as expected by Whisper."""
        audio = audio.astype(np.float32)

        # Collapse to mono
        if audio.ndim == 2:
            if audio.shape[0] <= 8:
                audio = audio.mean(axis=0)
            else:
                audio = audio.mean(axis=1)

        if sr != WHISPER_TARGET_SR:
            try:
                import torchaudio.transforms as T
                import torch
                tensor = torch.from_numpy(audio).unsqueeze(0)
                resampler = T.Resample(orig_freq=sr, new_freq=WHISPER_TARGET_SR)
                audio = resampler(tensor).squeeze(0).numpy()
            except ImportError:
                # Fallback: scipy
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(sr, WHISPER_TARGET_SR)
                audio = resample_poly(audio, WHISPER_TARGET_SR // g, sr // g).astype(
                    np.float32
                )

        return audio

    def _transcribe_array(self, audio_16k: np.ndarray) -> dict[str, Any]:
        """Run Whisper on a single ≤30 s float32 array at 16 kHz."""
        decode_opts: dict[str, Any] = {
            "word_timestamps": True,
            "verbose": False,
        }
        if self.language is not None:
            decode_opts["language"] = self.language

        result = self._model.transcribe(audio_16k, **decode_opts)

        segments = self._normalise_segments(result.get("segments", []))
        confidence = self._compute_confidence(result.get("segments", []))

        return {
            "text": result.get("text", "").strip(),
            "segments": segments,
            "language": result.get("language", self.language or ""),
            "confidence": confidence,
        }

    def _transcribe_chunked(self, audio_16k: np.ndarray) -> dict[str, Any]:
        """
        Split long audio into overlapping 30 s windows and merge results.

        Segments near chunk boundaries are deduplicated by comparing start
        times; the version with the higher average token probability wins.
        """
        chunk_samples = int(WHISPER_CHUNK_DURATION * WHISPER_TARGET_SR)
        overlap_samples = int(WHISPER_CHUNK_OVERLAP * WHISPER_TARGET_SR)
        step_samples = chunk_samples - overlap_samples

        all_segments: list[dict[str, Any]] = []
        offset_samples = 0
        full_text_parts: list[str] = []

        while offset_samples < len(audio_16k):
            chunk = audio_16k[offset_samples: offset_samples + chunk_samples]
            offset_sec = offset_samples / WHISPER_TARGET_SR

            chunk_result = self._transcribe_array(chunk)

            # Shift timestamps by chunk offset
            for seg in chunk_result["segments"]:
                seg = dict(seg)
                seg["start"] = round(seg["start"] + offset_sec, 3)
                seg["end"] = round(seg["end"] + offset_sec, 3)
                for w in seg.get("words", []):
                    w["start"] = round(w["start"] + offset_sec, 3)
                    w["end"] = round(w["end"] + offset_sec, 3)
                all_segments.append(seg)

            full_text_parts.append(chunk_result["text"])
            offset_samples += step_samples

            if len(chunk) < chunk_samples:
                break  # last chunk – no more data

        merged = self._merge_segments(all_segments)
        confidence = self._compute_confidence(merged)

        return {
            "text": " ".join(full_text_parts).strip(),
            "segments": merged,
            "language": self.language or "",
            "confidence": confidence,
        }

    @staticmethod
    def _normalise_segments(raw: list[dict]) -> list[dict[str, Any]]:
        """Convert Whisper's raw segment dicts to the expected schema."""
        out = []
        for seg in raw:
            words = []
            for w in seg.get("words", []):
                words.append(
                    {
                        "word": w.get("word", "").strip(),
                        "start": float(w.get("start", 0.0)),
                        "end": float(w.get("end", 0.0)),
                        "probability": float(w.get("probability", 0.0)),
                    }
                )
            out.append(
                {
                    "start": float(seg.get("start", 0.0)),
                    "end": float(seg.get("end", 0.0)),
                    "text": seg.get("text", "").strip(),
                    "words": words,
                }
            )
        return out

    @staticmethod
    def _merge_segments(segments: list[dict]) -> list[dict[str, Any]]:
        """
        Deduplicate overlapping segments produced by chunked transcription.

        Two segments are considered duplicates if their start times differ by
        less than 0.5 s.  The one with longer text is kept.
        """
        if not segments:
            return []

        segments = sorted(segments, key=lambda s: s["start"])
        merged: list[dict] = [segments[0]]

        for seg in segments[1:]:
            prev = merged[-1]
            if abs(seg["start"] - prev["start"]) < 0.5:
                # Keep the segment with more content
                if len(seg["text"]) > len(prev["text"]):
                    merged[-1] = seg
            else:
                merged.append(seg)

        return merged

    @staticmethod
    def _compute_confidence(segments: list[dict]) -> float:
        """
        Aggregate segment-level avg_logprob into a [0, 1] confidence score.

        Whisper reports ``avg_logprob`` per segment (typically in [-1, 0]).
        We map this to [0, 1] via ``exp(avg_logprob)``.
        """
        log_probs = []
        for seg in segments:
            lp = seg.get("avg_logprob")
            if lp is not None:
                log_probs.append(float(lp))
        if not log_probs:
            return 0.0
        mean_lp = float(np.mean(log_probs))
        return float(np.clip(np.exp(mean_lp), 0.0, 1.0))
