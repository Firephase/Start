"""
Audio Enhancement Module
========================
Provides source separation (Demucs) and noise reduction (DeepFilterNet)
for preprocessing amateur vocal recordings before further analysis or synthesis.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import torch
import torchaudio
import torchaudio.transforms as T

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy imports – these heavyweight libraries are only imported when the class
# is first instantiated so that importing this module alone stays cheap.
# ---------------------------------------------------------------------------

def _import_demucs():
    try:
        from demucs.pretrained import get_model
        from demucs.apply import apply_model
        return get_model, apply_model
    except ImportError as exc:
        raise ImportError(
            "demucs is required for source separation. "
            "Install it with: pip install demucs"
        ) from exc


def _import_deepfilternet():
    try:
        from df.enhance import enhance, init_df
        return enhance, init_df
    except ImportError as exc:
        raise ImportError(
            "deepfilternet (df) is required for noise reduction. "
            "Install it with: pip install deepfilternet"
        ) from exc


def _import_pyloudnorm():
    try:
        import pyloudnorm as pyln
        return pyln
    except ImportError as exc:
        raise ImportError(
            "pyloudnorm is required for LUFS normalization. "
            "Install it with: pip install pyloudnorm"
        ) from exc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_SR: int = 44_100
DEMUCS_MODEL: str = "htdemucs_ft"


class AudioEnhancer:
    """
    End-to-end audio enhancement pipeline.

    Steps
    -----
    1. Denoise with DeepFilterNet (removes room noise, mic hiss, etc.)
    2. Separate vocals from accompaniment using Demucs (htdemucs_ft).
    3. Optionally normalise loudness to a target LUFS value.

    Parameters
    ----------
    device : str
        PyTorch device string, e.g. ``'cuda'``, ``'cpu'``, or ``'mps'``.
    """

    def __init__(self, device: str = "cuda") -> None:
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available – falling back to CPU.")
            device = "cpu"
        self.device = torch.device(device)

        logger.info("Initialising AudioEnhancer on device=%s", self.device)

        # --- Demucs ---
        get_model, self._apply_model = _import_demucs()
        self._demucs = get_model(DEMUCS_MODEL)
        self._demucs.to(self.device)
        self._demucs.eval()
        logger.info("Loaded Demucs model: %s", DEMUCS_MODEL)

        # --- DeepFilterNet ---
        enhance_fn, init_df = _import_deepfilternet()
        self._df_enhance = enhance_fn
        self._df_model, self._df_state, _ = init_df()
        logger.info("Loaded DeepFilterNet model (sr=%d)", self._df_state.sr())

        # --- pyloudnorm ---
        self._pyln = _import_pyloudnorm()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enhance(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Full enhancement pipeline: denoise → separate vocals → return vocals.

        Parameters
        ----------
        audio : np.ndarray
            Input waveform, shape ``(samples,)`` (mono) or ``(2, samples)``
            (stereo, channels-first).
        sr : int
            Sample rate of *audio*.

        Returns
        -------
        np.ndarray
            Enhanced vocal track resampled to 44 100 Hz, shape ``(samples,)``.
        """
        denoised = self.denoise(audio, sr)
        vocals, _ = self.separate_vocals(denoised, TARGET_SR)
        return vocals

    def separate_vocals(
        self, audio: np.ndarray, sr: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Separate vocals from accompaniment using Demucs ``htdemucs_ft``.

        Parameters
        ----------
        audio : np.ndarray
            Waveform at any sample rate; resampled internally to 44 100 Hz.
        sr : int
            Sample rate of *audio*.

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            ``(vocals, accompaniment)`` – both at 44 100 Hz, mono, float32.
        """
        tensor = self._to_stereo_tensor(audio, sr, target_sr=TARGET_SR)
        # Demucs expects shape (batch, channels, samples)
        tensor = tensor.unsqueeze(0).to(self.device)

        with torch.no_grad():
            sources = self._apply_model(
                self._demucs,
                tensor,
                device=self.device,
                shifts=1,
                split=True,
                overlap=0.25,
                progress=False,
                num_workers=0,
            )
        # sources: (batch=1, n_sources, channels, samples)
        sources = sources.squeeze(0)  # (n_sources, channels, samples)

        source_names: list[str] = list(self._demucs.sources)
        vocal_idx = source_names.index("vocals")
        other_idxs = [i for i in range(len(source_names)) if i != vocal_idx]

        vocals_stereo = sources[vocal_idx]                        # (2, samples)
        accompaniment_stereo = sources[other_idxs].sum(dim=0)    # (2, samples)

        vocals = self._to_mono_numpy(vocals_stereo)
        accompaniment = self._to_mono_numpy(accompaniment_stereo)

        return vocals, accompaniment

    def denoise(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Apply DeepFilterNet noise reduction.

        The model runs at its own internal sample rate (typically 48 000 Hz).
        Input is resampled to that rate before processing and resampled back
        to ``TARGET_SR`` (44 100 Hz) afterwards.

        Parameters
        ----------
        audio : np.ndarray
            Input waveform (mono or stereo, any sample rate).
        sr : int
            Sample rate of *audio*.

        Returns
        -------
        np.ndarray
            Denoised mono waveform at 44 100 Hz, float32.
        """
        df_sr: int = self._df_state.sr()

        mono = self._ensure_mono(audio)
        tensor = torch.from_numpy(mono.astype(np.float32))

        if sr != df_sr:
            resample_in = T.Resample(orig_freq=sr, new_freq=df_sr)
            tensor = resample_in(tensor.unsqueeze(0)).squeeze(0)

        # DF enhance expects (channels, samples)
        tensor_2d = tensor.unsqueeze(0)
        enhanced = self._df_enhance(self._df_model, self._df_state, tensor_2d)
        enhanced = enhanced.squeeze(0)  # (samples,)

        if df_sr != TARGET_SR:
            resample_out = T.Resample(orig_freq=df_sr, new_freq=TARGET_SR)
            enhanced = resample_out(enhanced.unsqueeze(0)).squeeze(0)

        return enhanced.numpy().astype(np.float32)

    def normalize(
        self, audio: np.ndarray, target_lufs: float = -14.0
    ) -> np.ndarray:
        """
        Loudness-normalise *audio* to *target_lufs* LUFS (ITU-R BS.1770-4).

        Parameters
        ----------
        audio : np.ndarray
            Mono waveform at 44 100 Hz, float32.
        target_lufs : float
            Target integrated loudness in LUFS (default: -14.0 dB LUFS,
            the Spotify streaming standard).

        Returns
        -------
        np.ndarray
            Loudness-normalised, hard-clipped waveform, float32.
        """
        pyln = self._pyln
        meter = pyln.Meter(TARGET_SR)  # BS.1770 meter

        audio_f64 = audio.astype(np.float64)
        loudness = meter.integrated_loudness(audio_f64)

        if not np.isfinite(loudness):
            logger.warning(
                "Could not measure integrated loudness (signal may be silence). "
                "Skipping normalisation."
            )
            return audio

        normalised = pyln.normalize.loudness(audio_f64, loudness, target_lufs)
        normalised = np.clip(normalised, -1.0, 1.0)
        return normalised.astype(np.float32)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_mono(self, audio: np.ndarray) -> np.ndarray:
        """Convert any audio array shape to mono float32."""
        audio = audio.astype(np.float32)
        if audio.ndim == 1:
            return audio
        if audio.ndim == 2:
            # Distinguish (channels, samples) vs (samples, channels) by
            # convention: channels axis is usually ≤ 8.
            if audio.shape[0] <= 8:
                return audio.mean(axis=0)
            return audio.mean(axis=1)
        raise ValueError(
            f"Unsupported audio shape {audio.shape}. "
            "Expected 1-D (samples,) or 2-D (channels, samples)."
        )

    def _to_stereo_tensor(
        self, audio: np.ndarray, sr: int, target_sr: int
    ) -> torch.Tensor:
        """
        Return a stereo ``(2, samples)`` float32 tensor at *target_sr*.

        Handles mono ``(samples,)``, channels-first ``(C, samples)``, and
        channels-last ``(samples, C)`` inputs.
        """
        audio = audio.astype(np.float32)

        if audio.ndim == 1:
            stereo = np.stack([audio, audio], axis=0)
        elif audio.ndim == 2:
            if audio.shape[0] <= 8:
                # channels-first
                if audio.shape[0] == 1:
                    stereo = np.concatenate([audio, audio], axis=0)
                else:
                    stereo = audio[:2]
            else:
                # channels-last → transpose
                tmp = audio.T
                if tmp.shape[0] == 1:
                    stereo = np.concatenate([tmp, tmp], axis=0)
                else:
                    stereo = tmp[:2]
        else:
            raise ValueError(f"Unsupported audio shape: {audio.shape}")

        tensor = torch.from_numpy(stereo)   # (2, samples)

        if sr != target_sr:
            resample = T.Resample(orig_freq=sr, new_freq=target_sr)
            tensor = resample(tensor)

        return tensor

    @staticmethod
    def _to_mono_numpy(stereo: torch.Tensor) -> np.ndarray:
        """Average stereo tensor ``(2, samples)`` to mono numpy float32."""
        return stereo.mean(dim=0).cpu().numpy().astype(np.float32)
