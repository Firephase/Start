"""
Audio augmentation pipeline for training generative audio models.

All methods return float32 NumPy arrays normalized to approximately [-1, 1].
"""

import logging
import random
from typing import Callable, List, Optional, Tuple, Union

import numpy as np

log = logging.getLogger(__name__)


class AudioAugmenter:
    """
    Randomized audio augmentation pipeline.

    Each augmentation method accepts a float32 NumPy array (mono waveform)
    and a sample rate, and returns an augmented array of the same length and dtype.

    Methods can be called individually or combined via :meth:`augment`, which
    randomly applies a subset of augmentations based on the provided probability.

    Args:
        seed: Optional random seed for reproducibility.
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = np.random.RandomState(seed)
        if seed is not None:
            random.seed(seed)

    # ------------------------------------------------------------------
    # Noise addition
    # ------------------------------------------------------------------

    def add_noise(
        self,
        audio: np.ndarray,
        sr: int,
        snr_db_range: Tuple[float, float] = (10.0, 30.0),
    ) -> np.ndarray:
        """
        Add white Gaussian noise at a randomly chosen SNR.

        Args:
            audio: Mono float32 waveform (T,).
            sr: Sample rate (unused; kept for API consistency).
            snr_db_range: (min_snr, max_snr) in dB. Higher values add less noise.

        Returns:
            Noisy waveform (T,), float32.
        """
        snr_db = self._rng.uniform(*snr_db_range)
        signal_power = np.mean(audio ** 2)
        if signal_power < 1e-10:
            return audio.copy()

        noise_power = signal_power / (10.0 ** (snr_db / 10.0))
        noise = self._rng.randn(*audio.shape).astype(np.float32) * np.sqrt(noise_power)
        return np.clip(audio + noise, -1.0, 1.0)

    # ------------------------------------------------------------------
    # Room reverb
    # ------------------------------------------------------------------

    def add_room_reverb(
        self,
        audio: np.ndarray,
        sr: int,
        rt60_range: Tuple[float, float] = (0.1, 0.8),
        room_dim_range: Tuple[float, float] = (3.0, 10.0),
    ) -> np.ndarray:
        """
        Simulate room acoustics using pyroomacoustics.

        A random shoebox room is generated and an image-source model is used
        to compute the room impulse response (RIR), which is then convolved
        with the audio.

        Falls back to a simple exponential-decay convolution if pyroomacoustics
        is not installed.

        Args:
            audio: Mono float32 waveform (T,).
            sr: Sample rate in Hz.
            rt60_range: (min_rt60, max_rt60) reverb time in seconds.
            room_dim_range: Range for each room dimension in meters.

        Returns:
            Reverberant waveform (T,), float32.
        """
        rt60 = self._rng.uniform(*rt60_range)

        try:
            import pyroomacoustics as pra  # type: ignore

            # Random shoebox room dimensions
            dims = self._rng.uniform(room_dim_range[0], room_dim_range[1], size=3)

            # Compute absorption coefficient from Sabine's formula
            e_absorption, max_order = pra.inverse_sabine(rt60, dims)

            room = pra.ShoeBox(
                dims,
                fs=sr,
                materials=pra.Material(e_absorption),
                max_order=min(max_order, 17),
            )

            # Place source and microphone at random positions
            margin = 0.5
            src_pos = self._rng.uniform(margin, dims - margin)
            mic_pos = self._rng.uniform(margin, dims - margin)

            room.add_source(src_pos, signal=audio)
            mic_array = np.array(mic_pos).reshape(3, 1)
            room.add_microphone(mic_array)

            room.simulate()
            reverb = room.mic_array.signals[0]

            # Trim or pad to original length
            reverb = reverb[: len(audio)]
            if len(reverb) < len(audio):
                reverb = np.pad(reverb, (0, len(audio) - len(reverb)))

            # Normalise to avoid clipping
            peak = np.abs(reverb).max()
            if peak > 0:
                reverb = reverb * (np.abs(audio).max() / peak)

            return reverb.astype(np.float32)

        except ImportError:
            log.debug(
                "pyroomacoustics not installed; using exponential-decay reverb fallback."
            )
            return self._simple_reverb(audio, sr, rt60)

    def _simple_reverb(
        self,
        audio: np.ndarray,
        sr: int,
        rt60: float,
    ) -> np.ndarray:
        """
        Minimal reverb via an exponentially-decaying noise impulse response.
        """
        ir_length = int(rt60 * sr)
        if ir_length < 2:
            return audio.copy()

        t = np.linspace(0, rt60, ir_length)
        decay = np.exp(-6.9 * t / rt60)  # -60 dB at rt60
        noise = self._rng.randn(ir_length).astype(np.float32)
        rir = (noise * decay).astype(np.float32)
        rir /= np.abs(rir).max() + 1e-8

        from scipy.signal import fftconvolve  # type: ignore (optional)
        try:
            reverb = fftconvolve(audio, rir)[: len(audio)]
        except ImportError:
            reverb = np.convolve(audio, rir)[: len(audio)]

        # Normalise
        peak = np.abs(reverb).max()
        if peak > 0:
            reverb = reverb * (np.abs(audio).max() / (peak + 1e-8))

        return reverb.astype(np.float32)

    # ------------------------------------------------------------------
    # Pitch shift
    # ------------------------------------------------------------------

    def pitch_shift(
        self,
        audio: np.ndarray,
        sr: int,
        semitones_range: Tuple[float, float] = (-2.0, 2.0),
    ) -> np.ndarray:
        """
        Pitch-shift audio by a random number of semitones without changing duration.

        Uses librosa's high-quality phase vocoder. Falls back to
        resampling-based pitch shifting if librosa is unavailable.

        Args:
            audio: Mono float32 waveform (T,).
            sr: Sample rate.
            semitones_range: (min, max) shift in semitones.

        Returns:
            Pitch-shifted waveform (T,), float32.
        """
        n_steps = self._rng.uniform(*semitones_range)
        if abs(n_steps) < 0.01:
            return audio.copy()

        try:
            import librosa
            shifted = librosa.effects.pitch_shift(
                audio.astype(np.float32),
                sr=sr,
                n_steps=float(n_steps),
                bins_per_octave=24,
            )
            return shifted.astype(np.float32)
        except ImportError:
            pass

        # Fallback: resample-based (changes duration, so we resample back)
        ratio = 2.0 ** (n_steps / 12.0)
        target_len = int(len(audio) / ratio)
        try:
            from scipy.signal import resample
            stretched = resample(audio, target_len)
            result = resample(stretched, len(audio))
            return result.astype(np.float32)
        except ImportError:
            log.warning("Install librosa or scipy for pitch shifting.")
            return audio.copy()

    # ------------------------------------------------------------------
    # Time stretch
    # ------------------------------------------------------------------

    def time_stretch(
        self,
        audio: np.ndarray,
        sr: int,
        rate_range: Tuple[float, float] = (0.9, 1.1),
    ) -> np.ndarray:
        """
        Time-stretch audio by a random rate without changing pitch.

        Stretched output is trimmed or zero-padded to preserve the
        original sample count so downstream processing stays consistent.

        Args:
            audio: Mono float32 waveform (T,).
            sr: Sample rate (unused here; kept for API consistency).
            rate_range: (min_rate, max_rate). rate < 1 → slower, rate > 1 → faster.

        Returns:
            Time-stretched waveform of same length as input, float32.
        """
        rate = self._rng.uniform(*rate_range)
        if abs(rate - 1.0) < 0.005:
            return audio.copy()

        try:
            import librosa
            stretched = librosa.effects.time_stretch(audio.astype(np.float32), rate=rate)
        except ImportError:
            # Fallback: scipy resample
            try:
                from scipy.signal import resample
                target_len = int(len(audio) / rate)
                stretched = resample(audio, target_len).astype(np.float32)
            except ImportError:
                log.warning("Install librosa or scipy for time stretching.")
                return audio.copy()

        # Restore original length
        original_len = len(audio)
        if len(stretched) >= original_len:
            return stretched[:original_len].astype(np.float32)
        return np.pad(stretched, (0, original_len - len(stretched))).astype(np.float32)

    # ------------------------------------------------------------------
    # Microphone effect
    # ------------------------------------------------------------------

    def apply_microphone_effect(
        self,
        audio: np.ndarray,
        sr: int,
    ) -> np.ndarray:
        """
        Simulate telephone / vintage microphone colouration.

        Applies:
        1. Bandwidth limiting (300 Hz – 3400 Hz high-pass + low-pass for telephone)
           or (80 Hz – 8000 Hz for a vintage studio mic).
        2. A gentle presence boost around 3–5 kHz.
        3. Slight harmonic saturation.

        The specific effect is randomly chosen to vary training data.

        Args:
            audio: Mono float32 waveform (T,).
            sr: Sample rate in Hz.

        Returns:
            Processed waveform (T,), float32.
        """
        try:
            from scipy.signal import butter, sosfilt  # type: ignore
        except ImportError:
            log.warning("scipy is required for microphone effect simulation.")
            return audio.copy()

        effect = self._rng.choice(["telephone", "vintage", "presence"])

        if effect == "telephone":
            # Bandpass: 300 Hz – 3400 Hz (classic PSTN bandwidth)
            lo_hz, hi_hz = 300.0, 3400.0
        elif effect == "vintage":
            # Bandpass: 80 Hz – 8 kHz (old ribbon/dynamic mic)
            lo_hz, hi_hz = 80.0, 8000.0
        else:
            # Presence boost: only high-pass to remove rumble
            lo_hz, hi_hz = 100.0, sr / 2.0 * 0.95

        nyq = sr / 2.0
        lo = max(lo_hz / nyq, 1e-4)
        hi = min(hi_hz / nyq, 0.999)

        if lo < hi:
            sos = butter(4, [lo, hi], btype="bandpass", output="sos")
            processed = sosfilt(sos, audio).astype(np.float32)
        else:
            processed = audio.copy()

        # Presence boost (3 kHz shelf)
        if effect == "presence" and sr > 6000:
            boost_freq = min(3000.0 / nyq, 0.95)
            sos_shelf = butter(2, boost_freq, btype="high", output="sos")
            boost_signal = sosfilt(sos_shelf, processed).astype(np.float32)
            processed = processed + 0.3 * boost_signal

        # Soft saturation (tanh clipping)
        gain = 1.5
        processed = np.tanh(gain * processed) / np.tanh(gain)

        return processed.astype(np.float32)

    # ------------------------------------------------------------------
    # Gain / volume
    # ------------------------------------------------------------------

    def random_gain(
        self,
        audio: np.ndarray,
        sr: int,
        gain_db_range: Tuple[float, float] = (-6.0, 6.0),
    ) -> np.ndarray:
        """
        Apply random gain in dB.

        Args:
            audio: Mono float32 waveform (T,).
            sr: Sample rate (unused).
            gain_db_range: (min_gain, max_gain) in dB.

        Returns:
            Scaled waveform (T,), float32.
        """
        gain_db = self._rng.uniform(*gain_db_range)
        gain_linear = 10.0 ** (gain_db / 20.0)
        return np.clip(audio * gain_linear, -1.0, 1.0).astype(np.float32)

    # ------------------------------------------------------------------
    # Polarity inversion
    # ------------------------------------------------------------------

    def polarity_inversion(
        self,
        audio: np.ndarray,
        sr: int,
    ) -> np.ndarray:
        """
        Flip the polarity of the waveform (multiply by -1).

        This is a zero-cost augmentation that is perceptually transparent
        for most sounds but breaks assumptions that rely on waveform sign.

        Args:
            audio: Mono float32 waveform (T,).
            sr: Sample rate (unused).

        Returns:
            Polarity-inverted waveform (T,), float32.
        """
        return (-audio).astype(np.float32)

    # ------------------------------------------------------------------
    # Composite augmentation
    # ------------------------------------------------------------------

    def augment(
        self,
        audio: np.ndarray,
        sr: int,
        p: float = 0.5,
        augmentations: Optional[List[str]] = None,
    ) -> np.ndarray:
        """
        Randomly apply a subset of augmentations with probability p each.

        Args:
            audio: Mono float32 waveform (T,).
            sr: Sample rate.
            p: Probability of applying each augmentation independently.
               E.g. p=0.5 means each transform is applied ~50% of the time.
            augmentations: Optional list of method names to consider.
                           Defaults to all available augmentations.

        Returns:
            Augmented waveform (T,), float32.

        Example::

            augmenter = AudioAugmenter(seed=0)
            aug_audio = augmenter.augment(audio, sr=22050, p=0.4)

            # Only use noise and pitch shift:
            aug_audio = augmenter.augment(
                audio, sr, p=0.6,
                augmentations=["add_noise", "pitch_shift"]
            )
        """
        if augmentations is None:
            augmentations = [
                "add_noise",
                "add_room_reverb",
                "pitch_shift",
                "time_stretch",
                "apply_microphone_effect",
                "random_gain",
                "polarity_inversion",
            ]

        result = audio.astype(np.float32).copy()

        # Shuffle order for variety
        order = augmentations.copy()
        self._rng.shuffle(order)

        for aug_name in order:
            if self._rng.random() < p:
                method: Optional[Callable] = getattr(self, aug_name, None)
                if method is None:
                    log.warning("Unknown augmentation: %s", aug_name)
                    continue
                try:
                    result = method(result, sr)
                except Exception as exc:
                    log.warning("Augmentation '%s' failed: %s", aug_name, exc)

        return result.astype(np.float32)

    # ------------------------------------------------------------------
    # Batch convenience
    # ------------------------------------------------------------------

    def augment_batch(
        self,
        audios: np.ndarray,
        sr: int,
        p: float = 0.5,
        augmentations: Optional[List[str]] = None,
    ) -> np.ndarray:
        """
        Apply augmentation independently to each sample in a batch.

        Args:
            audios: Float32 array of shape (B, T) or (B, C, T).
                    Multi-channel input is processed channel-by-channel.
            sr: Sample rate.
            p: Per-augmentation application probability.
            augmentations: Subset of augmentation method names to use.

        Returns:
            Augmented batch, same shape as input.
        """
        result = np.empty_like(audios)
        for i in range(audios.shape[0]):
            if audios.ndim == 2:
                result[i] = self.augment(audios[i], sr, p, augmentations)
            else:
                # (C, T)
                for c in range(audios.shape[1]):
                    result[i, c] = self.augment(audios[i, c], sr, p, augmentations)
        return result
