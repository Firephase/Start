"""
Pitch / F0 Extraction Module
=============================
Provides fundamental frequency (F0) extraction, melody contour analysis,
musical key detection (Krumhansl-Schmuckler), and tempo/beat tracking.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

import numpy as np
import librosa
import scipy.signal
import scipy.ndimage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------

def _import_crepe():
    try:
        import crepe
        return crepe
    except ImportError as exc:
        raise ImportError(
            "crepe is required for CREPE pitch extraction. "
            "Install it with: pip install crepe"
        ) from exc


def _import_parselmouth():
    try:
        import parselmouth
        return parselmouth
    except ImportError as exc:
        raise ImportError(
            "praat-parselmouth is required for Parselmouth pitch extraction. "
            "Install it with: pip install praat-parselmouth"
        ) from exc


# ---------------------------------------------------------------------------
# Krumhansl-Schmuckler key profiles (major and minor)
# ---------------------------------------------------------------------------

_KS_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_KS_MINOR = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


class PitchExtractor:
    """
    Fundamental frequency (F0) extraction and musical feature analysis.

    Supports two F0 estimation back-ends:

    * ``'crepe'``  – deep-learning model; highly accurate on vocals.
    * ``'parselmouth'`` – Praat's autocorrelation method; fast, no GPU needed.

    Parameters
    ----------
    method : {'crepe', 'parselmouth'}
        F0 estimation backend.
    device : str
        PyTorch device for CREPE (``'cuda'`` / ``'cpu'``).
    """

    def __init__(
        self,
        method: Literal["crepe", "parselmouth"] = "crepe",
        device: str = "cuda",
    ) -> None:
        if method not in {"crepe", "parselmouth"}:
            raise ValueError(
                f"Unknown pitch method '{method}'. Choose 'crepe' or 'parselmouth'."
            )
        self.method = method
        self.device = device

        if method == "crepe":
            try:
                import torch
                if device == "cuda" and not torch.cuda.is_available():
                    logger.warning("CUDA not available for CREPE – using CPU.")
                    self.device = "cpu"
            except ImportError:
                pass
            self._crepe = _import_crepe()
            logger.info("PitchExtractor using CREPE backend.")
        else:
            self._parselmouth = _import_parselmouth()
            logger.info("PitchExtractor using Parselmouth (Praat) backend.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_f0(
        self,
        audio: np.ndarray,
        sr: int,
        hop_length: int = 512,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Extract the fundamental frequency contour.

        Parameters
        ----------
        audio : np.ndarray
            Mono waveform (any sample rate).
        sr : int
            Sample rate of *audio*.
        hop_length : int
            Hop size in samples for frame-based methods (used with Parselmouth).

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            ``(f0_hz, voiced_flag)`` – both shape ``(n_frames,)``.
            Unvoiced frames have ``f0_hz == 0.0``.
        """
        mono = self._ensure_mono(audio)

        if self.method == "crepe":
            return self._extract_crepe(mono, sr)
        return self._extract_parselmouth(mono, sr, hop_length)

    def extract_melody_contour(
        self, audio: np.ndarray, sr: int
    ) -> dict[str, Any]:
        """
        Extract a smoothed melody contour with summary statistics.

        Returns
        -------
        dict with keys:
            ``f0`` : np.ndarray        – raw F0 array (Hz).
            ``voiced`` : np.ndarray    – boolean voiced flag array.
            ``mean_f0`` : float        – mean F0 over voiced frames (Hz).
            ``std_f0`` : float         – std-dev of voiced F0 (Hz).
            ``pitch_range`` : tuple    – ``(min_hz, max_hz)`` over voiced frames.
            ``f0_smooth`` : np.ndarray – median-filtered F0 (Hz).
        """
        f0, voiced = self.extract_f0(audio, sr)
        f0_smooth = self.smooth_f0(f0, voiced)

        voiced_f0 = f0[voiced]
        mean_f0 = float(np.mean(voiced_f0)) if voiced_f0.size else 0.0
        std_f0 = float(np.std(voiced_f0)) if voiced_f0.size else 0.0
        pitch_min = float(np.min(voiced_f0)) if voiced_f0.size else 0.0
        pitch_max = float(np.max(voiced_f0)) if voiced_f0.size else 0.0

        return {
            "f0": f0,
            "voiced": voiced,
            "mean_f0": mean_f0,
            "std_f0": std_f0,
            "pitch_range": (pitch_min, pitch_max),
            "f0_smooth": f0_smooth,
        }

    def detect_key(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """
        Estimate the musical key using Krumhansl-Schmuckler profiles.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo waveform.
        sr : int
            Sample rate.

        Returns
        -------
        dict with keys:
            ``key`` : str          – e.g. ``'G major'``.
            ``mode`` : str         – ``'major'`` or ``'minor'``.
            ``root_note`` : int    – MIDI pitch class 0–11 (C=0).
            ``confidence`` : float – Pearson correlation coefficient in [0, 1].
        """
        mono = self._ensure_mono(audio)
        chroma = librosa.feature.chroma_cqt(y=mono, sr=sr, bins_per_octave=36)
        chroma_mean = chroma.mean(axis=1)  # shape (12,)

        best_r = -np.inf
        best_root = 0
        best_mode = "major"

        for root in range(12):
            rolled_major = np.roll(_KS_MAJOR, root)
            rolled_minor = np.roll(_KS_MINOR, root)

            r_major = float(np.corrcoef(chroma_mean, rolled_major)[0, 1])
            r_minor = float(np.corrcoef(chroma_mean, rolled_minor)[0, 1])

            if r_major > best_r:
                best_r = r_major
                best_root = root
                best_mode = "major"

            if r_minor > best_r:
                best_r = r_minor
                best_root = root
                best_mode = "minor"

        key_name = f"{_NOTE_NAMES[best_root]} {best_mode}"
        confidence = float(np.clip(best_r, 0.0, 1.0))

        return {
            "key": key_name,
            "mode": best_mode,
            "root_note": best_root,
            "confidence": confidence,
        }

    def detect_tempo(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """
        Estimate tempo and beat positions.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo waveform.
        sr : int
            Sample rate.

        Returns
        -------
        dict with keys:
            ``bpm`` : float              – estimated tempo in beats per minute.
            ``beat_frames`` : np.ndarray – frame indices of detected beats.
            ``downbeats`` : np.ndarray   – estimated downbeat frame indices.
        """
        mono = self._ensure_mono(audio)
        tempo, beat_frames = librosa.beat.beat_track(
            y=mono, sr=sr, units="frames", trim=False
        )
        bpm = float(np.atleast_1d(tempo)[0])

        # Heuristic downbeats: every 4th beat starting from the first
        downbeats = beat_frames[::4] if len(beat_frames) >= 4 else beat_frames[:1]

        return {
            "bpm": round(bpm, 2),
            "beat_frames": beat_frames,
            "downbeats": downbeats,
        }

    def smooth_f0(
        self, f0: np.ndarray, voiced: np.ndarray, kernel_size: int = 11
    ) -> np.ndarray:
        """
        Smooth the F0 contour using a median filter and linear interpolation
        across unvoiced regions.

        Parameters
        ----------
        f0 : np.ndarray
            Raw F0 array (Hz). Unvoiced frames should be 0.0.
        voiced : np.ndarray
            Boolean array indicating voiced frames.
        kernel_size : int
            Median filter window size (must be odd).

        Returns
        -------
        np.ndarray
            Smoothed F0 contour (Hz). Unvoiced frames remain 0.0.
        """
        if not np.any(voiced):
            return f0.copy()

        f0_smooth = f0.copy()

        # --- Interpolate across unvoiced gaps ---
        indices = np.arange(len(f0))
        voiced_idx = indices[voiced]
        voiced_vals = f0[voiced]

        if len(voiced_idx) >= 2:
            interp_f0 = np.interp(indices, voiced_idx, voiced_vals)
        else:
            interp_f0 = f0.copy()

        # --- Median filter on interpolated contour ---
        if kernel_size % 2 == 0:
            kernel_size += 1
        filtered = scipy.signal.medfilt(interp_f0, kernel_size=kernel_size)

        # --- Restore silence in unvoiced regions ---
        f0_smooth = filtered
        f0_smooth[~voiced] = 0.0

        return f0_smooth.astype(np.float32)

    # ------------------------------------------------------------------
    # Private backends
    # ------------------------------------------------------------------

    def _extract_crepe(
        self, mono: np.ndarray, sr: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Use CREPE (deep-learning) for F0 estimation."""
        crepe = self._crepe

        # CREPE expects audio at 16 kHz
        if sr != 16_000:
            mono = librosa.resample(mono, orig_sr=sr, target_sr=16_000)
            sr = 16_000

        _, frequency, confidence, _ = crepe.predict(
            mono,
            sr,
            viterbi=True,
            center=True,
            step_size=10,         # ms
            verbose=False,
        )

        voiced = confidence >= 0.5
        f0 = frequency.copy().astype(np.float32)
        f0[~voiced] = 0.0

        return f0, voiced.astype(bool)

    def _extract_parselmouth(
        self, mono: np.ndarray, sr: int, hop_length: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """Use Praat (via Parselmouth) for F0 estimation."""
        pm = self._parselmouth

        sound = pm.Sound(values=mono.astype(np.float64), sampling_frequency=float(sr))
        pitch_obj = sound.to_pitch_ac(
            time_step=hop_length / sr,
            pitch_floor=50.0,
            pitch_ceiling=800.0,
        )

        frames = pitch_obj.n_frames
        f0 = np.zeros(frames, dtype=np.float32)
        voiced = np.zeros(frames, dtype=bool)

        for i in range(frames):
            val = pitch_obj.get_value_in_frame(i + 1)
            if val is not None and not np.isnan(val) and val > 0:
                f0[i] = float(val)
                voiced[i] = True

        return f0, voiced

    @staticmethod
    def _ensure_mono(audio: np.ndarray) -> np.ndarray:
        audio = audio.astype(np.float32)
        if audio.ndim == 1:
            return audio
        if audio.ndim == 2:
            return audio.mean(axis=0) if audio.shape[0] <= 8 else audio.mean(axis=1)
        raise ValueError(f"Unsupported audio shape: {audio.shape}")

    # ------------------------------------------------------------------
    # Utility: semitone conversion
    # ------------------------------------------------------------------

    @staticmethod
    def hz_to_semitones(f0_hz: np.ndarray, reference_hz: float = 440.0) -> np.ndarray:
        """
        Convert an F0 array from Hz to semitones relative to *reference_hz*.

        Unvoiced frames (f0 == 0) map to NaN.
        """
        out = np.full_like(f0_hz, np.nan, dtype=np.float32)
        voiced = f0_hz > 0
        out[voiced] = 12.0 * np.log2(f0_hz[voiced] / reference_hz)
        return out

    @staticmethod
    def semitones_to_hz(semitones: np.ndarray, reference_hz: float = 440.0) -> np.ndarray:
        """Inverse of :meth:`hz_to_semitones`. NaN values map to 0 Hz."""
        out = np.zeros_like(semitones, dtype=np.float32)
        valid = ~np.isnan(semitones)
        out[valid] = reference_hz * (2.0 ** (semitones[valid] / 12.0))
        return out
