"""
Mel spectrogram reconstruction losses for audio generation models.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchaudio
from typing import List, Optional


class MelLoss(nn.Module):
    """
    Combined L1 + L2 mel spectrogram reconstruction loss with log compression.

    Computes loss in both linear and log-compressed (dB) mel domains,
    then combines them with configurable weights.

    Args:
        sample_rate: Audio sample rate in Hz.
        n_fft: FFT window size.
        hop_length: Hop size between STFT frames.
        win_length: Window length for STFT (defaults to n_fft).
        n_mels: Number of mel filter banks.
        f_min: Minimum frequency for mel filterbank.
        f_max: Maximum frequency for mel filterbank.
        l1_weight: Weight for L1 loss component.
        l2_weight: Weight for L2 loss component.
        log_weight: Weight for loss in log domain vs linear domain.
        eps: Small constant to avoid log(0).
    """

    def __init__(
        self,
        sample_rate: int = 22050,
        n_fft: int = 1024,
        hop_length: int = 256,
        win_length: Optional[int] = None,
        n_mels: int = 80,
        f_min: float = 0.0,
        f_max: Optional[float] = None,
        l1_weight: float = 1.0,
        l2_weight: float = 1.0,
        log_weight: float = 1.0,
        eps: float = 1e-5,
    ) -> None:
        super().__init__()
        self.l1_weight = l1_weight
        self.l2_weight = l2_weight
        self.log_weight = log_weight
        self.eps = eps

        self.mel_transform = torchaudio.transforms.MelSpectrogram(
            sample_rate=sample_rate,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=win_length or n_fft,
            n_mels=n_mels,
            f_min=f_min,
            f_max=f_max,
            power=2.0,
            normalized=False,
        )

    def _to_mel(self, waveform: torch.Tensor) -> torch.Tensor:
        # waveform: (..., T) -> (..., n_mels, frames)
        return self.mel_transform(waveform)

    def _log_mel(self, mel: torch.Tensor) -> torch.Tensor:
        return torch.log(mel.clamp(min=self.eps))

    def forward(
        self,
        predicted: torch.Tensor,
        target: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            predicted: Predicted waveform or mel spectrogram.
                       Shape: (B, T) for waveform or (B, n_mels, frames) for mel.
            target: Ground-truth waveform or mel spectrogram, same shape as predicted.

        Returns:
            Scalar loss tensor.
        """
        # If inputs are raw waveforms, convert to mel first
        if predicted.dim() == 2:
            mel_pred = self._to_mel(predicted)
            mel_tgt = self._to_mel(target)
        else:
            mel_pred = predicted
            mel_tgt = target

        # Align time dimension (may differ by 1 frame due to padding)
        min_frames = min(mel_pred.size(-1), mel_tgt.size(-1))
        mel_pred = mel_pred[..., :min_frames]
        mel_tgt = mel_tgt[..., :min_frames]

        # Linear domain losses
        l1_lin = F.l1_loss(mel_pred, mel_tgt)
        l2_lin = F.mse_loss(mel_pred, mel_tgt)

        # Log-compressed domain losses
        log_pred = self._log_mel(mel_pred)
        log_tgt = self._log_mel(mel_tgt)
        l1_log = F.l1_loss(log_pred, log_tgt)
        l2_log = F.mse_loss(log_pred, log_tgt)

        loss = (
            self.l1_weight * l1_lin
            + self.l2_weight * l2_lin
            + self.log_weight * (self.l1_weight * l1_log + self.l2_weight * l2_log)
        )
        return loss


class MultiScaleMelLoss(nn.Module):
    """
    Multi-scale mel spectrogram loss using multiple FFT sizes.

    Computes mel losses at each of [512, 1024, 2048] FFT sizes and
    averages them, capturing different time-frequency resolutions.

    Args:
        sample_rate: Audio sample rate in Hz.
        fft_sizes: List of FFT window sizes to use.
        hop_lengths: Hop sizes corresponding to each FFT size.
        win_lengths: Window lengths; defaults to each FFT size.
        n_mels: Number of mel filter banks.
        f_min: Minimum frequency.
        f_max: Maximum frequency.
        l1_weight: Weight for L1 component in each scale.
        l2_weight: Weight for L2 component in each scale.
        log_weight: Weight for log-domain losses at each scale.
        eps: Numerical stability constant.
    """

    def __init__(
        self,
        sample_rate: int = 22050,
        fft_sizes: List[int] = (512, 1024, 2048),
        hop_lengths: Optional[List[int]] = None,
        win_lengths: Optional[List[int]] = None,
        n_mels: int = 80,
        f_min: float = 0.0,
        f_max: Optional[float] = None,
        l1_weight: float = 1.0,
        l2_weight: float = 1.0,
        log_weight: float = 1.0,
        eps: float = 1e-5,
    ) -> None:
        super().__init__()
        if hop_lengths is None:
            hop_lengths = [s // 4 for s in fft_sizes]
        if win_lengths is None:
            win_lengths = list(fft_sizes)

        assert len(fft_sizes) == len(hop_lengths) == len(win_lengths)

        self.losses = nn.ModuleList(
            [
                MelLoss(
                    sample_rate=sample_rate,
                    n_fft=n_fft,
                    hop_length=hop,
                    win_length=win,
                    n_mels=n_mels,
                    f_min=f_min,
                    f_max=f_max,
                    l1_weight=l1_weight,
                    l2_weight=l2_weight,
                    log_weight=log_weight,
                    eps=eps,
                )
                for n_fft, hop, win in zip(fft_sizes, hop_lengths, win_lengths)
            ]
        )

    def forward(
        self,
        predicted: torch.Tensor,
        target: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            predicted: Predicted waveform, shape (B, T).
            target: Ground-truth waveform, shape (B, T).

        Returns:
            Scalar loss averaged across all scales.
        """
        total = torch.zeros(1, device=predicted.device, dtype=predicted.dtype)
        for loss_fn in self.losses:
            total = total + loss_fn(predicted, target)
        return total / len(self.losses)


class SpectralConvergenceLoss(nn.Module):
    """
    Spectral convergence loss.

    Measures the Frobenius-norm ratio between the difference and ground-truth
    magnitude spectrograms, encouraging the predicted spectrogram to converge
    to the target's energy distribution.

    Reference: Arik et al., "Fast Spectrogram Inversion Using Multi-Head
    Convolutional Neural Networks" (2018).

    Args:
        n_fft: FFT size.
        hop_length: Hop size.
        win_length: Window length (defaults to n_fft).
        eps: Numerical stability constant.
    """

    def __init__(
        self,
        n_fft: int = 1024,
        hop_length: int = 256,
        win_length: Optional[int] = None,
        eps: float = 1e-8,
    ) -> None:
        super().__init__()
        self.n_fft = n_fft
        self.hop_length = hop_length
        self.win_length = win_length or n_fft
        self.eps = eps

        self.register_buffer(
            "window", torch.hann_window(self.win_length)
        )

    def _stft_magnitude(self, audio: torch.Tensor) -> torch.Tensor:
        """
        Compute STFT magnitude for a batch of waveforms.

        Args:
            audio: (B, T)

        Returns:
            Magnitude spectrogram: (B, n_fft//2+1, frames)
        """
        B, T = audio.shape
        # Flatten batch for torch.stft
        stft = torch.stft(
            audio.reshape(B, T),
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            win_length=self.win_length,
            window=self.window,
            return_complex=True,
        )
        return stft.abs()  # (B, freq, frames)

    def forward(
        self,
        predicted: torch.Tensor,
        target: torch.Tensor,
    ) -> torch.Tensor:
        """
        Args:
            predicted: Predicted waveform (B, T).
            target: Target waveform (B, T).

        Returns:
            Scalar spectral convergence loss.
        """
        mag_pred = self._stft_magnitude(predicted)
        mag_tgt = self._stft_magnitude(target)

        # Align frames
        min_f = min(mag_pred.size(-1), mag_tgt.size(-1))
        mag_pred = mag_pred[..., :min_f]
        mag_tgt = mag_tgt[..., :min_f]

        # Frobenius norm over (freq, frames) per batch element
        diff_norm = torch.norm(mag_tgt - mag_pred, p="fro", dim=(-2, -1))
        tgt_norm = torch.norm(mag_tgt, p="fro", dim=(-2, -1))

        loss = (diff_norm / (tgt_norm + self.eps)).mean()
        return loss
