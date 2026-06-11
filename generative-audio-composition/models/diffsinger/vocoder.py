"""
HiFi-GAN vocoder for DiffSinger.

Converts mel-spectrograms (80-bin, 22050 Hz or 44100 Hz) to raw waveforms.

Architecture follows the HiFi-GAN V1 generator (Kong et al., 2020):
  - Transposed convolution upsampling stack with strides [8, 8, 4, 2]
    (total upsampling factor = 512, suitable for 80-frame / 256-hop mels).
  - Multi-Receptive Field (MRF) fusion block at each scale, each containing
    three residual blocks with different dilation patterns.
  - Leaky ReLU activations (slope 0.1) throughout.

Classes
-------
ResBlock       — single dilated residual block (one kernel size, one dilation set).
MRFBlock       — three parallel ResBlocks fused by summation.
HiFiGAN        — full generator with transposed conv + MRF stack.
"""

import os
from typing import List, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor


LRELU_SLOPE: float = 0.1


def _init_weights(m: nn.Module) -> None:
    """Xavier-uniform initialisation for Conv layers."""
    if isinstance(m, (nn.Conv1d, nn.ConvTranspose1d)):
        nn.init.xavier_uniform_(m.weight)
        if m.bias is not None:
            nn.init.zeros_(m.bias)


# ---------------------------------------------------------------------------
# Residual Block
# ---------------------------------------------------------------------------

class ResBlock(nn.Module):
    """
    Dilated residual block as used inside each MRF block.

    For a given *kernel_size* and list of *dilations*, the block applies
    ``len(dilations)`` sequential (conv → leaky_relu → conv → leaky_relu)
    sub-blocks with a skip connection around each sub-block.

    Args:
        channels:   Number of input / output channels.
        kernel_size: Kernel size for all dilated convolutions (default 3).
        dilations:  List of dilation values; one sub-block per entry.
    """

    def __init__(
        self,
        channels: int,
        kernel_size: int = 3,
        dilations: List[int] = (1, 3, 5),
    ) -> None:
        super().__init__()
        self.convs1 = nn.ModuleList()
        self.convs2 = nn.ModuleList()
        for d in dilations:
            p1 = (kernel_size - 1) * d // 2
            self.convs1.append(
                nn.Conv1d(channels, channels, kernel_size, dilation=d, padding=p1)
            )
            self.convs2.append(
                nn.Conv1d(channels, channels, kernel_size, dilation=1, padding=(kernel_size - 1) // 2)
            )
        self.apply(_init_weights)

    def forward(self, x: Tensor) -> Tensor:
        """(B, C, T) -> (B, C, T)"""
        for c1, c2 in zip(self.convs1, self.convs2):
            xt = F.leaky_relu(x, LRELU_SLOPE)
            xt = c1(xt)
            xt = F.leaky_relu(xt, LRELU_SLOPE)
            xt = c2(xt)
            x = x + xt
        return x


# ---------------------------------------------------------------------------
# Multi-Receptive Field Block
# ---------------------------------------------------------------------------

class MRFBlock(nn.Module):
    """
    Multi-Receptive Field fusion of three ResBlocks with different kernel
    sizes and dilation patterns, as in HiFi-GAN V1.

    Args:
        channels:     Channel width (same for all ResBlocks).
        kernel_sizes: Tuple of three kernel sizes (default (3, 7, 11)).
        dilations:    Tuple of three dilation lists corresponding to each
                      kernel size (default HiFi-GAN V1 values).
    """

    def __init__(
        self,
        channels: int,
        kernel_sizes: tuple = (3, 7, 11),
        dilations: tuple = (
            (1, 3, 5),   # for kernel 3
            (1, 3, 5),   # for kernel 7
            (1, 3, 5),   # for kernel 11
        ),
    ) -> None:
        super().__init__()
        assert len(kernel_sizes) == len(dilations)
        self.res_blocks = nn.ModuleList([
            ResBlock(channels, ks, ds)
            for ks, ds in zip(kernel_sizes, dilations)
        ])
        self.num_blocks = len(self.res_blocks)

    def forward(self, x: Tensor) -> Tensor:
        """(B, C, T) -> (B, C, T)"""
        out = None
        for block in self.res_blocks:
            y = block(x)
            out = y if out is None else out + y
        return out / self.num_blocks


# ---------------------------------------------------------------------------
# HiFi-GAN Generator
# ---------------------------------------------------------------------------

class HiFiGAN(nn.Module):
    """
    HiFi-GAN V1 generator.

    Upsampling stack:  strides [8, 8, 4, 2] → total × 512.
    Input:  (B, n_mels, T_mel)
    Output: (B, 1, T_wave)  — waveform in [-1, 1]

    For an 80-bin mel with hop 512 at 22050 Hz the generator reproduces
    waveforms at 22050 Hz.  DiffSinger targets 44100 Hz; use hop 1024 for
    mels or resample the waveform externally.

    Args:
        n_mels:           Input mel channels (default 80).
        upsample_rates:   Transposed conv strides (default [8, 8, 4, 2]).
        upsample_kernel:  Kernel sizes for transposed convs (must be 2× rates).
        upsample_init_ch: Channel width after first conv (halved at each scale).
        resblock_kernels: Kernel sizes for MRF ResBlocks.
        resblock_dilations: Dilation patterns for MRF ResBlocks.
    """

    def __init__(
        self,
        n_mels: int = 80,
        upsample_rates: List[int] = None,
        upsample_kernel: List[int] = None,
        upsample_init_ch: int = 512,
        resblock_kernels: tuple = (3, 7, 11),
        resblock_dilations: tuple = (
            (1, 3, 5),
            (1, 3, 5),
            (1, 3, 5),
        ),
    ) -> None:
        super().__init__()

        if upsample_rates is None:
            upsample_rates = [8, 8, 4, 2]
        if upsample_kernel is None:
            upsample_kernel = [16, 16, 8, 4]

        assert len(upsample_rates) == len(upsample_kernel), (
            "upsample_rates and upsample_kernel must have the same length."
        )

        self.num_upsamples = len(upsample_rates)
        self.num_mrf_kernels = len(resblock_kernels)

        # Initial conv: n_mels → upsample_init_ch
        self.conv_pre = nn.Conv1d(n_mels, upsample_init_ch, kernel_size=7, padding=3)

        # Transposed conv upsampling stack
        self.ups = nn.ModuleList()
        self.mrfs = nn.ModuleList()
        ch = upsample_init_ch
        for stride, k in zip(upsample_rates, upsample_kernel):
            padding = (k - stride) // 2
            self.ups.append(
                nn.ConvTranspose1d(ch, ch // 2, kernel_size=k, stride=stride, padding=padding)
            )
            self.mrfs.append(
                MRFBlock(ch // 2, resblock_kernels, resblock_dilations)
            )
            ch = ch // 2

        # Final conv: ch → 1
        self.conv_post = nn.Conv1d(ch, 1, kernel_size=7, padding=3, bias=False)

        self.apply(_init_weights)

    def forward(self, mel: Tensor) -> Tensor:
        """
        Convert a mel-spectrogram to a waveform.

        Args:
            mel: (B, n_mels, T_mel) — normalised mel-spectrogram.

        Returns:
            waveform: (B, 1, T_wave) — values in [-1, 1].
        """
        x = self.conv_pre(mel)                        # (B, init_ch, T_mel)
        for up, mrf in zip(self.ups, self.mrfs):
            x = F.leaky_relu(x, LRELU_SLOPE)
            x = up(x)                                 # upsample
            x = mrf(x)                               # MRF fusion
        x = F.leaky_relu(x, LRELU_SLOPE)
        x = self.conv_post(x)                        # (B, 1, T_wave)
        x = torch.tanh(x)
        return x

    # ------------------------------------------------------------------
    # Checkpoint loading
    # ------------------------------------------------------------------

    @classmethod
    def from_pretrained(cls, path: str, map_location: Optional[str] = None) -> "HiFiGAN":
        """
        Load a HiFiGAN checkpoint saved by ``torch.save``.

        The checkpoint may be either:
          (a) A raw ``state_dict``.
          (b) A dict with keys ``"generator"`` or ``"model_state_dict"``.
          (c) A dict with a ``"config"`` sub-dict and one of the above keys.

        Args:
            path:          Path to the .pt / .pth checkpoint file.
            map_location:  Optional device string (e.g. "cpu").

        Returns:
            Instantiated HiFiGAN with loaded weights (in eval mode).
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"HiFiGAN checkpoint not found: {path}")

        ckpt = torch.load(path, map_location=map_location or "cpu")

        # Extract config if present
        config = ckpt.get("config", {}) if isinstance(ckpt, dict) else {}
        model = cls(
            n_mels=config.get("n_mels", 80),
            upsample_rates=config.get("upsample_rates", None),
            upsample_kernel=config.get("upsample_kernel", None),
            upsample_init_ch=config.get("upsample_init_ch", 512),
            resblock_kernels=tuple(config.get("resblock_kernels", (3, 7, 11))),
            resblock_dilations=tuple(
                tuple(d) for d in config.get("resblock_dilations", ((1, 3, 5), (1, 3, 5), (1, 3, 5)))
            ),
        )

        # Extract state dict
        if isinstance(ckpt, dict):
            state = (
                ckpt.get("generator")
                or ckpt.get("model_state_dict")
                or ckpt.get("state_dict")
                or ckpt
            )
        else:
            state = ckpt

        model.load_state_dict(state, strict=False)
        model.eval()
        return model

    def remove_weight_norm(self) -> None:
        """Remove weight normalisation layers (call before inference for speed)."""
        for layer in self.modules():
            if isinstance(layer, (nn.Conv1d, nn.ConvTranspose1d)):
                try:
                    nn.utils.remove_weight_norm(layer)
                except ValueError:
                    pass
