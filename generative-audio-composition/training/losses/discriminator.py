"""
HiFi-GAN style multi-period and multi-scale discriminators.

Reference: Kong et al., "HiFi-GAN: Generative Adversarial Networks for
Efficient and High Fidelity Speech Synthesis" (NeurIPS 2020).
"""

from typing import List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch.nn.utils import weight_norm, spectral_norm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_padding(kernel_size: int, dilation: int = 1) -> int:
    return (kernel_size * dilation - dilation) // 2


# ---------------------------------------------------------------------------
# Period Discriminator
# ---------------------------------------------------------------------------

class PeriodDiscriminator(nn.Module):
    """
    Single-period sub-discriminator operating on reshaped 2-D representations.

    The waveform is folded into a (period, T//period) grid and processed by
    2-D convolutions, capturing periodic patterns at the given period.

    Args:
        period: The period to fold the waveform by.
        kernel_size: Kernel size for convolutions.
        stride: Stride for the first four conv layers.
        use_spectral_norm: Use spectral normalization instead of weight norm.
    """

    def __init__(
        self,
        period: int,
        kernel_size: int = 5,
        stride: int = 3,
        use_spectral_norm: bool = False,
    ) -> None:
        super().__init__()
        self.period = period
        norm = spectral_norm if use_spectral_norm else weight_norm

        channels = [1, 32, 128, 512, 1024, 1024]
        self.convs = nn.ModuleList()
        for i in range(len(channels) - 1):
            s = stride if i < 4 else 1
            self.convs.append(
                norm(
                    nn.Conv2d(
                        channels[i],
                        channels[i + 1],
                        kernel_size=(kernel_size, 1),
                        stride=(s, 1),
                        padding=(_get_padding(kernel_size, 1), 0),
                    )
                )
            )
        self.conv_post = norm(
            nn.Conv2d(1024, 1, kernel_size=(3, 1), stride=1, padding=(1, 0))
        )

    def forward(self, x: Tensor) -> Tuple[Tensor, List[Tensor]]:
        """
        Args:
            x: Waveform tensor of shape (B, 1, T) or (B, T).

        Returns:
            (logits, feature_maps) where logits has shape (B, 1, T', 1)
            flattened to (B, T') and feature_maps is a list of intermediate activations.
        """
        if x.dim() == 2:
            x = x.unsqueeze(1)  # (B, 1, T)

        B, C, T = x.shape
        # Pad to make T divisible by period
        if T % self.period != 0:
            n_pad = self.period - (T % self.period)
            x = F.pad(x, (0, n_pad), "reflect")
            T = T + n_pad

        x = x.view(B, C, T // self.period, self.period)  # (B, 1, T/p, p)

        fmaps: List[Tensor] = []
        for conv in self.convs:
            x = conv(x)
            x = F.leaky_relu(x, 0.1)
            fmaps.append(x)

        x = self.conv_post(x)
        fmaps.append(x)
        x = torch.flatten(x, 1, -1)  # (B, *)
        return x, fmaps


class MultiPeriodDiscriminator(nn.Module):
    """
    Multi-period discriminator combining five period sub-discriminators.

    Uses periods [2, 3, 5, 7, 11] as in the original HiFi-GAN paper.

    Args:
        periods: Periods for each sub-discriminator.
        use_spectral_norm: Use spectral normalization.
    """

    def __init__(
        self,
        periods: List[int] = (2, 3, 5, 7, 11),
        use_spectral_norm: bool = False,
    ) -> None:
        super().__init__()
        self.discriminators = nn.ModuleList(
            [PeriodDiscriminator(p, use_spectral_norm=use_spectral_norm) for p in periods]
        )

    def forward(
        self,
        y: Tensor,
        y_hat: Tensor,
    ) -> Tuple[List[Tensor], List[Tensor], List[List[Tensor]], List[List[Tensor]]]:
        """
        Args:
            y: Real waveform (B, 1, T) or (B, T).
            y_hat: Generated waveform (B, 1, T) or (B, T).

        Returns:
            (real_logits, gen_logits, real_fmaps, gen_fmaps)
        """
        real_logits, gen_logits = [], []
        real_fmaps, gen_fmaps = [], []
        for d in self.discriminators:
            rl, rfm = d(y)
            gl, gfm = d(y_hat)
            real_logits.append(rl)
            gen_logits.append(gl)
            real_fmaps.append(rfm)
            gen_fmaps.append(gfm)
        return real_logits, gen_logits, real_fmaps, gen_fmaps


# ---------------------------------------------------------------------------
# Scale Discriminator
# ---------------------------------------------------------------------------

class ScaleDiscriminator(nn.Module):
    """
    Single-scale waveform discriminator using 1-D convolutions.

    Args:
        use_spectral_norm: If True, use spectral normalization (recommended for
                           the first sub-discriminator of the MSD).
    """

    def __init__(self, use_spectral_norm: bool = False) -> None:
        super().__init__()
        norm = spectral_norm if use_spectral_norm else weight_norm

        self.convs = nn.ModuleList(
            [
                norm(nn.Conv1d(1, 128, 15, 1, padding=7)),
                norm(nn.Conv1d(128, 128, 41, 2, groups=4, padding=20)),
                norm(nn.Conv1d(128, 256, 41, 2, groups=16, padding=20)),
                norm(nn.Conv1d(256, 512, 41, 4, groups=16, padding=20)),
                norm(nn.Conv1d(512, 1024, 41, 4, groups=16, padding=20)),
                norm(nn.Conv1d(1024, 1024, 41, 1, groups=16, padding=20)),
                norm(nn.Conv1d(1024, 1024, 5, 1, padding=2)),
            ]
        )
        self.conv_post = norm(nn.Conv1d(1024, 1, 3, 1, padding=1))

    def forward(self, x: Tensor) -> Tuple[Tensor, List[Tensor]]:
        """
        Args:
            x: (B, 1, T) or (B, T).

        Returns:
            (logits (B, 1, T'), feature_maps)
        """
        if x.dim() == 2:
            x = x.unsqueeze(1)

        fmaps: List[Tensor] = []
        for conv in self.convs:
            x = conv(x)
            x = F.leaky_relu(x, 0.1)
            fmaps.append(x)

        x = self.conv_post(x)
        fmaps.append(x)
        x = torch.flatten(x, 1, -1)
        return x, fmaps


class MultiScaleDiscriminator(nn.Module):
    """
    Multi-scale discriminator operating on raw waveform and 2x/4x downsampled versions.

    Uses average pooling to produce multiple input resolutions.

    Args:
        num_scales: Number of scales (default 3 as in HiFi-GAN).
    """

    def __init__(self, num_scales: int = 3) -> None:
        super().__init__()
        # First discriminator uses spectral norm for training stability
        self.discriminators = nn.ModuleList(
            [ScaleDiscriminator(use_spectral_norm=(i == 0)) for i in range(num_scales)]
        )
        self.pooling = nn.ModuleList(
            [nn.AvgPool1d(4, 2, padding=2) for _ in range(num_scales - 1)]
        )

    def forward(
        self,
        y: Tensor,
        y_hat: Tensor,
    ) -> Tuple[List[Tensor], List[Tensor], List[List[Tensor]], List[List[Tensor]]]:
        """
        Args:
            y: Real waveform (B, 1, T) or (B, T).
            y_hat: Generated waveform (B, 1, T) or (B, T).

        Returns:
            (real_logits, gen_logits, real_fmaps, gen_fmaps)
        """
        if y.dim() == 2:
            y = y.unsqueeze(1)
        if y_hat.dim() == 2:
            y_hat = y_hat.unsqueeze(1)

        real_logits, gen_logits = [], []
        real_fmaps, gen_fmaps = [], []

        for i, d in enumerate(self.discriminators):
            if i > 0:
                y = self.pooling[i - 1](y)
                y_hat = self.pooling[i - 1](y_hat)

            rl, rfm = d(y)
            gl, gfm = d(y_hat)
            real_logits.append(rl)
            gen_logits.append(gl)
            real_fmaps.append(rfm)
            gen_fmaps.append(gfm)

        return real_logits, gen_logits, real_fmaps, gen_fmaps


# ---------------------------------------------------------------------------
# Loss functions
# ---------------------------------------------------------------------------

def discriminator_loss(
    disc_real_outputs: List[Tensor],
    disc_generated_outputs: List[Tensor],
) -> Tuple[Tensor, List[Tensor], List[Tensor]]:
    """
    Hinge / least-squares discriminator loss (LS-GAN formulation as in HiFi-GAN).

    Encourages real outputs towards +1 and generated outputs towards -1.

    Args:
        disc_real_outputs: List of real-audio discriminator logits (one per sub-disc).
        disc_generated_outputs: List of generated-audio discriminator logits.

    Returns:
        (total_loss, real_losses, gen_losses)
        - total_loss: Scalar sum over all sub-discriminators.
        - real_losses: Per-sub-discriminator real loss values.
        - gen_losses: Per-sub-discriminator generated loss values.
    """
    real_losses: List[Tensor] = []
    gen_losses: List[Tensor] = []
    total = torch.zeros(1, device=disc_real_outputs[0].device)

    for dr, dg in zip(disc_real_outputs, disc_generated_outputs):
        r_loss = torch.mean((1.0 - dr) ** 2)
        g_loss = torch.mean(dg ** 2)
        real_losses.append(r_loss)
        gen_losses.append(g_loss)
        total = total + r_loss + g_loss

    return total.squeeze(), real_losses, gen_losses


def generator_loss(
    disc_outputs: List[Tensor],
) -> Tuple[Tensor, List[Tensor]]:
    """
    Generator adversarial loss (LS-GAN).

    Encourages the generator to produce outputs that the discriminator
    classifies as real (+1).

    Args:
        disc_outputs: List of discriminator logits on generated audio.

    Returns:
        (total_loss, per_discriminator_losses)
    """
    per_disc_losses: List[Tensor] = []
    total = torch.zeros(1, device=disc_outputs[0].device)

    for dg in disc_outputs:
        loss = torch.mean((1.0 - dg) ** 2)
        per_disc_losses.append(loss)
        total = total + loss

    return total.squeeze(), per_disc_losses


def feature_loss(
    fmap_r: List[List[Tensor]],
    fmap_g: List[List[Tensor]],
) -> Tensor:
    """
    Feature matching loss between intermediate discriminator activations.

    Minimizes the mean absolute difference between real and generated feature
    maps at every layer of every sub-discriminator.

    Args:
        fmap_r: Real feature maps, shape: [num_discs][num_layers] -> Tensor.
        fmap_g: Generated feature maps, same structure.

    Returns:
        Scalar feature matching loss.
    """
    loss = torch.zeros(1, device=fmap_r[0][0].device)

    for fm_r_disc, fm_g_disc in zip(fmap_r, fmap_g):
        for fr, fg in zip(fm_r_disc, fm_g_disc):
            loss = loss + F.l1_loss(fr, fg.detach())

    return loss.squeeze()
