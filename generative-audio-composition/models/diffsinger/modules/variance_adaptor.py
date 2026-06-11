"""
Variance Adaptor for DiffSinger.

Sits between the FastSpeech encoder and the diffusion decoder.  It:
  1. Predicts (or accepts ground-truth) phoneme durations and expands the
     encoder output from phoneme-rate to frame-rate via the length regulator.
  2. Predicts (or accepts ground-truth) frame-level F0 and energy, then folds
     them back into the hidden representation.

F0 conditioning follows the DiffSinger paper: the continuous F0 contour is
quantised into 300 log-spaced pitch bins, embedded via a learned lookup, and
added to the hidden states.
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple

from .fastspeech_encoder import DurationPredictor, VariancePredictor


# ---------------------------------------------------------------------------
# F0 Quantisation helpers
# ---------------------------------------------------------------------------

# Pitch bin boundaries (Hz) — 300 bins spanning ~32 Hz to ~1975 Hz (C1–B6)
_F0_MIN_HZ: float = 32.7  # C1
_F0_MAX_HZ: float = 1975.5  # B6
_NUM_PITCH_BINS: int = 300


def _build_f0_bins(n_bins: int = _NUM_PITCH_BINS) -> torch.Tensor:
    """Return a (n_bins,) tensor of Hz boundaries, log-spaced."""
    return torch.linspace(
        math.log(_F0_MIN_HZ), math.log(_F0_MAX_HZ), n_bins
    ).exp()


def f0_to_bin_indices(f0_hz: torch.Tensor, bins: torch.Tensor) -> torch.LongTensor:
    """
    Quantise a continuous F0 tensor to bin indices via nearest-bin lookup.

    Args:
        f0_hz: (...) tensor of F0 values in Hz (0 = unvoiced).
        bins:  (n_bins,) bin centre values.

    Returns:
        Long tensor of same shape, with values in [0, n_bins-1].
        Unvoiced frames (f0 <= 0) map to bin 0.
    """
    voiced = f0_hz > 0.0
    # Clamp to valid range for log
    f0_safe = f0_hz.clamp(min=_F0_MIN_HZ)
    log_f0 = f0_safe.log()
    log_bins = bins.log().to(f0_hz.device)
    # Nearest bin index
    diff = (log_f0.unsqueeze(-1) - log_bins).abs()   # (..., n_bins)
    indices = diff.argmin(dim=-1).long()              # (...)
    indices = torch.where(voiced, indices, torch.zeros_like(indices))
    return indices


# ---------------------------------------------------------------------------
# Variance Adaptor
# ---------------------------------------------------------------------------

class VarianceAdaptor(nn.Module):
    """
    DiffSinger Variance Adaptor.

    Components
    ----------
    * DurationPredictor  – predicts log-duration per phoneme.
    * PitchPredictor     – VariancePredictor that predicts log-F0 per frame;
                           the predicted (or GT) F0 is quantised and embedded.
    * EnergyPredictor    – VariancePredictor that predicts energy per frame.

    Teacher Forcing
    ---------------
    During training, ground-truth ``target_duration``, ``target_f0``, and
    ``target_energy`` should be passed.  The adaptor returns the predicted
    values alongside the adapted hidden states so that auxiliary losses can be
    computed externally.

    Args:
        hidden_dim:      Model dimension (must match encoder output).
        n_pitch_bins:    Number of F0 quantisation bins.
        speaker_emb_dim: Dimension of speaker embedding (currently unused here
                         but kept for API symmetry—speaker conditioning happens
                         in the encoder and diffusion decoder).
        dur_kernel_size: Conv kernel size for duration predictor.
        dur_num_layers:  Conv layers in duration predictor.
        var_kernel_size: Conv kernel size for pitch/energy predictors.
        var_num_layers:  Conv layers in pitch/energy predictors.
        dropout:         Dropout applied in all sub-modules.
    """

    def __init__(
        self,
        hidden_dim: int = 256,
        n_pitch_bins: int = _NUM_PITCH_BINS,
        speaker_emb_dim: int = 256,
        dur_kernel_size: int = 3,
        dur_num_layers: int = 2,
        var_kernel_size: int = 3,
        var_num_layers: int = 2,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.n_pitch_bins = n_pitch_bins

        # Duration predictor (phoneme-rate)
        self.duration_predictor = DurationPredictor(
            hidden_dim=hidden_dim,
            kernel_size=dur_kernel_size,
            num_layers=dur_num_layers,
            dropout=dropout,
        )

        # Pitch predictor (frame-rate, after length regulation)
        self.pitch_predictor = VariancePredictor(
            hidden_dim=hidden_dim,
            kernel_size=var_kernel_size,
            num_layers=var_num_layers,
            dropout=dropout,
            out_dim=1,  # log-F0
        )

        # Energy predictor (frame-rate)
        self.energy_predictor = VariancePredictor(
            hidden_dim=hidden_dim,
            kernel_size=var_kernel_size,
            num_layers=var_num_layers,
            dropout=dropout,
            out_dim=1,
        )

        # F0 bin embedding — index 0 reserved for unvoiced
        self.pitch_embedding = nn.Embedding(n_pitch_bins, hidden_dim)
        nn.init.normal_(self.pitch_embedding.weight, std=hidden_dim ** -0.5)

        # Energy embedding (linear projection from scalar)
        self.energy_embedding = nn.Linear(1, hidden_dim)

        # F0 bin boundaries (registered as a buffer so they move with .to(device))
        self.register_buffer("f0_bins", _build_f0_bins(n_pitch_bins))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _predict_duration(
        self,
        encoder_out: torch.Tensor,
        target_duration: Optional[torch.Tensor],
        inference: bool,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Returns:
            log_dur_pred: (B, T_ph)  — always the model prediction.
            dur_to_use:   (B, T_ph)  — integer durations for LR.
        """
        log_dur_pred = self.duration_predictor(encoder_out)  # (B, T_ph)

        if inference or target_duration is None:
            # Predict: exponentiate and round to nearest integer
            dur_to_use = (log_dur_pred.exp() - 1.0).clamp(min=0).round().long()
        else:
            dur_to_use = target_duration.long()

        return log_dur_pred, dur_to_use

    def _embed_f0(
        self,
        regulated: torch.Tensor,
        target_f0: Optional[torch.Tensor],
        inference: bool,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Predict frame-level F0, quantise, embed, and add to hidden states.

        Returns:
            out:       (B, T_fr, D) hidden states augmented with F0 embedding.
            log_f0_pred: (B, T_fr, 1) model-predicted log-F0.
            f0_used:   (B, T_fr) F0 values used (GT or predicted) in Hz.
        """
        log_f0_pred = self.pitch_predictor(regulated)  # (B, T_fr, 1)

        if inference or target_f0 is None:
            # Convert log-F0 prediction back to Hz
            f0_hz = (log_f0_pred.squeeze(-1).exp() - 1.0).clamp(min=0.0)
        else:
            f0_hz = target_f0  # (B, T_fr) in Hz

        bin_idx = f0_to_bin_indices(f0_hz, self.f0_bins)  # (B, T_fr)
        f0_emb = self.pitch_embedding(bin_idx)             # (B, T_fr, D)
        out = regulated + f0_emb
        return out, log_f0_pred, f0_hz

    def _embed_energy(
        self,
        hidden: torch.Tensor,
        target_energy: Optional[torch.Tensor],
        inference: bool,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Predict frame-level energy, embed, and add to hidden states.

        Returns:
            out:           (B, T_fr, D)
            energy_pred:   (B, T_fr, 1) model-predicted energy.
        """
        energy_pred = self.energy_predictor(hidden)  # (B, T_fr, 1)

        if inference or target_energy is None:
            energy_val = energy_pred
        else:
            energy_val = target_energy.unsqueeze(-1)  # (B, T_fr, 1)

        energy_emb = self.energy_embedding(energy_val)  # (B, T_fr, D)
        out = hidden + energy_emb
        return out, energy_pred

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(
        self,
        encoder_out: torch.Tensor,
        speaker_emb: torch.Tensor,
        target_f0: Optional[torch.Tensor] = None,
        target_energy: Optional[torch.Tensor] = None,
        target_duration: Optional[torch.Tensor] = None,
        max_len: Optional[int] = None,
        inference: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            encoder_out:     (B, T_ph, hidden_dim)  — encoder output.
            speaker_emb:     (B, speaker_emb_dim)   — speaker embedding (reserved
                             for future FiLM here; not used in current forward).
            target_f0:       (B, T_fr) GT F0 in Hz for teacher forcing.
            target_energy:   (B, T_fr) GT energy for teacher forcing.
            target_duration: (B, T_ph) GT integer frame counts per phoneme.
            max_len:         Optional cap on output length.
            inference:       If True, use all predicted values regardless of
                             whether GT targets are provided.

        Returns:
            adapted_output: (B, T_fr, hidden_dim) frame-rate hidden states.
            pred_duration:  (B, T_ph)   predicted log-duration.
            pred_f0:        (B, T_fr, 1) predicted log-F0 (before exp).
            pred_energy:    (B, T_fr, 1) predicted energy.
        """
        # 1. Duration prediction + length regulation
        log_dur_pred, dur_to_use = self._predict_duration(
            encoder_out, target_duration, inference
        )

        regulated, _ = self.duration_predictor.regulate_length(
            encoder_out, dur_to_use, max_len=max_len
        )  # (B, T_fr, D)

        # 2. Pitch predictor + F0 embedding
        hidden, log_f0_pred, _ = self._embed_f0(regulated, target_f0, inference)

        # 3. Energy predictor + energy embedding
        adapted_output, energy_pred = self._embed_energy(
            hidden, target_energy, inference
        )

        return adapted_output, log_dur_pred, log_f0_pred, energy_pred
