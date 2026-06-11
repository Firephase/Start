"""
Key and Tempo Detection Module
================================
Comprehensive musical structure analysis using librosa.
Implements Krumhansl-Schmuckler key profiles for all 24 major/minor keys,
multi-resolution beat tracking, and time-signature detection.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import librosa
import scipy.signal
import scipy.stats

logger = logging.getLogger(__name__)

# ===========================================================================
# Krumhansl-Schmuckler key profiles
# ===========================================================================
# Original profiles from:
#   Krumhansl, C. L. (1990). Cognitive Foundations of Musical Pitch.
#   Oxford University Press.
#
# These are correlational profiles measuring how well each pitch class "fits"
# the given key context.  Each 12-element array starts at C (pitch class 0).

_KS_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float64,
)

_KS_MINOR = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float64,
)

# Note names for MIDI pitch class 0 (C) … 11 (B)
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# All 24 keys in canonical order (used for returning human-readable names)
_ALL_KEYS: list[str] = [
    f"{note} {mode}"
    for note in _NOTE_NAMES
    for mode in ("major", "minor")
]


class MusicAnalyzer:
    """
    Comprehensive musical structure analysis for audio recordings.

    All methods accept a raw waveform + sample rate and return plain Python
    dicts so results can be serialised to JSON without further processing.

    Key detection uses the Krumhansl-Schmuckler algorithm:
    chroma features are extracted via CQT and compared (Pearson r) against
    all 24 major/minor pitch-class profiles.  The profile with the highest
    correlation determines the key and mode.

    Tempo detection uses librosa's multi-resolution approach (onset envelope
    at multiple hop sizes) to improve robustness for non-metronomic singing.

    Class constants
    ---------------
    KS_MAJOR : np.ndarray
        Krumhansl-Schmuckler major key profile (12 pitch classes, C=0).
    KS_MINOR : np.ndarray
        Krumhansl-Schmuckler minor key profile (12 pitch classes, C=0).
    NOTE_NAMES : list[str]
        Chromatic scale note names, C=0.
    ALL_KEYS : list[str]
        All 24 major/minor key names in chromatic order.
    """

    KS_MAJOR: np.ndarray = _KS_MAJOR
    KS_MINOR: np.ndarray = _KS_MINOR
    NOTE_NAMES: list[str] = _NOTE_NAMES
    ALL_KEYS: list[str] = _ALL_KEYS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_key(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """
        Estimate the musical key of *audio* using Krumhansl-Schmuckler.

        The chroma is extracted with the constant-Q transform at high
        frequency resolution (``bins_per_octave=36``) and accumulated over
        all frames to form a 12-element pitch-class distribution.  This
        distribution is then correlated against all 24 key profiles.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo waveform.
        sr : int
            Sample rate of *audio*.

        Returns
        -------
        dict with keys:
            ``key`` : str
                Human-readable key, e.g. ``'A minor'``.
            ``mode`` : str
                ``'major'`` or ``'minor'``.
            ``root_note`` : int
                Pitch class (0 = C, 1 = C#, … 11 = B).
            ``confidence`` : float
                Pearson r of the best-matching profile, mapped to [0, 1].
            ``all_scores`` : dict[str, float]
                Correlation scores for all 24 keys (useful for debugging).
        """
        mono = self._ensure_mono(audio)

        # CQT-based chroma; higher bins_per_octave → better pitch resolution
        chroma = librosa.feature.chroma_cqt(y=mono, sr=sr, bins_per_octave=36)
        chroma_mean = chroma.mean(axis=1).astype(np.float64)  # (12,)

        scores: dict[str, float] = {}
        best_r = -np.inf
        best_root = 0
        best_mode = "major"

        for root in range(12):
            for mode, profile in (("major", self.KS_MAJOR), ("minor", self.KS_MINOR)):
                # Rotate profile to align with current root
                rotated = np.roll(profile, root)
                r = float(np.corrcoef(chroma_mean, rotated)[0, 1])
                key_name = f"{self.NOTE_NAMES[root]} {mode}"
                scores[key_name] = round(r, 4)

                if r > best_r:
                    best_r = r
                    best_root = root
                    best_mode = mode

        confidence = float(np.clip(best_r, 0.0, 1.0))
        key_str = f"{self.NOTE_NAMES[best_root]} {best_mode}"

        return {
            "key": key_str,
            "mode": best_mode,
            "root_note": best_root,
            "confidence": confidence,
            "all_scores": scores,
        }

    def detect_tempo(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """
        Estimate tempo and beat positions using multi-resolution beat tracking.

        A combination of hop sizes is used to stabilise the BPM estimate for
        recordings with slight tempo drift (common in amateur vocals).  The
        final BPM is the median of per-resolution estimates.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo waveform.
        sr : int
            Sample rate of *audio*.

        Returns
        -------
        dict with keys:
            ``bpm`` : float
                Estimated tempo in beats per minute.
            ``beat_frames`` : np.ndarray
                Frame indices of detected beats (frame size = hop_length at
                the primary resolution).
            ``beat_times`` : np.ndarray
                Timestamps (seconds) of detected beats.
        """
        mono = self._ensure_mono(audio)

        # Primary tracking at hop=512 frames
        primary_hop = 512
        tempo_primary, beat_frames = librosa.beat.beat_track(
            y=mono, sr=sr, hop_length=primary_hop, trim=False, units="frames"
        )
        bpm_primary = float(np.atleast_1d(tempo_primary)[0])

        # Secondary estimates at different resolutions for robustness
        bpm_estimates = [bpm_primary]
        for hop in (256, 1024):
            t, _ = librosa.beat.beat_track(
                y=mono, sr=sr, hop_length=hop, trim=False, units="frames"
            )
            bpm_estimates.append(float(np.atleast_1d(t)[0]))

        bpm = float(np.median(bpm_estimates))

        # Convert beat frames to timestamps using primary hop size
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sr, hop_length=primary_hop
        ).astype(np.float32)

        return {
            "bpm": round(bpm, 2),
            "beat_frames": beat_frames,
            "beat_times": beat_times,
        }

    def detect_time_signature(
        self,
        beat_frames: np.ndarray,
        audio: np.ndarray,
        sr: int,
    ) -> dict[str, int]:
        """
        Estimate the time signature by detecting groupings of beat-level energy.

        The onset strength is evaluated at each beat position.  Periodicity
        analysis over windows of 2, 3, and 4 beats identifies which grouping
        has the most consistent accent pattern.

        Parameters
        ----------
        beat_frames : np.ndarray
            Beat frame indices (from :meth:`detect_tempo`).
        audio : np.ndarray
            Mono or stereo waveform (used to compute onset strength at beats).
        sr : int
            Sample rate.

        Returns
        -------
        dict with keys:
            ``numerator`` : int   – beats per bar (2, 3, or 4).
            ``denominator`` : int – always 4 (quarter note beats).
        """
        if len(beat_frames) < 8:
            # Not enough beats to reliably detect grouping; default to 4/4
            return {"numerator": 4, "denominator": 4}

        mono = self._ensure_mono(audio)
        hop = 512
        onset_env = librosa.onset.onset_strength(y=mono, sr=sr, hop_length=hop)

        # Sample onset strength at each beat frame
        beat_energy = np.array(
            [
                float(onset_env[min(int(f), len(onset_env) - 1)])
                for f in beat_frames
            ]
        )

        # Score each candidate meter by measuring the strength of
        # energy at positions 1, 1+N, 1+2N, … (downbeats) relative
        # to other beat positions.
        best_n = 4
        best_score = -np.inf

        for n in (2, 3, 4):
            downbeat_energy = beat_energy[::n]
            offbeat_mask = np.ones(len(beat_energy), dtype=bool)
            offbeat_mask[::n] = False
            offbeat_energy = beat_energy[offbeat_mask]

            if offbeat_energy.size == 0:
                continue

            # Score = mean downbeat energy minus mean offbeat energy
            score = float(downbeat_energy.mean() - offbeat_energy.mean())

            if score > best_score:
                best_score = score
                best_n = n

        return {"numerator": best_n, "denominator": 4}

    def analyze(self, audio: np.ndarray, sr: int) -> dict[str, Any]:
        """
        Run the full musical analysis pipeline.

        Combines key detection, tempo tracking, and time-signature estimation
        into a single call.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo waveform.
        sr : int
            Sample rate.

        Returns
        -------
        dict
            Merged dict containing all keys from :meth:`detect_key`,
            :meth:`detect_tempo`, and :meth:`detect_time_signature`, plus:

            ``duration_seconds`` : float – total audio duration.
        """
        key_info = self.detect_key(audio, sr)
        tempo_info = self.detect_tempo(audio, sr)
        ts_info = self.detect_time_signature(
            tempo_info["beat_frames"], audio, sr
        )

        mono = self._ensure_mono(audio)
        duration = len(mono) / sr

        return {
            # Key
            "key": key_info["key"],
            "mode": key_info["mode"],
            "root_note": key_info["root_note"],
            "key_confidence": key_info["confidence"],
            "all_key_scores": key_info["all_scores"],
            # Tempo
            "bpm": tempo_info["bpm"],
            "beat_frames": tempo_info["beat_frames"],
            "beat_times": tempo_info["beat_times"],
            # Time signature
            "time_signature_numerator": ts_info["numerator"],
            "time_signature_denominator": ts_info["denominator"],
            # Meta
            "duration_seconds": round(duration, 3),
        }

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    @staticmethod
    def pitch_class_to_note(pitch_class: int) -> str:
        """Convert MIDI pitch class 0–11 to note name string (e.g. 0 → 'C')."""
        return _NOTE_NAMES[int(pitch_class) % 12]

    @staticmethod
    def bpm_to_beat_duration(bpm: float) -> float:
        """Return the duration (seconds) of one beat at *bpm*."""
        if bpm <= 0:
            raise ValueError(f"BPM must be positive, got {bpm}.")
        return 60.0 / bpm

    @staticmethod
    def relative_key(key: str) -> str:
        """
        Return the relative major/minor key.

        E.g. ``'A minor'`` → ``'C major'``, ``'C major'`` → ``'A minor'``.
        """
        parts = key.strip().rsplit(" ", 1)
        if len(parts) != 2:
            raise ValueError(f"Cannot parse key string '{key}'.")
        note_str, mode = parts

        if note_str not in _NOTE_NAMES:
            raise ValueError(f"Unknown note '{note_str}' in key '{key}'.")

        root = _NOTE_NAMES.index(note_str)

        if mode == "major":
            rel_root = (root - 3) % 12
            return f"{_NOTE_NAMES[rel_root]} minor"
        elif mode == "minor":
            rel_root = (root + 3) % 12
            return f"{_NOTE_NAMES[rel_root]} major"
        else:
            raise ValueError(f"Unknown mode '{mode}' in key '{key}'.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_mono(audio: np.ndarray) -> np.ndarray:
        audio = audio.astype(np.float32)
        if audio.ndim == 1:
            return audio
        if audio.ndim == 2:
            return audio.mean(axis=0) if audio.shape[0] <= 8 else audio.mean(axis=1)
        raise ValueError(
            f"Unsupported audio shape {audio.shape}. "
            "Expected 1-D (samples,) or 2-D (channels, samples)."
        )
