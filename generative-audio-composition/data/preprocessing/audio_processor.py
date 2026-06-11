"""
Audio preprocessing pipeline for generative audio training.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
import librosa
import soundfile as sf
import torch
import torchaudio

log = logging.getLogger(__name__)


class AudioProcessor:
    """
    End-to-end audio preprocessing utility.

    Class-level constant listing recognised file extensions.
    """

    SUPPORTED_FORMATS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus"}

    """
    (Original docstring continues below)

    End-to-end audio preprocessing utility (continued):

    Provides loading, resampling, silence trimming, mel spectrogram extraction,
    length normalization, and segmentation. All methods operate on NumPy arrays
    to remain framework-agnostic; convert to tensors in your Dataset.__getitem__.

    Args:
        default_sr: Sample rate used when none is specified in method calls.
        n_fft: FFT size for spectrogram computation.
        hop_length: Hop size for spectrogram computation.
        win_length: Window length (defaults to n_fft).
        n_mels: Number of mel filter banks.
        f_min: Minimum frequency for mel filterbank.
        f_max: Maximum frequency for mel filterbank. None -> sr / 2.
        top_db: Dynamic range (dB) for dB-scale mel normalization.
    """

    def __init__(
        self,
        default_sr: int = 44100,
        n_fft: int = 2048,
        hop_length: int = 512,
        win_length: Optional[int] = None,
        n_mels: int = 128,
        f_min: float = 0.0,
        f_max: Optional[float] = None,
        top_db: float = 80.0,
    ) -> None:
        self.default_sr = default_sr
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.win_length = win_length or n_fft
        self.n_mels = n_mels
        self.f_min = f_min
        self.f_max = f_max
        self.top_db = top_db

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(
        self,
        path: Union[str, Path],
        target_sr: int = 44100,
    ) -> Tuple[np.ndarray, int]:
        """
        Load any audio format into a float32 NumPy array.

        Handles wav, flac, mp3, m4a, ogg and other formats supported by
        soundfile / torchaudio backends. Returned audio is always float32
        in [-1, 1] and mono-converted if the caller subsequently calls
        to_mono().

        Args:
            path: Path to audio file.
            target_sr: Target sample rate. Audio will be resampled if the
                       file's native rate differs.

        Returns:
            (audio, sample_rate) where audio has shape (channels, samples)
            or (samples,) depending on the source file.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        audio: Optional[np.ndarray] = None
        sr: Optional[int] = None

        # --- Try soundfile first (fast, handles wav / flac / ogg) --------
        try:
            import soundfile as sf
            audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
            # soundfile returns (samples,) for mono or (samples, channels) for multi
            if audio.ndim == 2:
                audio = audio.T  # -> (channels, samples)
        except Exception:
            audio = None

        # --- Fall back to torchaudio (handles mp3, m4a, etc.) ------------
        if audio is None:
            try:
                import torchaudio
                waveform, sr = torchaudio.load(str(path))
                audio = waveform.numpy()  # (channels, samples)
            except Exception as exc:
                raise RuntimeError(f"Could not load audio file '{path}': {exc}") from exc

        # Ensure float32
        audio = audio.astype(np.float32)

        # Resample if needed
        if sr != target_sr:
            audio = self.resample(audio, sr, target_sr)
            sr = target_sr

        return audio, sr

    # ------------------------------------------------------------------
    # Resampling
    # ------------------------------------------------------------------

    def resample(
        self,
        audio: np.ndarray,
        src_sr: int,
        tgt_sr: int,
    ) -> np.ndarray:
        """
        Resample audio from src_sr to tgt_sr using librosa's high-quality resampler.

        Args:
            audio: Input waveform. Shape: (T,) or (C, T).
            src_sr: Source sample rate.
            tgt_sr: Target sample rate.

        Returns:
            Resampled waveform, same leading dimensions, new length.
        """
        if src_sr == tgt_sr:
            return audio

        try:
            import librosa
            if audio.ndim == 1:
                return librosa.resample(audio, orig_sr=src_sr, target_sr=tgt_sr)
            # Multi-channel: resample each channel independently
            channels = [
                librosa.resample(audio[c], orig_sr=src_sr, target_sr=tgt_sr)
                for c in range(audio.shape[0])
            ]
            return np.stack(channels, axis=0)
        except ImportError:
            pass

        # Fallback: scipy.signal.resample_poly
        try:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(src_sr, tgt_sr)
            up, down = tgt_sr // g, src_sr // g
            if audio.ndim == 1:
                return resample_poly(audio, up, down).astype(np.float32)
            channels = [
                resample_poly(audio[c], up, down).astype(np.float32)
                for c in range(audio.shape[0])
            ]
            return np.stack(channels, axis=0)
        except ImportError as exc:
            raise RuntimeError(
                "Install librosa or scipy for resampling support."
            ) from exc

    # ------------------------------------------------------------------
    # Channel conversion
    # ------------------------------------------------------------------

    def to_mono(self, audio: np.ndarray) -> np.ndarray:
        """
        Convert stereo or multi-channel audio to mono by averaging channels.

        Args:
            audio: Shape (T,) or (C, T).

        Returns:
            Mono waveform of shape (T,).
        """
        if audio.ndim == 1:
            return audio
        return audio.mean(axis=0)

    # ------------------------------------------------------------------
    # Silence trimming
    # ------------------------------------------------------------------

    def trim_silence(
        self,
        audio: np.ndarray,
        sr: int,
        threshold_db: float = -40.0,
    ) -> np.ndarray:
        """
        Remove leading and trailing silence below the energy threshold.

        Uses a short-time energy envelope with a 10 ms frame size.

        Args:
            audio: Mono waveform (T,).
            sr: Sample rate.
            threshold_db: Energy threshold in dBFS below which frames
                          are considered silent.

        Returns:
            Trimmed waveform (T',).
        """
        # Prefer librosa for robustness
        try:
            import librosa
            trimmed, _ = librosa.effects.trim(
                audio,
                top_db=-threshold_db if threshold_db < 0 else threshold_db,
                frame_length=int(0.025 * sr),
                hop_length=int(0.010 * sr),
            )
            return trimmed
        except ImportError:
            pass

        # Manual short-time energy fallback
        frame_size = int(0.025 * sr)
        hop = int(0.010 * sr)
        threshold_linear = 10.0 ** (threshold_db / 20.0)

        n_frames = max(1, (len(audio) - frame_size) // hop + 1)
        energies = np.array(
            [np.sqrt(np.mean(audio[i * hop : i * hop + frame_size] ** 2)) for i in range(n_frames)]
        )
        active = energies > threshold_linear

        if not active.any():
            return audio

        first = int(np.argmax(active)) * hop
        last = int(len(active) - np.argmax(active[::-1]) - 1) * hop + frame_size
        return audio[first:last]

    # ------------------------------------------------------------------
    # Mel spectrogram
    # ------------------------------------------------------------------

    def extract_mel(
        self,
        audio: np.ndarray,
        sr: int,
        n_mels: Optional[int] = None,
        hop_length: Optional[int] = None,
    ) -> np.ndarray:
        """
        Compute linear-scale mel spectrogram (power).

        Args:
            audio: Mono waveform (T,).
            sr: Sample rate.
            n_mels: Number of mel bins (overrides instance default).
            hop_length: Hop size in samples (overrides instance default).

        Returns:
            Mel spectrogram of shape (n_mels, frames) in linear power scale.
        """
        n_mels = n_mels or self.n_mels
        hop_length = hop_length or self.hop_length
        f_max = self.f_max or sr / 2.0

        try:
            import librosa
            mel = librosa.feature.melspectrogram(
                y=audio,
                sr=sr,
                n_fft=self.n_fft,
                hop_length=hop_length,
                win_length=self.win_length,
                n_mels=n_mels,
                fmin=self.f_min,
                fmax=f_max,
                power=2.0,
            )
            return mel.astype(np.float32)
        except ImportError as exc:
            raise RuntimeError("librosa is required for mel spectrogram extraction.") from exc

    def extract_mel_db(self, mel: np.ndarray) -> np.ndarray:
        """
        Convert a linear-scale mel spectrogram to dB scale.

        Uses the formula: 10 * log10(mel / ref_max), then clips to
        [-top_db, 0] dBFS.

        Args:
            mel: Linear mel spectrogram (n_mels, frames), power scale.

        Returns:
            dB-scale mel spectrogram (n_mels, frames), float32.
        """
        try:
            import librosa
            mel_db = librosa.power_to_db(mel, ref=np.max, top_db=self.top_db)
            return mel_db.astype(np.float32)
        except ImportError:
            pass

        # Manual fallback
        ref = np.max(mel) + 1e-10
        mel_db = 10.0 * np.log10(np.clip(mel, 1e-10, None) / ref)
        mel_db = np.clip(mel_db, -self.top_db, 0.0)
        return mel_db.astype(np.float32)

    # ------------------------------------------------------------------
    # Length normalization
    # ------------------------------------------------------------------

    def pad_or_trim(
        self,
        audio: np.ndarray,
        target_length: int,
    ) -> np.ndarray:
        """
        Pad with zeros or trim the waveform to exactly target_length samples.

        For padding, zeros are appended at the end.
        For trimming, a random start position is chosen to avoid always
        cutting from the end.

        Args:
            audio: Mono waveform (T,).
            target_length: Desired number of samples.

        Returns:
            Waveform of shape (target_length,).
        """
        current = len(audio)
        if current == target_length:
            return audio
        if current < target_length:
            pad_amount = target_length - current
            return np.pad(audio, (0, pad_amount), mode="constant")
        # Trim: random crop for data augmentation during training
        start = np.random.randint(0, current - target_length + 1)
        return audio[start : start + target_length]

    # ------------------------------------------------------------------
    # Segmentation
    # ------------------------------------------------------------------

    def segment(
        self,
        audio: np.ndarray,
        sr: int,
        segment_length: float = 10.0,
        overlap: float = 0.5,
    ) -> List[np.ndarray]:
        """
        Split a long audio recording into overlapping fixed-length segments.

        The last segment is zero-padded to reach segment_length if the
        remaining audio is shorter than one full segment.

        Args:
            audio: Mono waveform (T,).
            sr: Sample rate.
            segment_length: Duration of each segment in seconds.
            overlap: Fractional overlap between consecutive segments [0, 1).
                     0.5 means 50% overlap.

        Returns:
            List of numpy arrays, each of shape (segment_samples,).
        """
        if not (0.0 <= overlap < 1.0):
            raise ValueError(f"overlap must be in [0, 1), got {overlap}")

        segment_samples = int(segment_length * sr)
        hop_samples = int(segment_samples * (1.0 - overlap))
        if hop_samples < 1:
            hop_samples = 1

        segments: List[np.ndarray] = []
        total = len(audio)

        start = 0
        while start < total:
            end = start + segment_samples
            chunk = audio[start:end]
            if len(chunk) < segment_samples:
                chunk = np.pad(chunk, (0, segment_samples - len(chunk)), mode="constant")
            segments.append(chunk.astype(np.float32))
            start += hop_samples

        return segments
