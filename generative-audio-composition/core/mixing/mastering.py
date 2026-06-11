import numpy as np
import torch
import scipy.signal as signal
from typing import Optional


class NeuralMastering:
    """
    Neural mastering chain: EQ → multiband compression → stereo enhancement → limiting.
    Targets -14 LUFS for streaming (Spotify/Apple Music spec).
    """

    TARGET_LUFS = -14.0
    TRUE_PEAK_DBFS = -1.0

    def __init__(self, sample_rate: int = 44100):
        self.sr = sample_rate

    def master(self, audio: np.ndarray, target_lufs: float = TARGET_LUFS) -> np.ndarray:
        """Full mastering chain."""
        audio = self._eq(audio)
        audio = self._multiband_compress(audio)
        audio = self._mid_side_enhance(audio)
        audio = self._loudness_normalize(audio, target_lufs)
        audio = self._true_peak_limit(audio)
        return audio.astype(np.float32)

    def _eq(self, audio: np.ndarray) -> np.ndarray:
        """Mastering EQ: gentle shelving + presence boost."""
        # Low shelf boost +1.5dB at 80Hz
        audio = self._low_shelf(audio, freq=80.0, gain_db=1.5)
        # High shelf boost +1dB at 12kHz (air)
        audio = self._high_shelf(audio, freq=12000.0, gain_db=1.0)
        # Slight cut -0.5dB at 400Hz (muddiness)
        audio = self._peak_eq(audio, freq=400.0, gain_db=-0.5, q=1.0)
        # Presence boost +0.8dB at 3.5kHz
        audio = self._peak_eq(audio, freq=3500.0, gain_db=0.8, q=2.0)
        return audio

    def _multiband_compress(self, audio: np.ndarray) -> np.ndarray:
        """3-band multiband compression."""
        # Split into bands: lows (<200Hz), mids (200-5kHz), highs (>5kHz)
        low_band = self._lowpass(audio, cutoff=200.0)
        high_band = self._highpass(audio, cutoff=5000.0)
        mid_band = audio - low_band - high_band

        low_band = self._compress_band(low_band, threshold=-18.0, ratio=3.0, attack_ms=30.0, release_ms=150.0)
        mid_band = self._compress_band(mid_band, threshold=-15.0, ratio=2.5, attack_ms=10.0, release_ms=100.0)
        high_band = self._compress_band(high_band, threshold=-20.0, ratio=2.0, attack_ms=5.0, release_ms=60.0)

        return low_band + mid_band + high_band

    def _mid_side_enhance(self, audio: np.ndarray) -> np.ndarray:
        """Gentle M/S processing: tighten bass in mid, widen high-mids."""
        if audio.ndim < 2 or audio.shape[0] < 2:
            return audio

        mid = (audio[0] + audio[1]) * 0.5
        side = (audio[0] - audio[1]) * 0.5

        # Mono-ize bass below 120Hz
        side_low = self._lowpass(side, cutoff=120.0)
        side = side - side_low  # remove low-freq from side

        # Slightly widen high-mids (2-8kHz) in side channel
        side_highmid = self._bandpass(side, low=2000.0, high=8000.0)
        side = side + side_highmid * 0.15

        left = mid + side
        right = mid - side
        return np.stack([left, right], axis=0)

    def _loudness_normalize(self, audio: np.ndarray, target_lufs: float) -> np.ndarray:
        """Integrated loudness normalization (simplified ITU-R BS.1770)."""
        measured_lufs = self._measure_lufs(audio)
        gain_db = target_lufs - measured_lufs
        gain_linear = 10.0 ** (gain_db / 20.0)
        return audio * gain_linear

    def _true_peak_limit(self, audio: np.ndarray, ceiling_dbfs: float = TRUE_PEAK_DBFS) -> np.ndarray:
        """Brick-wall limiter at ceiling."""
        ceiling_lin = 10.0 ** (ceiling_dbfs / 20.0)
        peak = np.abs(audio).max()
        if peak > ceiling_lin:
            audio = audio * (ceiling_lin / peak)
        return audio

    def _measure_lufs(self, audio: np.ndarray) -> float:
        """Simplified LUFS measurement (momentary power approximation)."""
        if audio.ndim > 1:
            mono = audio.mean(axis=0)
        else:
            mono = audio
        # K-weighting: high-pass at 60Hz + high-shelf at 1.5kHz
        mono = self._highpass(mono, cutoff=60.0)
        # Mean square power → LUFS
        mean_sq = np.mean(mono ** 2)
        if mean_sq < 1e-10:
            return -70.0
        return -0.691 + 10.0 * np.log10(mean_sq)

    # ── Filter primitives ──────────────────────────────────────────────────────

    def _lowpass(self, audio: np.ndarray, cutoff: float, order: int = 4) -> np.ndarray:
        b, a = signal.butter(order, cutoff / (self.sr / 2), btype='low')
        return self._apply_filter(audio, b, a)

    def _highpass(self, audio: np.ndarray, cutoff: float, order: int = 4) -> np.ndarray:
        b, a = signal.butter(order, cutoff / (self.sr / 2), btype='high')
        return self._apply_filter(audio, b, a)

    def _bandpass(self, audio: np.ndarray, low: float, high: float) -> np.ndarray:
        nyq = self.sr / 2
        b, a = signal.butter(2, [low / nyq, high / nyq], btype='band')
        return self._apply_filter(audio, b, a)

    def _low_shelf(self, audio: np.ndarray, freq: float, gain_db: float) -> np.ndarray:
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2 * np.pi * freq / self.sr
        S = 1.0
        alpha = np.sin(w0) / 2 * np.sqrt((A + 1 / A) * (1 / S - 1) + 2)
        b0 = A * ((A + 1) - (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha)
        b1 = 2 * A * ((A - 1) - (A + 1) * np.cos(w0))
        b2 = A * ((A + 1) - (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) + (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha
        a1 = -2 * ((A - 1) + (A + 1) * np.cos(w0))
        a2 = (A + 1) + (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1.0, a1 / a0, a2 / a0])
        return self._apply_filter(audio, b, a)

    def _high_shelf(self, audio: np.ndarray, freq: float, gain_db: float) -> np.ndarray:
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2 * np.pi * freq / self.sr
        S = 1.0
        alpha = np.sin(w0) / 2 * np.sqrt((A + 1 / A) * (1 / S - 1) + 2)
        b0 = A * ((A + 1) + (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha)
        b1 = -2 * A * ((A - 1) + (A + 1) * np.cos(w0))
        b2 = A * ((A + 1) + (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha)
        a0 = (A + 1) - (A - 1) * np.cos(w0) + 2 * np.sqrt(A) * alpha
        a1 = 2 * ((A - 1) - (A + 1) * np.cos(w0))
        a2 = (A + 1) - (A - 1) * np.cos(w0) - 2 * np.sqrt(A) * alpha
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1.0, a1 / a0, a2 / a0])
        return self._apply_filter(audio, b, a)

    def _peak_eq(self, audio: np.ndarray, freq: float, gain_db: float, q: float) -> np.ndarray:
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2 * np.pi * freq / self.sr
        alpha = np.sin(w0) / (2 * q)
        b0 = 1 + alpha * A
        b1 = -2 * np.cos(w0)
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A
        a1 = -2 * np.cos(w0)
        a2 = 1 - alpha / A
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1.0, a1 / a0, a2 / a0])
        return self._apply_filter(audio, b, a)

    def _apply_filter(self, audio: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
        if audio.ndim == 1:
            return signal.filtfilt(b, a, audio).astype(np.float32)
        return np.stack([signal.filtfilt(b, a, ch).astype(np.float32) for ch in audio])

    def _compress_band(
        self,
        audio: np.ndarray,
        threshold: float,
        ratio: float,
        attack_ms: float,
        release_ms: float,
    ) -> np.ndarray:
        sr = self.sr
        attack = np.exp(-1.0 / (sr * attack_ms / 1000.0))
        release = np.exp(-1.0 / (sr * release_ms / 1000.0))
        threshold_lin = 10.0 ** (threshold / 20.0)

        def compress_ch(ch):
            env = 0.0
            out = np.zeros_like(ch)
            for i, s in enumerate(ch):
                level = abs(s)
                if level > env:
                    env = attack * env + (1.0 - attack) * level
                else:
                    env = release * env + (1.0 - release) * level
                if env > threshold_lin:
                    over_db = 20.0 * np.log10(env / threshold_lin + 1e-8)
                    gr_db = over_db * (1.0 - 1.0 / ratio)
                    gain = 10.0 ** (-gr_db / 20.0)
                else:
                    gain = 1.0
                out[i] = s * gain
            return out

        if audio.ndim == 1:
            return compress_ch(audio).astype(np.float32)
        return np.stack([compress_ch(ch).astype(np.float32) for ch in audio])
