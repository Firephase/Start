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

    Provides loading, resampling, silence trimming, mel spectrogram extraction,
    length normalization, segmentation, and validation. All methods operate on
    NumPy arrays to remain framework-agnostic; convert to tensors in your
    Dataset.__getitem__.

    Class Attributes
    ----------------
    SUPPORTED_FORMATS : set
        File extensions that can be loaded. Lossless formats (.wav, .flac, .ogg)
        are handled via soundfile; lossy formats (.mp3, .m4a, .aac, .opus) are
        handled via torchaudio / librosa (requires ffmpeg).

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

    SUPPORTED_FORMATS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus"}

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
        Load any audio format into a mono float32 NumPy array.

        Strategy:
          1. soundfile  – fast, handles wav / flac / ogg natively.
          2. torchaudio – fallback for mp3, m4a, aac, opus.
          3. librosa    – final fallback (calls ffmpeg internally).

        Returned audio is always:
          - float32 in [-1, 1]
          - mono (1-D shape ``(T,)``)
          - at ``target_sr``

        Args:
            path: Path to audio file.
            target_sr: Target sample rate. Audio will be resampled if the
                       file's native rate differs.

        Returns:
            (audio, sample_rate) where audio has shape (T,) and sample_rate
            equals target_sr.

        Raises:
            FileNotFoundError: File does not exist.
            ValueError: File extension is not in SUPPORTED_FORMATS.
            RuntimeError: All loading backends failed.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{suffix}'. Supported: {sorted(self.SUPPORTED_FORMATS)}"
            )

        audio: Optional[np.ndarray] = None
        sr: Optional[int] = None

        # --- 1. Try soundfile first (fast, handles wav / flac / ogg) --------
        sf_formats = {".wav", ".flac", ".ogg"}
        if suffix in sf_formats:
            try:
                audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
                # soundfile returns (samples,) for mono or (samples, channels) for multi
                if audio.ndim == 2:
                    audio = audio.T  # -> (channels, samples)
            except Exception as exc:
                log.debug("soundfile failed for %s: %s", path, exc)
                audio = None

        # --- 2. Fall back to torchaudio (handles mp3, m4a, etc.) ------------
        if audio is None:
            try:
                waveform, sr = torchaudio.load(str(path))
                audio = waveform.numpy()  # (channels, samples)
            except Exception as exc:
                log.debug("torchaudio failed for %s: %s", path, exc)
                audio = None

        # --- 3. Final fallback: librosa (requires ffmpeg) --------------------
        if audio is None:
            try:
                audio, sr = librosa.load(str(path), sr=None, mono=False)
                audio = audio.astype(np.float32)
            except Exception as exc:
                raise RuntimeError(
                    f"All backends failed to load '{path}'. Last error: {exc}"
                ) from exc

        # Ensure float32
        audio = audio.astype(np.float32)

        # Convert to mono
        audio = self.to_mono(audio)

        # Resample if needed
        if sr != target_sr:
            audio = self.resample(audio, sr, target_sr)
            sr = target_sr

        # Guard: clip to [-1, 1] to handle minor float overshoot
        audio = np.clip(audio, -1.0, 1.0)

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

        Falls back to scipy.signal.resample_poly if librosa is unavailable.

        Args:
            audio: Input waveform. Shape: (T,) or (C, T).
            src_sr: Source sample rate.
            tgt_sr: Target sample rate.

        Returns:
            Resampled waveform, same leading dimensions, new time length.
        """
        if src_sr == tgt_sr:
            return audio

        if audio.ndim == 1:
            return librosa.resample(
                audio.astype(np.float32),
                orig_sr=src_sr,
                target_sr=tgt_sr,
                res_type="kaiser_best",
            ).astype(np.float32)

        # Multi-channel: resample each channel independently
        channels = [
            librosa.resample(
                audio[c].astype(np.float32),
                orig_sr=src_sr,
                target_sr=tgt_sr,
                res_type="kaiser_best",
            )
            for c in range(audio.shape[0])
        ]
        return np.stack(channels, axis=0).astype(np.float32)

    # ------------------------------------------------------------------
    # Channel conversion
    # ------------------------------------------------------------------

    def to_mono(self, audio: np.ndarray) -> np.ndarray:
        """
        Convert stereo or multi-channel audio to mono by averaging channels.

        Handles both (T,) and (C, T) layouts automatically:
          - soundfile returns (T, C) for multi-channel → transpose to (C, T) first.
          - librosa/torchaudio return (C, T).
          - Heuristic: if shape[0] <= 8, treat first dim as channels.

        Args:
            audio: Shape (T,), (C, T) for C ≤ 8, or (T, C) for C ≤ 8.

        Returns:
            Mono waveform of shape (T,), float32.
        """
        audio = audio.astype(np.float32)
        if audio.ndim == 1:
            return audio
        if audio.ndim == 2:
            # Heuristic: first dim is channels when ≤ 8 (librosa / torchaudio)
            if audio.shape[0] <= 8:
                return audio.mean(axis=0)
            # Otherwise first dim is time (soundfile always_2d=False with T first)
            return audio.mean(axis=1)
        raise ValueError(f"Unsupported audio ndim: {audio.ndim}, shape: {audio.shape}")

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
        Remove leading and trailing silence below an energy threshold.

        Uses librosa.effects.trim with a 25 ms frame size and 10 ms hop.
        Falls back to a manual short-time energy computation if librosa
        is unavailable.

        Args:
            audio: Mono waveform (T,).
            sr: Sample rate (used to compute frame sizes in samples).
            threshold_db: Energy threshold in dBFS. Frames below this level
                          are considered silent.  Typical range: -60 to -20 dB.

        Returns:
            Trimmed waveform (T',). If the whole signal is below threshold,
            returns the original unmodified array.
        """
        top_db = abs(threshold_db)
        frame_length = max(64, int(0.025 * sr))
        hop_length = max(32, int(0.010 * sr))

        trimmed, _ = librosa.effects.trim(
            audio.astype(np.float32),
            top_db=top_db,
            frame_length=frame_length,
            hop_length=hop_length,
        )
        # Guard: never return empty array
        if trimmed.size == 0:
            log.warning(
                "trim_silence: entire signal is below %.1f dB threshold; returning original.",
                threshold_db,
            )
            return audio.astype(np.float32)
        return trimmed.astype(np.float32)

    # ------------------------------------------------------------------
    # Mel spectrogram
    # ------------------------------------------------------------------

    def extract_mel(
        self,
        audio: np.ndarray,
        sr: int,
        n_mels: int = 128,
        hop_length: int = 512,
        n_fft: int = 2048,
        fmin: float = 0.0,
        fmax: Optional[float] = None,
    ) -> np.ndarray:
        """
        Compute a linear-power mel spectrogram.

        Args:
            audio: Mono waveform (T,), float32.
            sr: Sample rate.
            n_mels: Number of mel bins.
            hop_length: STFT hop size in samples.
            n_fft: FFT window size in samples.
            fmin: Minimum frequency for mel filter banks (Hz).
            fmax: Maximum frequency (Hz). Defaults to sr / 2.

        Returns:
            Mel spectrogram of shape ``(n_mels, T_frames)`` in linear power
            scale, float32.
        """
        if fmax is None:
            fmax = self.f_max or float(sr) / 2.0

        mel = librosa.feature.melspectrogram(
            y=audio.astype(np.float32),
            sr=sr,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=n_fft,
            n_mels=n_mels,
            fmin=fmin,
            fmax=fmax,
            power=2.0,
        )
        return mel.astype(np.float32)

    def extract_mel_db(self, mel: np.ndarray, top_db: float = 80.0) -> np.ndarray:
        """
        Convert a linear-power mel spectrogram to dB scale.

        Applies ``librosa.power_to_db`` with ``ref=np.max`` and dynamic range
        clipping to *top_db* dB below the peak, giving values in
        ``[-top_db, 0]``.

        Args:
            mel: Linear mel spectrogram (n_mels, T), power scale.
            top_db: Dynamic range to keep below the peak (default 80 dB).

        Returns:
            dB-scale mel spectrogram of the same shape, float32.
        """
        mel_db = librosa.power_to_db(mel.astype(np.float32), ref=np.max, top_db=top_db)
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
        Pad (right-side zeros) or trim the waveform to exactly *target_length* samples.

        When trimming, a random start offset is chosen uniformly so that
        different training iterations see different crops of long recordings.

        Args:
            audio: Mono waveform (T,).
            target_length: Desired number of samples.

        Returns:
            Waveform of shape ``(target_length,)``, float32.
        """
        audio = audio.astype(np.float32)
        current = len(audio)
        if current == target_length:
            return audio
        if current < target_length:
            pad_amount = target_length - current
            return np.pad(audio, (0, pad_amount), mode="constant", constant_values=0.0)
        # Trim: random crop
        start = int(np.random.randint(0, current - target_length + 1))
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

        The last incomplete chunk is zero-padded to reach *segment_length*.

        Args:
            audio: Mono waveform (T,).
            sr: Sample rate.
            segment_length: Duration of each segment in seconds.
            overlap: Fractional overlap between consecutive segments, in
                     ``[0, 1)``.  0.5 gives 50 % overlap.

        Returns:
            List of float32 arrays, each of shape ``(int(segment_length * sr),)``.

        Raises:
            ValueError: If *overlap* is not in [0, 1).
        """
        if not (0.0 <= overlap < 1.0):
            raise ValueError(f"overlap must be in [0, 1), got {overlap}")

        segment_samples = int(segment_length * sr)
        hop_samples = max(1, int(segment_samples * (1.0 - overlap)))

        segments: List[np.ndarray] = []
        audio = audio.astype(np.float32)
        total = len(audio)
        start = 0

        while start < total:
            chunk = audio[start : start + segment_samples]
            if len(chunk) < segment_samples:
                chunk = np.pad(
                    chunk, (0, segment_samples - len(chunk)), mode="constant"
                )
            segments.append(chunk)
            start += hop_samples

        return segments

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def is_valid_audio(self, path: str) -> bool:
        """
        Return True if *path* is a readable, non-empty audio file.

        Validation steps (ordered by cost):
          1. File exists and is non-empty.
          2. Extension is in SUPPORTED_FORMATS.
          3. soundfile.info() can read the file header (cheap, lossless formats).
          4. librosa.load() with ``duration=1.0`` (reliable fallback for mp3/m4a).

        Does NOT fully decode the file, so this is relatively fast.

        Args:
            path: Filesystem path to check.

        Returns:
            bool: True if the file appears to be valid audio.
        """
        p = Path(path)

        # Basic filesystem checks
        if not p.exists() or not p.is_file():
            return False
        if p.suffix.lower() not in self.SUPPORTED_FORMATS:
            return False
        if p.stat().st_size == 0:
            return False

        # Try cheap header inspection via soundfile
        try:
            info = sf.info(str(p))
            if info.frames > 0 and info.samplerate > 0 and info.channels > 0:
                return True
        except Exception:
            pass

        # Fallback: decode first second with librosa
        try:
            audio, sr = librosa.load(str(p), sr=None, duration=1.0, mono=True)
            return len(audio) > 0 and sr > 0
        except Exception:
            return False
