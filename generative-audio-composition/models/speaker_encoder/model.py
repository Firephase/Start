"""
WavLM + ECAPA-TDNN Speaker Encoder
====================================
Combines WavLM-Large contextual representations with an ECAPA-TDNN pooling
head to produce compact, L2-normalised speaker embeddings.

Architecture
------------
  WavLM-Large (24 transformer layers)
    → Weighted sum of layer outputs
    → ECAPA-TDNN head (4 TDNN layers + attentive statistics pooling)
    → Linear projection → L2 normalisation

References
----------
- WavLM: https://arxiv.org/abs/2110.13900
- ECAPA-TDNN: https://arxiv.org/abs/2005.07143
- Res2Net: https://arxiv.org/abs/1904.01169
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)


# =============================================================================
# Squeeze-and-Excitation Block
# =============================================================================


class SEBlock(nn.Module):
    """
    Channel-wise Squeeze-and-Excitation (SE) block.

    Recalibrates channel responses by modelling inter-channel dependencies.
    ``channels`` → squeeze (channels // ratio) → ReLU → excite (channels) → Sigmoid gate.
    """

    def __init__(self, channels: int, ratio: int = 8):
        super().__init__()
        bottleneck = max(channels // ratio, 4)
        self.fc = nn.Sequential(
            nn.Linear(channels, bottleneck),
            nn.ReLU(inplace=True),
            nn.Linear(bottleneck, channels),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        x : (B, C, T)  input feature map
        Returns
        -------
        (B, C, T)  SE-gated output
        """
        # Global average pool over time → (B, C)
        scale = x.mean(dim=-1)          # (B, C)
        scale = self.fc(scale)          # (B, C)
        return x * scale.unsqueeze(-1)  # (B, C, T)


# =============================================================================
# Res2Conv — Res2Net-style multi-scale convolution
# =============================================================================


class Res2Conv(nn.Module):
    """
    Res2Net-style hierarchical multi-scale convolution.

    Splits the channel dimension into ``scale`` sub-groups; each sub-group
    is processed by a 1-D convolution and the outputs are accumulated
    hierarchically, providing rich multi-scale temporal representations
    at a low parameter cost.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 3,
        dilation: int = 1,
        scale: int = 8,
    ):
        super().__init__()
        assert in_channels % scale == 0, "in_channels must be divisible by scale"
        assert out_channels % scale == 0, "out_channels must be divisible by scale"

        self.scale = scale
        self.width = in_channels // scale   # channels per sub-group
        padding = (kernel_size - 1) * dilation // 2

        # One conv per sub-group (skip the first — it's passed through directly)
        self.convs = nn.ModuleList(
            [
                nn.Conv1d(
                    self.width,
                    self.width,
                    kernel_size=kernel_size,
                    dilation=dilation,
                    padding=padding,
                )
                for _ in range(scale - 1)
            ]
        )
        self.bns = nn.ModuleList([nn.BatchNorm1d(self.width) for _ in range(scale - 1)])

        # 1x1 projection to merge back to out_channels
        self.proj = nn.Conv1d(in_channels, out_channels, kernel_size=1)
        self.bn_proj = nn.BatchNorm1d(out_channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        x : (B, C, T)
        Returns
        -------
        (B, out_channels, T)
        """
        sub = torch.chunk(x, self.scale, dim=1)  # list of (B, width, T)
        outputs = []
        y = None
        for i, conv in enumerate(self.convs):
            if i == 0 or y is None:
                y = conv(sub[i])
            else:
                y = conv(sub[i] + y)
            y = F.relu(self.bns[i](y), inplace=True)
            outputs.append(y)
        # First sub-group is passed through unchanged
        outputs.insert(0, sub[0])
        out = torch.cat(outputs, dim=1)   # (B, C, T)
        return F.relu(self.bn_proj(self.proj(out)), inplace=True)


# =============================================================================
# ECAPA-TDNN Head
# =============================================================================


class _TDNNLayer(nn.Module):
    """
    Single TDNN layer: Conv1d + BN + ReLU + SE.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int,
        dilation: int,
        use_res2: bool = False,
        res2_scale: int = 8,
    ):
        super().__init__()
        self.use_res2 = use_res2

        if use_res2:
            self.conv = Res2Conv(
                in_channels,
                out_channels,
                kernel_size=kernel_size,
                dilation=dilation,
                scale=res2_scale,
            )
        else:
            padding = (kernel_size - 1) * dilation // 2
            self.conv = nn.Sequential(
                nn.Conv1d(in_channels, out_channels, kernel_size, dilation=dilation, padding=padding),
                nn.BatchNorm1d(out_channels),
                nn.ReLU(inplace=True),
            )

        self.se = SEBlock(out_channels)
        self.residual = (
            nn.Conv1d(in_channels, out_channels, 1) if in_channels != out_channels else nn.Identity()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.residual(x)
        out = self.conv(x)
        out = self.se(out)
        return F.relu(out + residual, inplace=True)


class ECAPA_TDNN_Head(nn.Module):
    """
    ECAPA-TDNN pooling head.

    Processes WavLM frame-level features through 4 TDNN layers with
    progressively larger dilations, applies multi-scale feature aggregation,
    then uses attentive statistics pooling to produce a single utterance-level
    embedding vector.

    Input  : (B, T, input_dim)   — WavLM frame features
    Output : (B, emb_dim)        — speaker embedding (before L2 norm)
    """

    def __init__(
        self,
        input_dim: int = 1024,
        channels: int = 512,
        emb_dim: int = 192,
    ):
        super().__init__()
        self.input_dim = input_dim
        self.channels  = channels
        self.emb_dim   = emb_dim

        # Input projection: (B, T, input_dim) → (B, channels, T)
        self.input_proj = nn.Sequential(
            nn.Conv1d(input_dim, channels, kernel_size=5, padding=2),
            nn.BatchNorm1d(channels),
            nn.ReLU(inplace=True),
        )

        # 4 TDNN layers (layers 2–4 use Res2Conv)
        self.layer1 = _TDNNLayer(channels, channels, kernel_size=3, dilation=2)
        self.layer2 = _TDNNLayer(channels, channels, kernel_size=3, dilation=3, use_res2=True)
        self.layer3 = _TDNNLayer(channels, channels, kernel_size=3, dilation=4, use_res2=True)
        self.layer4 = _TDNNLayer(channels, channels, kernel_size=3, dilation=5, use_res2=True)

        # Multi-scale fusion (cat all 4 layers → 1×1 conv)
        self.mfa = nn.Sequential(
            nn.Conv1d(channels * 4, channels * 3, kernel_size=1),
            nn.BatchNorm1d(channels * 3),
            nn.ReLU(inplace=True),
        )

        # Attentive statistics pooling
        # Attention weight per frame: (B, channels*3, T) → (B, 1, T) → softmax over T
        self.attention = nn.Sequential(
            nn.Conv1d(channels * 3, 128, kernel_size=1),
            nn.ReLU(inplace=True),
            nn.BatchNorm1d(128),
            nn.Conv1d(128, channels * 3, kernel_size=1),
            nn.Softmax(dim=-1),
        )

        # Batch norm after pooling (operates on 2*channels*3 = mean+std concat)
        self.bn_pool = nn.BatchNorm1d(channels * 6)

        # Final fully-connected projection to emb_dim
        self.fc = nn.Linear(channels * 6, emb_dim)
        self.bn_fc = nn.BatchNorm1d(emb_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        x : (B, T, input_dim)  — WavLM frame-level features

        Returns
        -------
        (B, emb_dim)  — unnormalised speaker embedding
        """
        # (B, T, D) → (B, D, T)
        x = x.transpose(1, 2)
        x = self.input_proj(x)          # (B, channels, T)

        x1 = self.layer1(x)             # (B, channels, T)
        x2 = self.layer2(x1)            # (B, channels, T)
        x3 = self.layer3(x2)            # (B, channels, T)
        x4 = self.layer4(x3)            # (B, channels, T)

        # Multi-scale concatenation
        cat = torch.cat([x1, x2, x3, x4], dim=1)  # (B, channels*4, T)
        mfa = self.mfa(cat)                         # (B, channels*3, T)

        # Attentive statistics pooling
        weights = self.attention(mfa)               # (B, channels*3, T)
        mean = (mfa * weights).sum(dim=-1)          # (B, channels*3)
        # Weighted variance
        var  = (weights * (mfa ** 2)).sum(dim=-1) - mean ** 2
        std  = torch.sqrt(var.clamp(min=1e-8))     # (B, channels*3)

        pooled = torch.cat([mean, std], dim=1)      # (B, channels*6)
        pooled = self.bn_pool(pooled)

        emb = self.fc(pooled)                       # (B, emb_dim)
        emb = self.bn_fc(emb)
        return emb


# =============================================================================
# WavLMSpeakerEncoder
# =============================================================================


class WavLMSpeakerEncoder(nn.Module):
    """
    WavLM-Large backbone + ECAPA-TDNN head for speaker verification / identification.

    Pipeline
    --------
    1. WavLM-Large encodes 16 kHz raw waveform into contextual frame features.
    2. A learnable weighted sum aggregates the hidden states from all transformer layers.
    3. ECAPA-TDNN head pools across time into a single embedding.
    4. A linear projection reduces to ``emb_dim``.
    5. L2 normalisation ensures embeddings lie on the unit hypersphere.

    Parameters
    ----------
    emb_dim : int
        Dimensionality of the final speaker embedding.
    freeze_wavlm_layers : int
        Number of WavLM transformer layers (from layer 0) to freeze.
        Frozen layers use less GPU memory and train faster.
        With WavLM-Large (24 layers), 12 is a common setting.
    ecapa_channels : int
        Number of channels in the ECAPA-TDNN layers.
    wavlm_model_name : str
        HuggingFace model hub name for WavLM.
    """

    WAVLM_HIDDEN_DIM = 1024   # WavLM-Large hidden size

    def __init__(
        self,
        emb_dim: int = 256,
        freeze_wavlm_layers: int = 12,
        ecapa_channels: int = 512,
        wavlm_model_name: str = "microsoft/wavlm-large",
    ):
        super().__init__()

        # ── WavLM backbone ────────────────────────────────────────────────────
        from transformers import WavLMModel

        logger.info("Loading WavLM backbone: %s", wavlm_model_name)
        self.wavlm = WavLMModel.from_pretrained(wavlm_model_name, output_hidden_states=True)

        # Freeze the feature extractor (convolutional feature encoder)
        for param in self.wavlm.feature_extractor.parameters():
            param.requires_grad_(False)
        # Freeze the positional embedding
        for param in self.wavlm.encoder.pos_conv_embed.parameters():
            param.requires_grad_(False)

        # Freeze the first `freeze_wavlm_layers` transformer layers
        for layer_idx, layer in enumerate(self.wavlm.encoder.layers):
            if layer_idx < freeze_wavlm_layers:
                for param in layer.parameters():
                    param.requires_grad_(False)

        num_layers = len(self.wavlm.encoder.layers) + 1  # +1 for the CNN output
        logger.info(
            "WavLM: %d total layers, %d frozen",
            num_layers,
            freeze_wavlm_layers,
        )

        # Learnable per-layer weights for weighted sum of hidden states
        self.layer_weights = nn.Parameter(torch.ones(num_layers) / num_layers)

        # ── ECAPA-TDNN head ───────────────────────────────────────────────────
        self.ecapa_head = ECAPA_TDNN_Head(
            input_dim=self.WAVLM_HIDDEN_DIM,
            channels=ecapa_channels,
            emb_dim=emb_dim,
        )

        # ── Final projection ──────────────────────────────────────────────────
        # ECAPA head already projects to emb_dim; add one more linear + BN for
        # fine-grained control and easier adaptation.
        self.projection = nn.Sequential(
            nn.Linear(emb_dim, emb_dim),
            nn.BatchNorm1d(emb_dim),
        )

        self.emb_dim = emb_dim

    # ── Forward pass ──────────────────────────────────────────────────────────

    def forward(self, audio: torch.Tensor) -> torch.Tensor:
        """
        Parameters
        ----------
        audio : (B, T)  raw waveform at 16 kHz, values in [-1, 1].

        Returns
        -------
        (B, emb_dim)  L2-normalised speaker embedding.
        """
        # attention_mask is not needed for fixed-length inference; for variable-
        # length batches the caller should pad and pass a mask.
        outputs = self.wavlm(
            input_values=audio,
            output_hidden_states=True,
        )

        # hidden_states: tuple of (B, T, 1024) — one per layer (including CNN)
        hidden_states = outputs.hidden_states  # len = num_transformer_layers + 1

        # Weighted sum over layers
        weights = F.softmax(self.layer_weights, dim=0)
        weighted = torch.stack(
            [w * h for w, h in zip(weights, hidden_states)], dim=0
        ).sum(dim=0)  # (B, T, 1024)

        # ECAPA-TDNN pooling head
        emb = self.ecapa_head(weighted)         # (B, emb_dim)

        # Final projection
        emb = self.projection(emb)              # (B, emb_dim)

        # L2 normalisation → unit hypersphere
        emb = F.normalize(emb, p=2, dim=-1)    # (B, emb_dim)

        return emb

    # ── Serialisation helpers ─────────────────────────────────────────────────

    def save_pretrained(self, save_dir: str) -> None:
        """Save weights and config to ``save_dir``."""
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)

        ckpt = {
            "model_state_dict": self.state_dict(),
            "config": {
                "emb_dim": self.emb_dim,
                "freeze_wavlm_layers": sum(
                    1
                    for layer in self.wavlm.encoder.layers
                    if not any(p.requires_grad for p in layer.parameters())
                ),
                "ecapa_channels": self.ecapa_head.channels,
                "wavlm_model_name": self.wavlm.config.name_or_path,
            },
        }
        torch.save(ckpt, save_path / "model.pt")
        logger.info("Saved WavLMSpeakerEncoder to %s", save_path / "model.pt")

    @classmethod
    def from_pretrained(cls, path: str, **kwargs) -> "WavLMSpeakerEncoder":
        """
        Load from a checkpoint saved by ``save_pretrained``.

        Parameters
        ----------
        path :
            Path to either the ``model.pt`` file or the directory containing it.
        **kwargs :
            Override any config keys (e.g. ``emb_dim=192``).
        """
        ckpt_path = Path(path)
        if ckpt_path.is_dir():
            ckpt_path = ckpt_path / "model.pt"

        if not ckpt_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

        ckpt = torch.load(str(ckpt_path), map_location="cpu")
        config = ckpt.get("config", {})
        config.update(kwargs)  # allow caller overrides

        model = cls(
            emb_dim=config.get("emb_dim", 256),
            freeze_wavlm_layers=config.get("freeze_wavlm_layers", 12),
            ecapa_channels=config.get("ecapa_channels", 512),
            wavlm_model_name=config.get("wavlm_model_name", "microsoft/wavlm-large"),
        )

        missing, unexpected = model.load_state_dict(ckpt["model_state_dict"], strict=False)
        if missing:
            logger.warning("Missing keys in checkpoint: %s", missing)
        if unexpected:
            logger.warning("Unexpected keys in checkpoint: %s", unexpected)

        logger.info("Loaded WavLMSpeakerEncoder from %s", ckpt_path)
        return model


# =============================================================================
# Quick smoke test
# =============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Running WavLMSpeakerEncoder smoke test …")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Use a small config to avoid downloading WavLM-Large weights during testing
    from transformers import WavLMConfig, WavLMModel

    config = WavLMConfig(
        hidden_size=256,
        num_hidden_layers=2,
        num_attention_heads=4,
        intermediate_size=512,
        conv_dim=(128,) * 7,
        output_hidden_states=True,
    )

    class _SmallEncoder(WavLMSpeakerEncoder):
        WAVLM_HIDDEN_DIM = 256

        def __init__(self):
            # Bypass the full __init__ to avoid HF download
            nn.Module.__init__(self)
            self.wavlm = WavLMModel(config)
            num_layers = len(self.wavlm.encoder.layers) + 1
            self.layer_weights = nn.Parameter(torch.ones(num_layers) / num_layers)
            self.ecapa_head = ECAPA_TDNN_Head(input_dim=256, channels=128, emb_dim=64)
            self.projection = nn.Sequential(nn.Linear(64, 64), nn.BatchNorm1d(64))
            self.emb_dim = 64

    encoder = _SmallEncoder().to(device)
    encoder.eval()

    B, T = 2, 16000  # 1 second at 16 kHz
    dummy = torch.randn(B, T).to(device)

    with torch.no_grad():
        emb = encoder(dummy)

    print(f"Output shape : {emb.shape}")   # expected: (2, 64)
    norms = emb.norm(dim=-1)
    print(f"L2 norms     : {norms.tolist()}")  # expected: [1.0, 1.0]
    assert emb.shape == (B, 64), f"Unexpected shape: {emb.shape}"
    assert torch.allclose(norms, torch.ones(B).to(device), atol=1e-5), "Embeddings not L2-normalised!"

    print("Smoke test PASSED.")
