"""
FastSpeech2-based phoneme encoder for DiffSinger.

Encodes a phoneme sequence into a continuous hidden representation and
optionally expands it to the mel-frame rate via a duration-based length
regulator.  Speaker identity is injected at every Transformer block using
FiLM (Feature-wise Linear Modulation) conditioning.
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple

from .attention import TransformerBlock


# ---------------------------------------------------------------------------
# Phoneme Embedding + Sinusoidal Positional Encoding
# ---------------------------------------------------------------------------

class PhonemeEmbedding(nn.Module):
    """
    Learnable phoneme embeddings combined with sinusoidal positional encoding.

    Args:
        vocab_size:  Number of phoneme tokens (including padding at index 0).
        hidden_dim:  Embedding / model dimension.
        dropout:     Dropout applied to the summed embedding.
        max_len:     Maximum sequence length for pre-computed positional table.
        padding_idx: Index treated as padding (embedding zeroed out).
    """

    def __init__(
        self,
        vocab_size: int,
        hidden_dim: int,
        dropout: float = 0.1,
        max_len: int = 2048,
        padding_idx: int = 0,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.padding_idx = padding_idx
        self.token_emb = nn.Embedding(vocab_size, hidden_dim, padding_idx=padding_idx)
        nn.init.normal_(self.token_emb.weight, std=hidden_dim ** -0.5)
        with torch.no_grad():
            self.token_emb.weight[padding_idx].fill_(0.0)

        # Pre-compute sinusoidal table
        self.register_buffer("pos_enc", self._build_pos_enc(max_len, hidden_dim))
        self.dropout = nn.Dropout(dropout)

    @staticmethod
    def _build_pos_enc(max_len: int, d_model: int) -> torch.Tensor:
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(0, max_len, dtype=torch.float32).unsqueeze(1)
        div = torch.exp(
            torch.arange(0, d_model, 2, dtype=torch.float32)
            * -(math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        return pe  # (max_len, d_model)

    def forward(self, token_ids: torch.Tensor) -> torch.Tensor:
        """
        Args:
            token_ids: (B, T) long tensor of phoneme indices.

        Returns:
            (B, T, hidden_dim)
        """
        T = token_ids.size(1)
        x = self.token_emb(token_ids) * math.sqrt(self.hidden_dim)
        x = x + self.pos_enc[:T].unsqueeze(0)
        return self.dropout(x)


# ---------------------------------------------------------------------------
# Duration Predictor + Length Regulator
# ---------------------------------------------------------------------------

class DurationPredictor(nn.Module):
    """
    Convolutional duration predictor that outputs log-duration for each
    phoneme position.  Uses the same architecture as FastSpeech 2 (two
    Conv1d layers with LayerNorm + ReLU, followed by a linear projection).

    Args:
        hidden_dim:  Input channel dimension.
        kernel_size: Convolution kernel size (should be odd).
        num_layers:  Number of Conv + LN + ReLU blocks.
        dropout:     Dropout probability.
    """

    def __init__(
        self,
        hidden_dim: int,
        kernel_size: int = 3,
        num_layers: int = 2,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        padding = (kernel_size - 1) // 2
        layers = []
        for _ in range(num_layers):
            layers += [
                nn.Conv1d(hidden_dim, hidden_dim, kernel_size, padding=padding),
                nn.ReLU(),
            ]
        self.conv_stack = nn.Sequential(*layers)
        self.layer_norm = nn.LayerNorm(hidden_dim)
        self.linear = nn.Linear(hidden_dim, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, T, hidden_dim)

        Returns:
            log_duration: (B, T) — predicted log(duration + 1) per phoneme.
        """
        # Conv1d expects (B, C, T)
        out = self.conv_stack(x.transpose(1, 2)).transpose(1, 2)  # (B, T, C)
        out = self.layer_norm(out)
        out = self.dropout(out)
        log_dur = self.linear(out).squeeze(-1)  # (B, T)
        return log_dur

    def regulate_length(
        self,
        x: torch.Tensor,
        duration: torch.Tensor,
        max_len: Optional[int] = None,
    ) -> Tuple[torch.Tensor, int]:
        """
        Expand encoder output from phoneme-rate to frame-rate using integer
        durations (length regulator).

        Args:
            x:        (B, T_phoneme, hidden_dim) — encoder hidden states.
            duration: (B, T_phoneme) long tensor of frame counts per phoneme.
                      Values must be non-negative.
            max_len:  Optional target length; output is padded/truncated to this.

        Returns:
            regulated: (B, T_frame, hidden_dim)
            out_len:   Scalar int — actual maximum output length (before pad).
        """
        B, T, D = x.shape
        out_len = int(duration.sum(dim=1).max().item())
        if max_len is not None:
            out_len = min(out_len, max_len)

        # Expand each phoneme embedding by its duration count
        outputs = []
        for b in range(B):
            # Repeat each position duration[b, t] times
            repeated = torch.repeat_interleave(x[b], duration[b].clamp(min=0), dim=0)
            if repeated.size(0) < out_len:
                pad = x.new_zeros(out_len - repeated.size(0), D)
                repeated = torch.cat([repeated, pad], dim=0)
            else:
                repeated = repeated[:out_len]
            outputs.append(repeated)

        regulated = torch.stack(outputs, dim=0)  # (B, out_len, D)
        return regulated, out_len


# ---------------------------------------------------------------------------
# Variance Predictor (shared architecture for pitch / energy)
# ---------------------------------------------------------------------------

class VariancePredictor(nn.Module):
    """
    Shared convolutional variance predictor used for both pitch (F0) and
    energy.  Architecture mirrors DurationPredictor but is kept as a
    separate class for independent parameterisation.

    Args:
        hidden_dim:  Input channel dimension.
        kernel_size: Convolution kernel size.
        num_layers:  Number of Conv + LN + ReLU blocks.
        dropout:     Dropout probability.
        out_dim:     Output scalar dimension (1 for pitch/energy).
    """

    def __init__(
        self,
        hidden_dim: int,
        kernel_size: int = 3,
        num_layers: int = 2,
        dropout: float = 0.1,
        out_dim: int = 1,
    ) -> None:
        super().__init__()
        padding = (kernel_size - 1) // 2

        self.conv_blocks = nn.ModuleList()
        self.layer_norms = nn.ModuleList()
        for _ in range(num_layers):
            self.conv_blocks.append(
                nn.Conv1d(hidden_dim, hidden_dim, kernel_size, padding=padding)
            )
            self.layer_norms.append(nn.LayerNorm(hidden_dim))

        self.linear = nn.Linear(hidden_dim, out_dim)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, T, hidden_dim)

        Returns:
            (B, T, out_dim)
        """
        out = x.transpose(1, 2)  # (B, C, T)
        for conv, ln in zip(self.conv_blocks, self.layer_norms):
            out = self.relu(conv(out))
            out = ln(out.transpose(1, 2)).transpose(1, 2)
            out = self.dropout(out)
        out = out.transpose(1, 2)  # (B, T, C)
        return self.linear(out)   # (B, T, out_dim)


# ---------------------------------------------------------------------------
# FiLM Conditioning
# ---------------------------------------------------------------------------

class FiLMCondition(nn.Module):
    """
    Feature-wise Linear Modulation: projects a conditioning vector into a
    scale and shift pair that modulates per-position hidden states.

    Args:
        cond_dim:   Dimension of the conditioning vector (speaker embedding).
        hidden_dim: Dimension of the hidden state to be modulated.
    """

    def __init__(self, cond_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.proj = nn.Linear(cond_dim, 2 * hidden_dim)

    def forward(self, x: torch.Tensor, cond: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x:    (B, T, hidden_dim)
            cond: (B, cond_dim) speaker embedding.

        Returns:
            (B, T, hidden_dim) after scale-shift modulation.
        """
        gamma_beta = self.proj(cond)          # (B, 2*D)
        gamma, beta = gamma_beta.chunk(2, dim=-1)  # each (B, D)
        gamma = gamma.unsqueeze(1)            # (B, 1, D)
        beta = beta.unsqueeze(1)              # (B, 1, D)
        return (1.0 + gamma) * x + beta


# ---------------------------------------------------------------------------
# FastSpeech Encoder
# ---------------------------------------------------------------------------

class FastSpeechEncoder(nn.Module):
    """
    FastSpeech2-style phoneme encoder with speaker conditioning.

    Architecture:
        PhonemeEmbedding
        → N × (TransformerBlock → FiLM(speaker_emb))
        → LayerNorm

    Speaker identity is injected after every Transformer block via FiLM
    modulation so that speaker characteristics influence all levels of the
    representation.

    Args:
        vocab_size:            Phoneme vocabulary size.
        hidden_dim:            Model dimension.
        num_heads:             Number of attention heads per block.
        num_layers:            Number of Transformer blocks.
        ffn_dim:               FFN inner dimension (default 4*hidden_dim).
        speaker_emb_dim:       Dimension of the input speaker embedding.
        dropout:               Dropout rate.
        max_relative_position: Clip radius for relative position bias.
        padding_idx:           Padding token index.
    """

    def __init__(
        self,
        vocab_size: int = 200,
        hidden_dim: int = 256,
        num_heads: int = 2,
        num_layers: int = 4,
        ffn_dim: Optional[int] = None,
        speaker_emb_dim: int = 256,
        dropout: float = 0.1,
        max_relative_position: int = 128,
        padding_idx: int = 0,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim

        self.embedding = PhonemeEmbedding(
            vocab_size=vocab_size,
            hidden_dim=hidden_dim,
            dropout=dropout,
            padding_idx=padding_idx,
        )

        self.layers = nn.ModuleList([
            TransformerBlock(
                hidden_dim=hidden_dim,
                num_heads=num_heads,
                ffn_dim=ffn_dim,
                dropout=dropout,
                max_relative_position=max_relative_position,
            )
            for _ in range(num_layers)
        ])

        self.film_layers = nn.ModuleList([
            FiLMCondition(cond_dim=speaker_emb_dim, hidden_dim=hidden_dim)
            for _ in range(num_layers)
        ])

        self.final_norm = nn.LayerNorm(hidden_dim)

    def forward(
        self,
        phoneme_ids: torch.Tensor,
        speaker_emb: torch.Tensor,
        key_padding_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            phoneme_ids:      (B, T_phoneme) long tensor.
            speaker_emb:      (B, speaker_emb_dim) speaker embedding.
            key_padding_mask: (B, T_phoneme) bool; True = padding position.

        Returns:
            encoder_out: (B, T_phoneme, hidden_dim) speaker-conditioned
                         phoneme representations.
        """
        x = self.embedding(phoneme_ids)  # (B, T, D)

        for transformer_block, film in zip(self.layers, self.film_layers):
            x = transformer_block(x, key_padding_mask=key_padding_mask)
            x = film(x, speaker_emb)

        x = self.final_norm(x)
        return x
