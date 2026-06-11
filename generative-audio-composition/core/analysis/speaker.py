"""
Speaker Embedding Extraction Module
=====================================
Extracts speaker embeddings using a WavLM-based ECAPA-TDNN architecture.
Embeddings are 256-dimensional L2-normalised vectors suitable for voice
cloning, speaker verification, and multi-speaker conditioning.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchaudio
import torchaudio.transforms as T

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WAVLM_SR: int = 16_000          # WavLM native sample rate
EMBEDDING_DIM: int = 256
WAVLM_HF_ID: str = "microsoft/wavlm-large"


# ===========================================================================
# Model definition
# ===========================================================================

class _SEModule(nn.Module):
    """Squeeze-and-Excitation module used inside ECAPA-TDNN Res2Blocks."""

    def __init__(self, channels: int, bottleneck: int = 128) -> None:
        super().__init__()
        self.se = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(channels, bottleneck),
            nn.ReLU(inplace=True),
            nn.Linear(bottleneck, channels),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, C, T)
        scale = self.se(x).unsqueeze(-1)  # (B, C, 1)
        return x * scale


class _Res2Block(nn.Module):
    """
    Res2Net-style dilated residual block for ECAPA-TDNN.
    """

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 3,
        dilation: int = 1,
        scale: int = 8,
    ) -> None:
        super().__init__()
        assert out_channels % scale == 0, "out_channels must be divisible by scale"
        self.scale = scale
        width = out_channels // scale

        self.conv_in = nn.Sequential(
            nn.Conv1d(in_channels, out_channels, kernel_size=1),
            nn.BatchNorm1d(out_channels),
            nn.ReLU(inplace=True),
        )

        self.convs = nn.ModuleList(
            [
                nn.Sequential(
                    nn.Conv1d(
                        width,
                        width,
                        kernel_size=kernel_size,
                        dilation=dilation,
                        padding=dilation * (kernel_size - 1) // 2,
                    ),
                    nn.BatchNorm1d(width),
                    nn.ReLU(inplace=True),
                )
                for _ in range(scale - 1)
            ]
        )

        self.conv_out = nn.Sequential(
            nn.Conv1d(out_channels, out_channels, kernel_size=1),
            nn.BatchNorm1d(out_channels),
        )

        self.se = _SEModule(out_channels)
        self.shortcut = (
            nn.Conv1d(in_channels, out_channels, kernel_size=1)
            if in_channels != out_channels
            else nn.Identity()
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.shortcut(x)
        out = self.conv_in(x)

        chunks = torch.chunk(out, self.scale, dim=1)
        y = chunks[0]
        outs = [y]
        for i, conv in enumerate(self.convs):
            y = conv(chunks[i + 1] + y)
            outs.append(y)

        out = torch.cat(outs, dim=1)
        out = self.conv_out(out)
        out = self.se(out)
        return self.relu(out + residual)


class _AttentiveStatsPooling(nn.Module):
    """
    Attentive statistics pooling: computes attention-weighted mean + std
    over the time axis to produce a fixed-length utterance embedding.
    """

    def __init__(self, in_dim: int, attention_dim: int = 128) -> None:
        super().__init__()
        self.attention = nn.Sequential(
            nn.Conv1d(in_dim * 3, attention_dim, kernel_size=1),
            nn.Tanh(),
            nn.Conv1d(attention_dim, in_dim, kernel_size=1),
            nn.Softmax(dim=2),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (B, C, T)
        mu = x.mean(dim=2, keepdim=True).expand_as(x)
        std = x.std(dim=2, keepdim=True).expand_as(x)
        attn_in = torch.cat([x, mu, std], dim=1)     # (B, 3C, T)
        alpha = self.attention(attn_in)               # (B, C, T)

        weighted_mean = (alpha * x).sum(dim=2)                              # (B, C)
        weighted_std = torch.sqrt(
            (alpha * (x - (alpha * x).sum(dim=2, keepdim=True)) ** 2).sum(dim=2)
            + 1e-8
        )
        return torch.cat([weighted_mean, weighted_std], dim=1)             # (B, 2C)


class SpeakerEncoderModel(nn.Module):
    """
    WavLM feature extractor + ECAPA-TDNN speaker encoder.

    Architecture
    ------------
    1. WavLM-large feature extractor (first 6 transformer layers frozen).
    2. Frame-level projection from WavLM hidden dim (1024) to ECAPA width.
    3. Stack of ECAPA-TDNN Res2Blocks with increasing dilation.
    4. Attentive statistics pooling → utterance embedding.
    5. L2-normalised linear projection to ``EMBEDDING_DIM`` (256).

    Parameters
    ----------
    wavlm_model : nn.Module
        Pre-loaded WavLM model (HuggingFace ``WavLMModel``).
    ecapa_channels : int
        Channel width for ECAPA-TDNN layers (default: 512).
    embedding_dim : int
        Output embedding dimensionality (default: 256).
    freeze_wavlm_layers : int
        Number of WavLM transformer layers to freeze (default: 6 out of 24).
    """

    def __init__(
        self,
        wavlm_model: nn.Module,
        ecapa_channels: int = 512,
        embedding_dim: int = EMBEDDING_DIM,
        freeze_wavlm_layers: int = 6,
    ) -> None:
        super().__init__()
        self.wavlm = wavlm_model
        self.embedding_dim = embedding_dim

        # Freeze the feature CNN and early transformer layers
        for param in self.wavlm.feature_extractor.parameters():
            param.requires_grad = False
        for i, layer in enumerate(self.wavlm.encoder.layers):
            if i < freeze_wavlm_layers:
                for param in layer.parameters():
                    param.requires_grad = False

        wavlm_hidden = self.wavlm.config.hidden_size  # 1024 for wavlm-large

        # Frame-level input projection
        self.input_proj = nn.Sequential(
            nn.Conv1d(wavlm_hidden, ecapa_channels, kernel_size=1),
            nn.BatchNorm1d(ecapa_channels),
            nn.ReLU(inplace=True),
        )

        # ECAPA-TDNN body
        self.res2blocks = nn.Sequential(
            _Res2Block(ecapa_channels, ecapa_channels, dilation=2),
            _Res2Block(ecapa_channels, ecapa_channels, dilation=3),
            _Res2Block(ecapa_channels, ecapa_channels, dilation=4),
            _Res2Block(ecapa_channels, ecapa_channels, dilation=5),
        )

        # Multi-scale aggregation conv
        self.agg_conv = nn.Sequential(
            nn.Conv1d(ecapa_channels * 4, ecapa_channels * 2, kernel_size=1),
            nn.BatchNorm1d(ecapa_channels * 2),
            nn.ReLU(inplace=True),
        )

        # Attentive stats pooling
        self.pooling = _AttentiveStatsPooling(ecapa_channels * 2)

        # Output projection
        self.output_proj = nn.Linear(ecapa_channels * 4, embedding_dim)
        self.bn_out = nn.BatchNorm1d(embedding_dim)

    def forward(
        self, input_values: torch.Tensor, attention_mask: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        """
        Parameters
        ----------
        input_values : torch.Tensor
            Shape ``(batch, samples)`` – 16 kHz waveform.
        attention_mask : torch.Tensor or None
            Padding mask for WavLM.

        Returns
        -------
        torch.Tensor
            L2-normalised embeddings, shape ``(batch, embedding_dim)``.
        """
        outputs = self.wavlm(
            input_values,
            attention_mask=attention_mask,
            output_hidden_states=False,
        )
        # (B, T_wav, hidden)  →  (B, hidden, T_wav) for Conv1d
        hidden = outputs.last_hidden_state.transpose(1, 2)

        x = self.input_proj(hidden)  # (B, C, T)

        # Multi-scale residual blocks
        b1 = self.res2blocks[0](x)
        b2 = self.res2blocks[1](b1)
        b3 = self.res2blocks[2](b2)
        b4 = self.res2blocks[3](b3)

        # Aggregate all scales
        agg = torch.cat([b1, b2, b3, b4], dim=1)  # (B, 4C, T)
        agg = self.agg_conv(agg)                   # (B, 2C, T)

        pooled = self.pooling(agg)                 # (B, 4C)
        proj = self.output_proj(pooled)            # (B, emb_dim)
        proj = self.bn_out(proj)

        return F.normalize(proj, p=2, dim=1)       # L2-normalise


# ===========================================================================
# High-level encoder
# ===========================================================================

class SpeakerEncoder:
    """
    High-level interface for speaker embedding extraction.

    If a fine-tuned checkpoint is provided via *model_path*, it is loaded on
    top of the WavLM-large backbone.  Otherwise only the WavLM feature
    extractor is used (useful for zero-shot or as a starting point for
    fine-tuning).

    Parameters
    ----------
    model_path : str or None
        Path to a ``.pt`` checkpoint produced by ``torch.save`` containing
        the full ``SpeakerEncoderModel`` state dict.  If ``None``, the raw
        WavLM-large backbone is downloaded from HuggingFace and the ECAPA
        head is randomly initialised.
    device : str
        PyTorch device string.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cuda",
    ) -> None:
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but not available – falling back to CPU.")
            device = "cpu"
        self.device = torch.device(device)

        logger.info("Loading WavLM backbone from HuggingFace (%s)…", WAVLM_HF_ID)
        self._wavlm_processor, wavlm_backbone = self._load_wavlm()

        self.model = SpeakerEncoderModel(wavlm_model=wavlm_backbone)

        if model_path is not None:
            checkpoint_path = str(Path(model_path).resolve())
            if not os.path.isfile(checkpoint_path):
                raise FileNotFoundError(
                    f"Speaker encoder checkpoint not found: {checkpoint_path}"
                )
            state_dict = torch.load(checkpoint_path, map_location=self.device)
            self.model.load_state_dict(state_dict)
            logger.info("Loaded checkpoint from %s", checkpoint_path)
        else:
            logger.info(
                "No checkpoint provided – WavLM backbone loaded with random ECAPA head."
            )

        self.model.to(self.device)
        self.model.eval()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_embedding(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """
        Extract a 256-dim L2-normalised speaker embedding.

        Parameters
        ----------
        audio : np.ndarray
            Mono or stereo waveform.
        sr : int
            Sample rate of *audio*.

        Returns
        -------
        np.ndarray
            Shape ``(256,)``, dtype float32.
        """
        tensor = self._preprocess(audio, sr)  # (1, samples)
        with torch.no_grad():
            emb = self.model(tensor.to(self.device))  # (1, 256)
        return emb.squeeze(0).cpu().numpy().astype(np.float32)

    def extract_embedding_from_segments(
        self, segments: list[np.ndarray], sr: int
    ) -> np.ndarray:
        """
        Compute a single embedding by averaging across multiple audio segments.

        Averaging in embedding space before L2-normalisation would distort the
        norm, so we normalise each segment embedding then average and
        re-normalise the result.

        Parameters
        ----------
        segments : list[np.ndarray]
            List of mono/stereo waveform arrays (any length).
        sr : int
            Sample rate (same for all segments).

        Returns
        -------
        np.ndarray
            Averaged, L2-normalised embedding, shape ``(256,)``.
        """
        if not segments:
            raise ValueError("segments list must not be empty.")

        embeddings = np.stack(
            [self.extract_embedding(seg, sr) for seg in segments], axis=0
        )  # (n, 256)

        mean_emb = embeddings.mean(axis=0)
        norm = np.linalg.norm(mean_emb)
        if norm < 1e-8:
            return mean_emb
        return (mean_emb / norm).astype(np.float32)

    def compute_similarity(
        self, emb1: np.ndarray, emb2: np.ndarray
    ) -> float:
        """
        Cosine similarity between two L2-normalised embeddings.

        Because embeddings are already unit-normalised, this is simply the
        dot product.

        Returns
        -------
        float
            Similarity in [-1, 1].
        """
        e1 = emb1.astype(np.float32).ravel()
        e2 = emb2.astype(np.float32).ravel()
        n1, n2 = np.linalg.norm(e1), np.linalg.norm(e2)
        if n1 < 1e-8 or n2 < 1e-8:
            return 0.0
        return float(np.dot(e1 / n1, e2 / n2))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _preprocess(self, audio: np.ndarray, sr: int) -> torch.Tensor:
        """
        Resample to 16 kHz, collapse to mono, L-inf normalise, and return a
        ``(1, samples)`` float32 tensor.
        """
        audio = audio.astype(np.float32)

        # Mono
        if audio.ndim == 2:
            audio = (
                audio.mean(axis=0) if audio.shape[0] <= 8 else audio.mean(axis=1)
            )

        # Resample
        if sr != WAVLM_SR:
            tensor = torch.from_numpy(audio).unsqueeze(0)
            resamp = T.Resample(orig_freq=sr, new_freq=WAVLM_SR)
            audio = resamp(tensor).squeeze(0).numpy()

        # Peak-normalise
        peak = np.abs(audio).max()
        if peak > 1e-6:
            audio = audio / peak

        return torch.from_numpy(audio).unsqueeze(0)  # (1, samples)

    @staticmethod
    def _load_wavlm() -> tuple[Any, nn.Module]:
        """
        Download WavLM-large from HuggingFace and return
        ``(processor, model)``.
        """
        try:
            from transformers import WavLMModel, Wav2Vec2FeatureExtractor
        except ImportError as exc:
            raise ImportError(
                "transformers>=4.30 is required for WavLM. "
                "Install it with: pip install transformers"
            ) from exc

        processor = Wav2Vec2FeatureExtractor.from_pretrained(WAVLM_HF_ID)
        model = WavLMModel.from_pretrained(WAVLM_HF_ID)
        model.eval()
        return processor, model
