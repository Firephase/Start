"""
Multi-head self-attention with relative positional encoding for DiffSinger.

Implements Shaw et al. (2018) relative position representations alongside
a standard Transformer building block with pre-layer-norm ordering.
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional


# ---------------------------------------------------------------------------
# Relative positional encoding (Shaw et al., 2018)
# ---------------------------------------------------------------------------

class RelativePositionalEncoding(nn.Module):
    """
    Learnable relative positional embeddings clipped to [-max_relative_position,
    max_relative_position].  Returns a (2*K+1, head_dim) embedding table where
    K = max_relative_position.  The forward pass maps a (query_len, key_len)
    pair to a (query_len, key_len, head_dim) relative-key bias tensor.
    """

    def __init__(self, head_dim: int, max_relative_position: int = 128) -> None:
        super().__init__()
        self.max_relative_position = max_relative_position
        vocab_size = 2 * max_relative_position + 1
        self.embeddings = nn.Embedding(vocab_size, head_dim)
        nn.init.normal_(self.embeddings.weight, std=head_dim ** -0.5)

    def _relative_indices(self, query_len: int, key_len: int) -> torch.Tensor:
        """Return (query_len, key_len) integer index tensor."""
        q_idx = torch.arange(query_len, dtype=torch.long)
        k_idx = torch.arange(key_len, dtype=torch.long)
        # (query_len, key_len)
        rel = k_idx.unsqueeze(0) - q_idx.unsqueeze(1)
        rel = rel.clamp(-self.max_relative_position, self.max_relative_position)
        rel = rel + self.max_relative_position  # shift to [0, 2K]
        return rel

    def forward(self, query_len: int, key_len: int) -> torch.Tensor:
        """
        Returns:
            Tensor of shape (query_len, key_len, head_dim) — relative key
            embeddings to be contracted with query vectors inside MHA.
        """
        idx = self._relative_indices(query_len, key_len)
        return self.embeddings(idx)  # (Q, K, head_dim)


# ---------------------------------------------------------------------------
# Multi-head self-attention
# ---------------------------------------------------------------------------

class MultiHeadAttention(nn.Module):
    """
    Standard scaled dot-product multi-head attention augmented with Shaw-style
    relative positional encodings.  Supports optional boolean key-padding mask.

    Args:
        hidden_dim:   Total model dimension (must be divisible by num_heads).
        num_heads:    Number of attention heads.
        dropout:      Attention weight dropout probability.
        max_relative_position: Clip radius for relative position bias.
    """

    def __init__(
        self,
        hidden_dim: int,
        num_heads: int,
        dropout: float = 0.1,
        max_relative_position: int = 128,
    ) -> None:
        super().__init__()
        assert hidden_dim % num_heads == 0, (
            f"hidden_dim ({hidden_dim}) must be divisible by num_heads ({num_heads})"
        )
        self.hidden_dim = hidden_dim
        self.num_heads = num_heads
        self.head_dim = hidden_dim // num_heads
        self.scale = math.sqrt(self.head_dim)

        self.q_proj = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.k_proj = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.v_proj = nn.Linear(hidden_dim, hidden_dim, bias=False)
        self.out_proj = nn.Linear(hidden_dim, hidden_dim)

        self.rel_pos_enc = RelativePositionalEncoding(
            self.head_dim, max_relative_position
        )
        self.attn_dropout = nn.Dropout(dropout)
        self.proj_dropout = nn.Dropout(dropout)

    def _split_heads(self, x: torch.Tensor) -> torch.Tensor:
        """(B, T, D) -> (B, H, T, head_dim)"""
        B, T, _ = x.shape
        x = x.view(B, T, self.num_heads, self.head_dim)
        return x.permute(0, 2, 1, 3)

    def _merge_heads(self, x: torch.Tensor) -> torch.Tensor:
        """(B, H, T, head_dim) -> (B, T, D)"""
        B, H, T, D = x.shape
        return x.permute(0, 2, 1, 3).contiguous().view(B, T, H * D)

    def _relative_attn_bias(
        self, q: torch.Tensor, rel_emb: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute the Shaw et al. relative attention scores.

        Args:
            q:       (B, H, Q, head_dim)
            rel_emb: (Q, K, head_dim)  — from RelativePositionalEncoding

        Returns:
            (B, H, Q, K) bias to add to content-content scores.
        """
        # (B, H, Q, head_dim) x (Q, K, head_dim)^T -> (B, H, Q, K)
        # We need: sum_d q[b,h,q,d] * rel[q,k,d]
        # Using einsum for clarity:
        return torch.einsum("bhqd,qkd->bhqk", q, rel_emb)

    def forward(
        self,
        x: torch.Tensor,
        key_padding_mask: Optional[torch.Tensor] = None,
        attn_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            x:                (B, T, hidden_dim)
            key_padding_mask: (B, T) boolean mask; True positions are ignored.
            attn_mask:        (T, T) additive float mask (e.g., causal mask).

        Returns:
            (B, T, hidden_dim)
        """
        B, T, _ = x.shape

        q = self._split_heads(self.q_proj(x))  # (B, H, T, d)
        k = self._split_heads(self.k_proj(x))
        v = self._split_heads(self.v_proj(x))

        # Content-content attention scores
        scores = torch.matmul(q, k.transpose(-2, -1)) / self.scale  # (B, H, T, T)

        # Relative position bias
        rel_emb = self.rel_pos_enc(T, T).to(x.device)  # (T, T, d)
        rel_bias = self._relative_attn_bias(q, rel_emb) / self.scale
        scores = scores + rel_bias

        # Optional additive mask (e.g. causal masking)
        if attn_mask is not None:
            scores = scores + attn_mask.unsqueeze(0).unsqueeze(0)

        # Key padding mask — set masked positions to -inf
        if key_padding_mask is not None:
            scores = scores.masked_fill(
                key_padding_mask.unsqueeze(1).unsqueeze(2), float("-inf")
            )

        attn_weights = F.softmax(scores, dim=-1)
        attn_weights = self.attn_dropout(attn_weights)

        out = torch.matmul(attn_weights, v)   # (B, H, T, d)
        out = self._merge_heads(out)           # (B, T, D)
        out = self.proj_dropout(self.out_proj(out))
        return out


# ---------------------------------------------------------------------------
# Position-wise Feed-Forward Network
# ---------------------------------------------------------------------------

class FFNLayer(nn.Module):
    """
    Two-layer position-wise feed-forward network with GELU activation.

    Args:
        hidden_dim:  Input/output dimension.
        ffn_dim:     Inner dimension (typically 4 * hidden_dim).
        dropout:     Dropout applied after each linear projection.
    """

    def __init__(
        self,
        hidden_dim: int,
        ffn_dim: Optional[int] = None,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if ffn_dim is None:
            ffn_dim = 4 * hidden_dim
        self.linear1 = nn.Linear(hidden_dim, ffn_dim)
        self.linear2 = nn.Linear(ffn_dim, hidden_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """(B, T, D) -> (B, T, D)"""
        x = self.linear1(x)
        x = F.gelu(x)
        x = self.dropout(x)
        x = self.linear2(x)
        x = self.dropout(x)
        return x


# ---------------------------------------------------------------------------
# Transformer Block (pre-LN)
# ---------------------------------------------------------------------------

class TransformerBlock(nn.Module):
    """
    A single Transformer layer using pre-layer-norm ordering:

        y = x + Attention(LN(x))
        z = y + FFN(LN(y))

    Args:
        hidden_dim:            Model dimension.
        num_heads:             Number of attention heads.
        ffn_dim:               FFN inner dimension (default 4*hidden_dim).
        dropout:               Dropout rate applied in both sub-layers.
        max_relative_position: Clip radius for relative position bias.
    """

    def __init__(
        self,
        hidden_dim: int,
        num_heads: int,
        ffn_dim: Optional[int] = None,
        dropout: float = 0.1,
        max_relative_position: int = 128,
    ) -> None:
        super().__init__()
        self.norm1 = nn.LayerNorm(hidden_dim)
        self.attn = MultiHeadAttention(
            hidden_dim=hidden_dim,
            num_heads=num_heads,
            dropout=dropout,
            max_relative_position=max_relative_position,
        )
        self.norm2 = nn.LayerNorm(hidden_dim)
        self.ffn = FFNLayer(hidden_dim=hidden_dim, ffn_dim=ffn_dim, dropout=dropout)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        x: torch.Tensor,
        key_padding_mask: Optional[torch.Tensor] = None,
        attn_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            x:                (B, T, hidden_dim)
            key_padding_mask: (B, T) boolean; True = ignore.
            attn_mask:        (T, T) additive float mask.

        Returns:
            (B, T, hidden_dim)
        """
        # Self-attention sub-layer (pre-LN)
        residual = x
        x = self.norm1(x)
        x = self.attn(x, key_padding_mask=key_padding_mask, attn_mask=attn_mask)
        x = residual + x

        # FFN sub-layer (pre-LN)
        residual = x
        x = self.norm2(x)
        x = self.ffn(x)
        x = residual + x

        return x
