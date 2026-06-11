import numpy as np
import torch
import torchaudio
import torchaudio.functional as F
import torchaudio.transforms as T
from typing import Optional
import scipy.signal as signal


class StemMixer:
    """Multi-stem audio mixer: vocals + instrumental → final mix."""

    # Standard mix levels (dBFS)
    VOCAL_LEVEL_DB = -3.0
    INSTRUMENTAL_LEVEL_DB = -6.0

    def __init__(self, target_sr: int = 44100):
        self.target_sr = target_sr

    def mix(
        self,
        vocals: np.ndarray,
        instrumental: np.ndarray,
        vocal_db: float = VOCAL_LEVEL_DB,
        instrumental_db: float = INSTRUMENTAL_LEVEL_DB,
        instrumental_sr: int = 32000,
    ) -> np.ndarray:
        """Mix vocals and instrumental into final stereo track."""
        # Resample instrumental if needed (MusicGen outputs 32kHz)
        if instrumental_sr != self.target_sr:
            instrumental = self._resample(instrumental, instrumental_sr, self.target_sr)

        vocals = self._to_stereo(vocals)
        instrumental = self._to_stereo(instrumental)

        # Match lengths
        min_len = min(vocals.shape[-1], instrumental.shape[-1])
        vocals = vocals[..., :min_len]
        instrumental = instrumental[..., :min_len]

        # Apply gain
        vocals = self._apply_gain_db(vocals, vocal_db)
        instrumental = self._apply_gain_db(instrumental, instrumental_db)

        # Widen instrumental slightly
        instrumental = self._stereo_widen(instrumental, width=1.3)

        # Sum and clip-safe normalize
        mixed = vocals + instrumental
        mixed = self._peak_normalize(mixed, target_db=-1.0)

        return mixed

    def create_vocal_chain(self, vocals: np.ndarray, sr: int) -> np.ndarray:
        """Apply standard vocal processing chain."""
        # High-pass filter at 80Hz (remove low rumble)
        vocals = self._highpass(vocals, sr, cutoff=80.0)
        # De-ess: reduce harsh sibilance around 6-8kHz
        vocals = self._deess(vocals, sr)
        # Light compression
        vocals = self._compress(vocals, threshold=-18.0, ratio=3.0, attack_ms=5.0, release_ms=80.0)
        return vocals

    def create_instrumental_chain(self, instrumental: np.ndarray, sr: int) -> np.ndarray:
        """Apply standard instrumental processing."""
        # High-pass at 30Hz
        instrumental = self._highpass(instrumental, sr, cutoff=30.0)
        # Gentle compression for glue
        instrumental = self._compress(instrumental, threshold=-12.0, ratio=2.0, attack_ms=20.0, release_ms=200.0)
        return instrumental

    def _resample(self, audio: np.ndarray, src_sr: int, tgt_sr: int) -> np.ndarray:
        t = torch.from_numpy(audio).float()
        if t.dim() == 1:
            t = t.unsqueeze(0)
        t = torchaudio.functional.resample(t, src_sr, tgt_sr)
        return t.numpy()

    def _to_stereo(self, audio: np.ndarray) -> np.ndarray:
        if audio.ndim == 1:
            return np.stack([audio, audio], axis=0)
        if audio.shape[0] == 1:
            return np.concatenate([audio, audio], axis=0)
        return audio

    def _apply_gain_db(self, audio: np.ndarray, gain_db: float) -> np.ndarray:
        return audio * (10.0 ** (gain_db / 20.0))

    def _peak_normalize(self, audio: np.ndarray, target_db: float = -1.0) -> np.ndarray:
        peak = np.abs(audio).max()
        if peak < 1e-8:
            return audio
        target_linear = 10.0 ** (target_db / 20.0)
        return audio * (target_linear / peak)

    def _stereo_widen(self, audio: np.ndarray, width: float = 1.2) -> np.ndarray:
        """Mid-side stereo widening."""
        if audio.ndim < 2 or audio.shape[0] < 2:
            return audio
        mid = (audio[0] + audio[1]) * 0.5
        side = (audio[0] - audio[1]) * 0.5
        side *= width
        left = mid + side
        right = mid - side
        return np.stack([left, right], axis=0)

    def _highpass(self, audio: np.ndarray, sr: int, cutoff: float) -> np.ndarray:
        b, a = signal.butter(4, cutoff / (sr / 2), btype='high')
        if audio.ndim == 1:
            return signal.filtfilt(b, a, audio).astype(np.float32)
        return np.stack([signal.filtfilt(b, a, ch).astype(np.float32) for ch in audio])

    def _deess(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Simple de-esser: dynamic EQ cut at 6-8kHz."""
        # Band-pass filter to detect sibilance
        b_detect, a_detect = signal.butter(2, [6000 / (sr / 2), 8000 / (sr / 2)], btype='band')
        b_cut, a_cut = signal.butter(2, [5500 / (sr / 2), 8500 / (sr / 2)], btype='band')
        threshold = 0.05

        def process_channel(ch):
            sibilance = signal.filtfilt(b_detect, a_detect, ch)
            gain_reduction = np.where(np.abs(sibilance) > threshold, 0.7, 1.0)
            sibilance_band = signal.filtfilt(b_cut, a_cut, ch)
            return ch - sibilance_band * (1.0 - gain_reduction)

        if audio.ndim == 1:
            return process_channel(audio).astype(np.float32)
        return np.stack([process_channel(ch).astype(np.float32) for ch in audio])

    def _compress(
        self,
        audio: np.ndarray,
        threshold: float,
        ratio: float,
        attack_ms: float,
        release_ms: float,
    ) -> np.ndarray:
        """Simple feed-forward compressor."""
        sr = self.target_sr
        attack_coeff = np.exp(-1.0 / (sr * attack_ms / 1000.0))
        release_coeff = np.exp(-1.0 / (sr * release_ms / 1000.0))
        threshold_lin = 10.0 ** (threshold / 20.0)

        def compress_channel(ch):
            envelope = np.zeros_like(ch)
            gain = np.zeros_like(ch)
            env = 0.0
            for i, sample in enumerate(np.abs(ch)):
                if sample > env:
                    env = attack_coeff * env + (1.0 - attack_coeff) * sample
                else:
                    env = release_coeff * env + (1.0 - release_coeff) * sample
                envelope[i] = env

            over = envelope / (threshold_lin + 1e-8)
            over_db = 20.0 * np.log10(np.maximum(over, 1e-8))
            gain_reduction_db = np.where(over > 1.0, over_db * (1.0 - 1.0 / ratio), 0.0)
            gain = 10.0 ** (-gain_reduction_db / 20.0)
            return ch * gain

        if audio.ndim == 1:
            return compress_channel(audio).astype(np.float32)
        return np.stack([compress_channel(ch).astype(np.float32) for ch in audio])
