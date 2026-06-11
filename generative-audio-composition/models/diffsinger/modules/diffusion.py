"""
WaveNet-based diffusion decoder and Gaussian Diffusion process for DiffSinger.

Implements:
  - SinusoidalPosEmb: timestep sinusoidal embedding.
  - ResidualBlock: dilated WaveNet-style residual block with conditioning.
  - DiffusionDecoder: full WaveNet noise predictor (ε-parameterisation).
  - GaussianDiffusion: DDPM forward/reverse process with DDIM-style fast
    sampling for inference.

Reference:
  Liu et al., "DiffSinger: Singing Voice Synthesis via Shallow Diffusion
  Mechanism", AAAI 2022.
"""

import math
from typing import Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Timestep embedding
# ---------------------------------------------------------------------------

class SinusoidalPosEmb(nn.Module):
    """
    Sinusoidal timestep embedding, identical in spirit to Transformer
    positional encoding but applied to the scalar diffusion timestep.

    Args:
        dim: Output embedding dimension (must be even).
    """

    def __init__(self, dim: int) -> None:
        super().__init__()
        assert dim % 2 == 0, "SinusoidalPosEmb dim must be even."
        self.dim = dim

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        """
        Args:
            t: (B,) long or float tensor of timestep indices.

        Returns:
            (B, dim) sinusoidal embedding.
        """
        device = t.device
        half = self.dim // 2
        freqs = torch.exp(
            -math.log(10000.0) * torch.arange(half, device=device).float() / (half - 1)
        )                                      # (half,)
        args = t.float().unsqueeze(1) * freqs.unsqueeze(0)  # (B, half)
        emb = torch.cat([args.sin(), args.cos()], dim=-1)   # (B, dim)
        return emb


# ---------------------------------------------------------------------------
# WaveNet Residual Block
# ---------------------------------------------------------------------------

class ResidualBlock(nn.Module):
    """
    Dilated WaveNet residual block with gated activations and multi-source
    conditioning (timestep + speaker + encoder cross-conditioning).

    Architecture per block:
        x  →  DilatedConv  →  + cond_proj(t_emb)
                             + cond_proj(spk_emb)
                             + cross_cond_proj(enc_out)
           →  Gated(tanh × sigmoid)
           →  skip_proj  →  skip
           →  res_proj   →  + x  (residual)

    Args:
        residual_channels: Number of channels for residual stream and input/
                           output of this block.
        dilation:          Dilation factor for the causal-free dilated conv.
        t_emb_dim:         Dimension of the projected timestep embedding.
        encoder_dim:       Dimension of encoder output for cross-conditioning.
        speaker_emb_dim:   Dimension of the speaker embedding.
        kernel_size:       Kernel size for dilated conv.
    """

    def __init__(
        self,
        residual_channels: int,
        dilation: int,
        t_emb_dim: int,
        encoder_dim: int,
        speaker_emb_dim: int,
        kernel_size: int = 3,
    ) -> None:
        super().__init__()
        gate_channels = 2 * residual_channels  # for gated activation

        # Dilated convolution (non-causal: symmetric padding)
        padding = dilation * (kernel_size - 1) // 2
        self.dilated_conv = nn.Conv1d(
            residual_channels,
            gate_channels,
            kernel_size=kernel_size,
            dilation=dilation,
            padding=padding,
        )

        # Timestep conditioning (broadcasts over time axis)
        self.t_proj = nn.Linear(t_emb_dim, gate_channels)

        # Speaker conditioning (FiLM-style; broadcasts over time)
        self.spk_proj = nn.Linear(speaker_emb_dim, gate_channels)

        # Cross-attention replacement: encoder output added as bias
        self.enc_proj = nn.Conv1d(encoder_dim, gate_channels, kernel_size=1)

        # Output projections
        self.skip_proj = nn.Conv1d(residual_channels, residual_channels, kernel_size=1)
        self.res_proj = nn.Conv1d(residual_channels, residual_channels, kernel_size=1)

    def forward(
        self,
        x: torch.Tensor,
        t_emb: torch.Tensor,
        encoder_out: torch.Tensor,
        speaker_emb: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            x:           (B, residual_channels, T_mel)
            t_emb:       (B, t_emb_dim)  projected timestep embedding.
            encoder_out: (B, encoder_dim, T_mel)  already up-sampled.
            speaker_emb: (B, speaker_emb_dim)

        Returns:
            residual_out: (B, residual_channels, T_mel) — for next block.
            skip_out:     (B, residual_channels, T_mel) — accumulated skip.
        """
        residual = x

        # Dilated convolution
        h = self.dilated_conv(x)                          # (B, 2C, T)

        # Timestep bias  (B, 2C) → (B, 2C, 1) broadcast
        h = h + self.t_proj(t_emb).unsqueeze(-1)

        # Speaker bias (B, 2C) → (B, 2C, 1)
        h = h + self.spk_proj(speaker_emb).unsqueeze(-1)

        # Encoder cross-conditioning  (B, 2C, T)
        h = h + self.enc_proj(encoder_out)

        # Gated activation
        h_tanh, h_sig = h.chunk(2, dim=1)
        h = h_tanh.tanh() * h_sig.sigmoid()              # (B, C, T)

        skip_out = self.skip_proj(h)
        res_out = self.res_proj(h) + residual

        return res_out, skip_out


# ---------------------------------------------------------------------------
# Diffusion Decoder (WaveNet ε-predictor)
# ---------------------------------------------------------------------------

class DiffusionDecoder(nn.Module):
    """
    WaveNet-based noise predictor that estimates ε given the noisy mel x_t,
    diffusion timestep t, encoder output, and speaker embedding.

    Architecture:
        x_t  → input_conv
             → 20 × ResidualBlock  (dilation cycle [1,2,4,8,...])
             → sum(skip outputs)
             → ReLU → skip_conv → ReLU → output_conv
             → predicted ε (B, n_mels, T_mel)

    Args:
        n_mels:            Number of mel bins (input/output channels).
        residual_channels: Width of the residual stream.
        num_blocks:        Number of WaveNet residual blocks (default 20).
        dilation_cycle:    Dilation cycle length (default 4 → [1,2,4,8,1,2,...]).
        kernel_size:       Dilated conv kernel size.
        t_emb_dim:         Timestep sinusoidal embedding dimension.
        encoder_dim:       Encoder output dimension.
        speaker_emb_dim:   Speaker embedding dimension.
    """

    def __init__(
        self,
        n_mels: int = 80,
        residual_channels: int = 256,
        num_blocks: int = 20,
        dilation_cycle: int = 4,
        kernel_size: int = 3,
        t_emb_dim: int = 128,
        encoder_dim: int = 256,
        speaker_emb_dim: int = 256,
    ) -> None:
        super().__init__()
        self.n_mels = n_mels
        self.residual_channels = residual_channels

        # Timestep embedding: sinusoidal → 2-layer MLP
        self.t_emb = SinusoidalPosEmb(t_emb_dim)
        self.t_mlp = nn.Sequential(
            nn.Linear(t_emb_dim, t_emb_dim * 4),
            nn.Mish(),
            nn.Linear(t_emb_dim * 4, t_emb_dim),
        )

        # Input projection: n_mels → residual_channels
        self.input_conv = nn.Conv1d(n_mels, residual_channels, kernel_size=1)

        # Residual blocks
        dilations = [2 ** (i % dilation_cycle) for i in range(num_blocks)]
        self.res_blocks = nn.ModuleList([
            ResidualBlock(
                residual_channels=residual_channels,
                dilation=d,
                t_emb_dim=t_emb_dim,
                encoder_dim=encoder_dim,
                speaker_emb_dim=speaker_emb_dim,
                kernel_size=kernel_size,
            )
            for d in dilations
        ])
        self.num_blocks = num_blocks

        # Output projection: residual_channels → n_mels
        self.skip_conv = nn.Conv1d(residual_channels, residual_channels, kernel_size=1)
        self.output_conv = nn.Conv1d(residual_channels, n_mels, kernel_size=1)

        # Encoder conditioning projection (encoder_dim → encoder_dim kept as-is)
        # Will be transposed to (B, encoder_dim, T) inside forward.

    def forward(
        self,
        x_t: torch.Tensor,
        t: torch.Tensor,
        encoder_out: torch.Tensor,
        speaker_emb: torch.Tensor,
    ) -> torch.Tensor:
        """
        Predict noise ε.

        Args:
            x_t:         (B, n_mels, T_mel)      — noisy mel at step t.
            t:           (B,) long              — diffusion timestep indices.
            encoder_out: (B, T_mel, encoder_dim) — variance-adapted encoder
                         output, already at mel-frame rate.
            speaker_emb: (B, speaker_emb_dim)

        Returns:
            eps_pred: (B, n_mels, T_mel) predicted noise.
        """
        # Timestep embedding
        t_emb = self.t_mlp(self.t_emb(t))          # (B, t_emb_dim)

        # Encoder output: (B, T, D) → (B, D, T) for Conv1d
        enc = encoder_out.transpose(1, 2)            # (B, encoder_dim, T_mel)

        # Input
        h = self.input_conv(x_t)                    # (B, C, T)

        # Residual blocks + skip accumulation
        skip_sum = torch.zeros_like(h)
        for block in self.res_blocks:
            h, skip = block(h, t_emb, enc, speaker_emb)
            skip_sum = skip_sum + skip

        # Output
        out = F.relu(skip_sum / math.sqrt(self.num_blocks))
        out = F.relu(self.skip_conv(out))
        out = self.output_conv(out)                  # (B, n_mels, T)
        return out


# ---------------------------------------------------------------------------
# Gaussian Diffusion (DDPM + DDIM fast sampling)
# ---------------------------------------------------------------------------

class GaussianDiffusion(nn.Module):
    """
    DDPM wrapper around DiffusionDecoder with a linear noise schedule.

    Noise schedule
    --------------
    β_t linearly increases from β_1 to β_T over T = 1000 steps.
    All derived quantities (α̅, σ̅, …) are pre-computed and stored as buffers.

    Args:
        decoder:     DiffusionDecoder instance.
        n_mels:      Mel-spectrogram channels.
        T:           Total diffusion steps (default 1000).
        beta_start:  β_1 (default 1e-4).
        beta_end:    β_T (default 0.02).
    """

    def __init__(
        self,
        decoder: DiffusionDecoder,
        n_mels: int = 80,
        T: int = 1000,
        beta_start: float = 1e-4,
        beta_end: float = 0.02,
    ) -> None:
        super().__init__()
        self.decoder = decoder
        self.n_mels = n_mels
        self.T = T

        # Linear schedule
        betas = torch.linspace(beta_start, beta_end, T)       # (T,)
        alphas = 1.0 - betas                                   # (T,)
        alphas_cumprod = torch.cumprod(alphas, dim=0)          # ᾱ_t
        alphas_cumprod_prev = F.pad(alphas_cumprod[:-1], (1, 0), value=1.0)

        # Forward process helpers
        sqrt_alphas_cumprod = alphas_cumprod.sqrt()
        sqrt_one_minus_alphas_cumprod = (1.0 - alphas_cumprod).sqrt()

        # Reverse process helpers
        posterior_variance = (
            betas * (1.0 - alphas_cumprod_prev) / (1.0 - alphas_cumprod)
        )
        posterior_log_variance_clipped = torch.log(
            posterior_variance.clamp(min=1e-20)
        )
        posterior_mean_coef1 = (
            betas * alphas_cumprod_prev.sqrt() / (1.0 - alphas_cumprod)
        )
        posterior_mean_coef2 = (
            (1.0 - alphas_cumprod_prev) * alphas.sqrt() / (1.0 - alphas_cumprod)
        )

        for name, val in [
            ("betas", betas),
            ("alphas_cumprod", alphas_cumprod),
            ("alphas_cumprod_prev", alphas_cumprod_prev),
            ("sqrt_alphas_cumprod", sqrt_alphas_cumprod),
            ("sqrt_one_minus_alphas_cumprod", sqrt_one_minus_alphas_cumprod),
            ("posterior_variance", posterior_variance),
            ("posterior_log_variance_clipped", posterior_log_variance_clipped),
            ("posterior_mean_coef1", posterior_mean_coef1),
            ("posterior_mean_coef2", posterior_mean_coef2),
        ]:
            self.register_buffer(name, val)

    # ------------------------------------------------------------------
    # Helper: extract (B,) values from a (T,) buffer
    # ------------------------------------------------------------------

    @staticmethod
    def _extract(a: torch.Tensor, t: torch.Tensor, shape: torch.Size) -> torch.Tensor:
        """
        Gather buffer values at timestep indices and reshape for broadcasting.

        Args:
            a:     (T,) buffer.
            t:     (B,) long indices.
            shape: Target shape (B, n_mels, T_mel) for broadcast.

        Returns:
            (B, 1, 1) float tensor.
        """
        b = t.shape[0]
        out = a.gather(0, t.long())
        return out.reshape(b, *((1,) * (len(shape) - 1))).float()

    # ------------------------------------------------------------------
    # Forward diffusion q(x_t | x_0)
    # ------------------------------------------------------------------

    def q_sample(
        self,
        x_0: torch.Tensor,
        t: torch.Tensor,
        noise: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Sample x_t ~ q(x_t | x_0) = N(√ᾱ_t · x_0, (1-ᾱ_t)·I).

        Args:
            x_0:   (B, n_mels, T_mel) clean mel-spectrogram.
            t:     (B,) long diffusion step indices in [0, T-1].
            noise: Optional pre-sampled noise tensor; sampled if None.

        Returns:
            x_t: (B, n_mels, T_mel)
        """
        if noise is None:
            noise = torch.randn_like(x_0)
        sqrt_a = self._extract(self.sqrt_alphas_cumprod, t, x_0.shape)
        sqrt_1ma = self._extract(self.sqrt_one_minus_alphas_cumprod, t, x_0.shape)
        return sqrt_a * x_0 + sqrt_1ma * noise

    # ------------------------------------------------------------------
    # Training loss  (simple ε-prediction MSE)
    # ------------------------------------------------------------------

    def p_losses(
        self,
        x_0: torch.Tensor,
        encoder_out: torch.Tensor,
        speaker_emb: torch.Tensor,
        noise: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Compute the simplified diffusion training loss:

            L = E_{t, ε} [ ||ε - ε_θ(x_t, t, c)||² ]

        Args:
            x_0:         (B, n_mels, T_mel)    — ground-truth mel.
            encoder_out: (B, T_mel, encoder_dim) — conditioner.
            speaker_emb: (B, speaker_emb_dim)
            noise:       Optional fixed noise for debugging.

        Returns:
            Scalar MSE loss.
        """
        B = x_0.shape[0]
        t = torch.randint(0, self.T, (B,), device=x_0.device, dtype=torch.long)

        if noise is None:
            noise = torch.randn_like(x_0)

        x_t = self.q_sample(x_0, t, noise)
        eps_pred = self.decoder(x_t, t, encoder_out, speaker_emb)

        loss = F.mse_loss(eps_pred, noise)
        return loss

    # ------------------------------------------------------------------
    # Single DDPM reverse step  p(x_{t-1} | x_t)
    # ------------------------------------------------------------------

    @torch.no_grad()
    def p_sample(
        self,
        x_t: torch.Tensor,
        t: torch.Tensor,
        encoder_out: torch.Tensor,
        speaker_emb: torch.Tensor,
    ) -> torch.Tensor:
        """
        One denoising step: x_t → x_{t-1} using the DDPM posterior.

        Args:
            x_t:         (B, n_mels, T_mel)
            t:           (B,) long timestep indices.
            encoder_out: (B, T_mel, encoder_dim)
            speaker_emb: (B, speaker_emb_dim)

        Returns:
            x_prev: (B, n_mels, T_mel) — denoised estimate at step t-1.
        """
        B = x_t.shape[0]
        eps_pred = self.decoder(x_t, t, encoder_out, speaker_emb)

        # Compute x_0 estimate
        sqrt_a = self._extract(self.sqrt_alphas_cumprod, t, x_t.shape)
        sqrt_1ma = self._extract(self.sqrt_one_minus_alphas_cumprod, t, x_t.shape)
        x0_pred = (x_t - sqrt_1ma * eps_pred) / sqrt_a.clamp(min=1e-8)
        x0_pred = x0_pred.clamp(-1.0, 1.0)

        # Posterior mean
        c1 = self._extract(self.posterior_mean_coef1, t, x_t.shape)
        c2 = self._extract(self.posterior_mean_coef2, t, x_t.shape)
        posterior_mean = c1 * x0_pred + c2 * x_t

        # Posterior variance (zero at t=0)
        log_var = self._extract(self.posterior_log_variance_clipped, t, x_t.shape)
        noise = torch.randn_like(x_t)
        nonzero_mask = (t != 0).float().view(B, 1, 1)
        x_prev = posterior_mean + nonzero_mask * (0.5 * log_var).exp() * noise
        return x_prev

    # ------------------------------------------------------------------
    # Full DDPM reverse chain (slow)
    # ------------------------------------------------------------------

    @torch.no_grad()
    def p_sample_loop(
        self,
        shape: Tuple[int, ...],
        encoder_out: torch.Tensor,
        speaker_emb: torch.Tensor,
    ) -> torch.Tensor:
        """
        Full T-step DDPM reverse chain.

        Returns:
            x_0: (B, n_mels, T_mel)
        """
        device = encoder_out.device
        B = shape[0]
        x = torch.randn(shape, device=device)
        for step in reversed(range(self.T)):
            t = torch.full((B,), step, device=device, dtype=torch.long)
            x = self.p_sample(x, t, encoder_out, speaker_emb)
        return x

    # ------------------------------------------------------------------
    # DDIM fast sampling
    # ------------------------------------------------------------------

    @torch.no_grad()
    def fast_sampling(
        self,
        encoder_out: torch.Tensor,
        speaker_emb: torch.Tensor,
        steps: int = 50,
        eta: float = 0.0,
    ) -> torch.Tensor:
        """
        DDIM-style accelerated inference with a user-defined number of steps.

        DDIM (Song et al., 2020) defines a non-Markovian reverse process that
        can generalise DDPM (η=1) or deterministic sampling (η=0).

        Args:
            encoder_out: (B, T_mel, encoder_dim)
            speaker_emb: (B, speaker_emb_dim)
            steps:       Number of sampling steps (default 50).
            eta:         Stochasticity level (0 = deterministic DDIM,
                         1 = DDPM-equivalent).

        Returns:
            x_0: (B, n_mels, T_mel) synthesised mel-spectrogram.
        """
        device = encoder_out.device
        B = encoder_out.shape[0]
        T_mel = encoder_out.shape[1]
        shape = (B, self.n_mels, T_mel)

        # Uniformly spaced subset of timesteps, reversed (T-1 → 0)
        t_seq = torch.linspace(self.T - 1, 0, steps + 1, dtype=torch.long, device=device)
        t_seq = t_seq.clamp(0, self.T - 1)

        x = torch.randn(shape, device=device)

        for i in range(len(t_seq) - 1):
            t_cur = t_seq[i]
            t_prev = t_seq[i + 1]

            t_batch = t_cur.expand(B)
            eps_pred = self.decoder(x, t_batch, encoder_out, speaker_emb)

            # ᾱ values
            a_t = self.alphas_cumprod[t_cur]
            a_prev = self.alphas_cumprod[t_prev] if t_prev >= 0 else torch.tensor(1.0)

            # Predicted x_0
            sqrt_a_t = a_t.sqrt()
            sqrt_1ma_t = (1.0 - a_t).sqrt()
            x0_pred = (x - sqrt_1ma_t * eps_pred) / sqrt_a_t.clamp(min=1e-8)
            x0_pred = x0_pred.clamp(-1.0, 1.0)

            # DDIM step
            sigma = eta * ((1.0 - a_prev) / (1.0 - a_t) * (1.0 - a_t / a_prev)).sqrt()
            dir_x = (1.0 - a_prev - sigma ** 2).sqrt() * eps_pred
            noise = sigma * torch.randn_like(x) if eta > 0 else 0.0
            x = a_prev.sqrt() * x0_pred + dir_x + noise

        return x
