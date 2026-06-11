"""
DiffSinger: Full singing voice synthesis model.

Combines:
  FastSpeechEncoder   — phoneme sequence → hidden representations
  VarianceAdaptor     — duration / pitch / energy prediction and length regulation
  GaussianDiffusion   — diffusion-based mel-spectrogram generation
  HiFiGAN             — mel → waveform

High-level API
--------------
  DiffSinger.synthesize(phonemes, speaker_emb, f0_contour, fast_sampling)
      → numpy waveform at 44100 Hz.

  DiffSinger.from_config(config)   — build from a config dict.
  DiffSinger.from_pretrained(path) — load from a checkpoint file.

G2P (Grapheme-to-Phoneme)
--------------------------
The module provides two backends:
  1. CMUdict (via NLTK)    — fast, English-only, no external process.
  2. phonemizer library    — supports multiple languages; falls back to
                             espeak when available.

Both backends are used lazily (imported on first call) so missing dependencies
only cause errors when actually invoking the G2P path.
"""

import os
import logging
import math
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from .modules.fastspeech_encoder import FastSpeechEncoder
from .modules.variance_adaptor import VarianceAdaptor
from .modules.diffusion import DiffusionDecoder, GaussianDiffusion
from .vocoder import HiFiGAN

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CMUdict / phonemizer G2P utilities
# ---------------------------------------------------------------------------

#: Standard ARPAbet phoneme set (index 0 = <pad>, 1 = <unk>)
ARPABET_VOCAB: List[str] = [
    "<pad>", "<unk>",
    "AA", "AE", "AH", "AO", "AW", "AY",
    "B", "CH", "D", "DH", "EH", "ER", "EY",
    "F", "G", "HH", "IH", "IY", "JH", "K",
    "L", "M", "N", "NG", "OW", "OY", "P",
    "R", "S", "SH", "T", "TH", "UH", "UW",
    "V", "W", "Y", "Z", "ZH",
    # Stress markers attached directly to vowels are mapped to their base
    # phoneme; we also include silences.
    "SIL", "SP",
]

PHONEME_TO_ID: Dict[str, int] = {p: i for i, p in enumerate(ARPABET_VOCAB)}
VOCAB_SIZE: int = len(ARPABET_VOCAB)


def _strip_stress(phoneme: str) -> str:
    """Remove CMUdict numeric stress markers (e.g. 'AH1' → 'AH')."""
    return phoneme.rstrip("012")


def _g2p_cmudict(words: List[str]) -> List[str]:
    """
    Convert a list of word strings to ARPAbet phonemes using NLTK CMUdict.

    Unknown words are mapped to a single <unk> token.

    Args:
        words: Tokenised list of (lowercased) English words.

    Returns:
        Flat list of ARPAbet phoneme strings.
    """
    try:
        from nltk.corpus import cmudict
        entries = cmudict.dict()
    except LookupError:
        import nltk
        nltk.download("cmudict", quiet=True)
        from nltk.corpus import cmudict
        entries = cmudict.dict()

    phonemes: List[str] = []
    for word in words:
        w = word.lower().strip(".,!?;:'\"")
        if w in entries:
            # Use the first pronunciation variant
            phonemes.extend(_strip_stress(p) for p in entries[w][0])
        else:
            phonemes.append("<unk>")
        phonemes.append("SP")  # word boundary
    return phonemes


def _g2p_phonemizer(text: str, language: str = "en-us") -> List[str]:
    """
    Convert raw text to ARPAbet-compatible phonemes using the `phonemizer`
    library (must be installed; requires espeak-ng).

    Falls back to CMUdict if phonemizer is not available.

    Args:
        text:     Raw input text.
        language: BCP-47 language code (default 'en-us').

    Returns:
        Flat list of phoneme strings.
    """
    try:
        from phonemizer import phonemize
        from phonemizer.separator import Separator
        sep = Separator(phone=" ", word="|", syllable="")
        ph_str: str = phonemize(
            text,
            language=language,
            backend="espeak",
            separator=sep,
            strip=True,
            with_stress=False,
        )
        # ph_str is space-separated phones with | as word boundary
        tokens: List[str] = []
        for segment in ph_str.split("|"):
            tokens.extend(p.upper() for p in segment.split() if p)
            tokens.append("SP")
        return tokens
    except ImportError:
        logger.warning(
            "phonemizer not installed — falling back to CMUdict G2P. "
            "Install with: pip install phonemizer"
        )
        return _g2p_cmudict(text.split())


def text_to_phoneme_ids(
    text: str,
    use_phonemizer: bool = False,
    language: str = "en-us",
) -> List[int]:
    """
    Convert a raw text string to a list of phoneme vocabulary indices.

    Args:
        text:            Input text (sentence or lyric line).
        use_phonemizer:  If True, use the phonemizer backend; otherwise CMUdict.
        language:        Language for phonemizer backend.

    Returns:
        List of integer indices into ARPABET_VOCAB.
    """
    if use_phonemizer:
        phones = _g2p_phonemizer(text, language=language)
    else:
        phones = _g2p_cmudict(text.split())

    ids = [PHONEME_TO_ID.get(p, PHONEME_TO_ID["<unk>"]) for p in phones]
    return ids


# ---------------------------------------------------------------------------
# Speaker Embedding Projection
# ---------------------------------------------------------------------------

class SpeakerEncoder(nn.Module):
    """
    Projects a pre-computed d-vector / x-vector to the model's hidden_dim.

    Args:
        input_dim:  Dimension of the input speaker embedding (e.g. 256).
        hidden_dim: Target dimension for the model.
    """

    def __init__(self, input_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )

    def forward(self, x: Tensor) -> Tensor:
        """
        Args:
            x: (B, input_dim)
        Returns:
            (B, hidden_dim)
        """
        return self.proj(x)


# ---------------------------------------------------------------------------
# DiffSinger main model
# ---------------------------------------------------------------------------

class DiffSinger(nn.Module):
    """
    End-to-end DiffSinger singing voice synthesis model.

    Pipeline
    --------
    phoneme_ids  →  FastSpeechEncoder (+ speaker FiLM)
                 →  VarianceAdaptor (duration / F0 / energy)
                 →  GaussianDiffusion (mel generation)
                 →  HiFiGAN (waveform)

    Training
    --------
    Call ``forward(...)`` with ground-truth targets to get training losses.
    The method returns a dict containing the diffusion loss and auxiliary
    variance predictor losses so they can be weighted externally.

    Inference
    ---------
    Call ``synthesize(...)`` for a high-level numpy API, or call
    ``forward(..., inference=True)`` for tensor-level access.

    Args:
        vocab_size:        Phoneme vocabulary size.
        hidden_dim:        Core model dimension.
        num_encoder_heads: Number of MHA heads in the encoder.
        num_encoder_layers: Number of Transformer blocks in encoder.
        speaker_emb_dim:   Dimensionality of raw (input) speaker embeddings.
        n_mels:            Number of mel-spectrogram bins.
        n_pitch_bins:      Number of F0 quantisation bins.
        diffusion_steps:   Total DDPM steps T.
        diffusion_blocks:  Number of WaveNet blocks in the decoder.
        t_emb_dim:         Timestep embedding dimension.
        dropout:           Dropout rate throughout.
        sample_rate:       Target waveform sample rate (default 44100).
    """

    def __init__(
        self,
        vocab_size: int = VOCAB_SIZE,
        hidden_dim: int = 256,
        num_encoder_heads: int = 2,
        num_encoder_layers: int = 4,
        speaker_emb_dim: int = 256,
        n_mels: int = 80,
        n_pitch_bins: int = 300,
        diffusion_steps: int = 1000,
        diffusion_blocks: int = 20,
        t_emb_dim: int = 128,
        dropout: float = 0.1,
        sample_rate: int = 44100,
    ) -> None:
        super().__init__()
        self.hidden_dim = hidden_dim
        self.n_mels = n_mels
        self.sample_rate = sample_rate

        # Speaker encoder projects raw embedding → hidden_dim
        self.speaker_encoder = SpeakerEncoder(
            input_dim=speaker_emb_dim,
            hidden_dim=hidden_dim,
        )

        # Phoneme encoder
        self.encoder = FastSpeechEncoder(
            vocab_size=vocab_size,
            hidden_dim=hidden_dim,
            num_heads=num_encoder_heads,
            num_layers=num_encoder_layers,
            speaker_emb_dim=hidden_dim,  # projected dim
            dropout=dropout,
        )

        # Variance adaptor
        self.variance_adaptor = VarianceAdaptor(
            hidden_dim=hidden_dim,
            n_pitch_bins=n_pitch_bins,
            speaker_emb_dim=hidden_dim,
            dropout=dropout,
        )

        # Mel projection (encoder hidden_dim → n_mels channel conditioning)
        # The diffusion decoder expects encoder_dim = hidden_dim.

        # Diffusion decoder
        decoder = DiffusionDecoder(
            n_mels=n_mels,
            residual_channels=hidden_dim,
            num_blocks=diffusion_blocks,
            t_emb_dim=t_emb_dim,
            encoder_dim=hidden_dim,
            speaker_emb_dim=hidden_dim,
        )
        self.diffusion = GaussianDiffusion(
            decoder=decoder,
            n_mels=n_mels,
            T=diffusion_steps,
        )

        # HiFi-GAN vocoder
        self.vocoder = HiFiGAN(n_mels=n_mels)

        # Whether the vocoder participates in the backward pass.
        # In most workflows the vocoder is pre-trained and frozen.
        self._vocoder_frozen = False

    def freeze_vocoder(self) -> None:
        """Freeze vocoder parameters (call after loading a pre-trained vocoder)."""
        for p in self.vocoder.parameters():
            p.requires_grad_(False)
        self._vocoder_frozen = True

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def forward(
        self,
        phonemes: Tensor,
        speaker_emb: Tensor,
        f0: Optional[Tensor] = None,
        energy: Optional[Tensor] = None,
        duration: Optional[Tensor] = None,
        mel_target: Optional[Tensor] = None,
        key_padding_mask: Optional[Tensor] = None,
        inference: bool = False,
        fast_sampling: bool = True,
        fast_steps: int = 50,
    ) -> Union[Dict[str, Tensor], Tensor]:
        """
        Training or inference forward pass.

        Args:
            phonemes:         (B, T_ph) long — phoneme token ids.
            speaker_emb:      (B, speaker_emb_dim) — raw speaker embedding.
            f0:               (B, T_fr) GT F0 contour in Hz (teacher forcing).
            energy:           (B, T_fr) GT energy (teacher forcing).
            duration:         (B, T_ph) GT integer frame durations.
            mel_target:       (B, n_mels, T_fr) GT mel for diffusion loss.
            key_padding_mask: (B, T_ph) bool; True = padding position.
            inference:        Run full inference (no GT targets, returns waveform).
            fast_sampling:    Use DDIM fast sampling during inference.
            fast_steps:       Number of DDIM steps.

        Returns:
            Training (inference=False):
                dict with keys:
                  "diffusion_loss"  — main reconstruction loss (scalar).
                  "dur_loss"        — duration predictor MSE loss (scalar).
                  "f0_loss"         — pitch predictor MSE loss (scalar).
                  "energy_loss"     — energy predictor MSE loss (scalar).
                  "mel_pred"        — (B, n_mels, T_fr) predicted mel.
                  "waveform"        — (B, 1, T_wave) synthesised waveform.
                  "pred_duration"   — (B, T_ph) log-duration predictions.
                  "pred_f0"         — (B, T_fr, 1) log-F0 predictions.
                  "pred_energy"     — (B, T_fr, 1) energy predictions.

            Inference (inference=True):
                (B, 1, T_wave) waveform tensor.
        """
        # 1. Project speaker embedding
        spk = self.speaker_encoder(speaker_emb)          # (B, hidden_dim)

        # 2. Encode phonemes
        enc_out = self.encoder(phonemes, spk, key_padding_mask=key_padding_mask)
        # enc_out: (B, T_ph, hidden_dim)

        # 3. Variance adaptor
        adapted, pred_duration, pred_f0, pred_energy = self.variance_adaptor(
            encoder_out=enc_out,
            speaker_emb=spk,
            target_f0=f0,
            target_energy=energy,
            target_duration=duration,
            inference=inference,
        )
        # adapted: (B, T_fr, hidden_dim)

        # 4. Diffusion step
        if inference:
            # Generate mel from noise
            if fast_sampling:
                mel_pred = self.diffusion.fast_sampling(
                    encoder_out=adapted,
                    speaker_emb=spk,
                    steps=fast_steps,
                )
            else:
                shape = (adapted.shape[0], self.n_mels, adapted.shape[1])
                mel_pred = self.diffusion.p_sample_loop(shape, adapted, spk)
            # mel_pred: (B, n_mels, T_fr)

            # 5. Vocoder
            with torch.no_grad() if self._vocoder_frozen else torch.enable_grad():
                waveform = self.vocoder(mel_pred)        # (B, 1, T_wave)

            return waveform

        else:
            # Training mode
            if mel_target is None:
                raise ValueError(
                    "mel_target must be provided during training (inference=False)."
                )

            # Compute diffusion loss
            diff_loss = self.diffusion.p_losses(
                x_0=mel_target,
                encoder_out=adapted,
                speaker_emb=spk,
            )

            # Auxiliary losses
            if duration is not None:
                log_dur_gt = torch.log(duration.float().clamp(min=1e-5) + 1.0)
                dur_loss = F.mse_loss(pred_duration, log_dur_gt)
            else:
                dur_loss = pred_duration.new_zeros(1).squeeze()

            if f0 is not None:
                log_f0_gt = torch.log(f0.clamp(min=1e-5) + 1.0).unsqueeze(-1)
                f0_loss = F.mse_loss(pred_f0, log_f0_gt)
            else:
                f0_loss = pred_f0.new_zeros(1).squeeze()

            if energy is not None:
                energy_loss = F.mse_loss(pred_energy, energy.unsqueeze(-1))
            else:
                energy_loss = pred_energy.new_zeros(1).squeeze()

            # Quick mel estimate for logging / perceptual loss
            # (run a few DDIM steps for a rough preview — not used in loss)
            with torch.no_grad():
                mel_pred_preview = self.diffusion.fast_sampling(
                    encoder_out=adapted,
                    speaker_emb=spk,
                    steps=10,
                )

            with torch.no_grad():
                waveform = self.vocoder(mel_pred_preview)

            return {
                "diffusion_loss": diff_loss,
                "dur_loss": dur_loss,
                "f0_loss": f0_loss,
                "energy_loss": energy_loss,
                "mel_pred": mel_pred_preview,
                "waveform": waveform,
                "pred_duration": pred_duration,
                "pred_f0": pred_f0,
                "pred_energy": pred_energy,
            }

    # ------------------------------------------------------------------
    # High-level synthesis API
    # ------------------------------------------------------------------

    @torch.no_grad()
    def synthesize(
        self,
        phonemes: Union[List[str], str],
        speaker_emb: np.ndarray,
        f0_contour: Optional[np.ndarray] = None,
        fast_sampling: bool = True,
        fast_steps: int = 50,
        device: Optional[str] = None,
    ) -> np.ndarray:
        """
        High-level inference API: text / phoneme list → numpy waveform.

        Args:
            phonemes:     Either a raw text string (G2P will be applied) or a
                          list of ARPAbet phoneme strings.
            speaker_emb:  (speaker_emb_dim,) numpy array — speaker d-vector.
            f0_contour:   Optional (T_fr,) numpy array of F0 values in Hz for
                          guided pitch synthesis.  When None, the model predicts
                          F0 automatically.
            fast_sampling: Use DDIM fast sampling (strongly recommended).
            fast_steps:   Number of DDIM denoising steps (default 50).
            device:       Target device string (e.g. "cuda", "cpu").  Defaults
                          to the device of the model parameters.

        Returns:
            waveform: (T_wave,) float32 numpy array at ``self.sample_rate`` Hz,
                      values in [-1, 1].
        """
        # Resolve device
        if device is None:
            try:
                device = next(self.parameters()).device
            except StopIteration:
                device = torch.device("cpu")
        else:
            device = torch.device(device)

        self.eval()

        # G2P: convert text/phoneme list → ids
        if isinstance(phonemes, str):
            ph_ids = text_to_phoneme_ids(phonemes, use_phonemizer=False)
        else:
            # List of phoneme strings
            ph_ids = [PHONEME_TO_ID.get(p, PHONEME_TO_ID["<unk>"]) for p in phonemes]

        if len(ph_ids) == 0:
            raise ValueError("phonemes resolved to an empty sequence.")

        # Build tensors
        ph_tensor = torch.tensor(ph_ids, dtype=torch.long, device=device).unsqueeze(0)
        # (1, T_ph)

        spk_tensor = torch.tensor(
            speaker_emb, dtype=torch.float32, device=device
        ).unsqueeze(0)
        # (1, speaker_emb_dim)

        f0_tensor: Optional[Tensor] = None
        if f0_contour is not None:
            f0_tensor = torch.tensor(
                f0_contour, dtype=torch.float32, device=device
            ).unsqueeze(0)
            # (1, T_fr)

        # Forward (inference mode)
        waveform = self.forward(
            phonemes=ph_tensor,
            speaker_emb=spk_tensor,
            f0=f0_tensor,
            inference=True,
            fast_sampling=fast_sampling,
            fast_steps=fast_steps,
        )
        # waveform: (1, 1, T_wave)

        wav_np = waveform.squeeze().cpu().float().numpy()
        return wav_np.astype(np.float32)

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: dict) -> "DiffSinger":
        """
        Build a DiffSinger model from a configuration dictionary.

        All keys are optional and fall back to the class defaults.

        Example config dict::

            {
                "vocab_size": 42,
                "hidden_dim": 256,
                "num_encoder_heads": 2,
                "num_encoder_layers": 4,
                "speaker_emb_dim": 256,
                "n_mels": 80,
                "n_pitch_bins": 300,
                "diffusion_steps": 1000,
                "diffusion_blocks": 20,
                "t_emb_dim": 128,
                "dropout": 0.1,
                "sample_rate": 44100,
            }

        Args:
            config: Dict of constructor keyword arguments.

        Returns:
            Instantiated DiffSinger model.
        """
        return cls(
            vocab_size=config.get("vocab_size", VOCAB_SIZE),
            hidden_dim=config.get("hidden_dim", 256),
            num_encoder_heads=config.get("num_encoder_heads", 2),
            num_encoder_layers=config.get("num_encoder_layers", 4),
            speaker_emb_dim=config.get("speaker_emb_dim", 256),
            n_mels=config.get("n_mels", 80),
            n_pitch_bins=config.get("n_pitch_bins", 300),
            diffusion_steps=config.get("diffusion_steps", 1000),
            diffusion_blocks=config.get("diffusion_blocks", 20),
            t_emb_dim=config.get("t_emb_dim", 128),
            dropout=config.get("dropout", 0.1),
            sample_rate=config.get("sample_rate", 44100),
        )

    @classmethod
    def from_pretrained(cls, checkpoint_path: str, map_location: Optional[str] = None) -> "DiffSinger":
        """
        Load a complete DiffSinger checkpoint.

        The checkpoint should be saved with::

            torch.save({
                "config": config_dict,
                "model_state_dict": model.state_dict(),
            }, path)

        Args:
            checkpoint_path: Path to the .pt / .pth file.
            map_location:    Optional device string.

        Returns:
            DiffSinger model loaded with saved weights, in eval mode.
        """
        if not os.path.isfile(checkpoint_path):
            raise FileNotFoundError(
                f"DiffSinger checkpoint not found: {checkpoint_path}"
            )

        ckpt = torch.load(
            checkpoint_path,
            map_location=map_location or "cpu",
            weights_only=False,
        )

        config: dict = {}
        if isinstance(ckpt, dict):
            config = ckpt.get("config", {})
            state = (
                ckpt.get("model_state_dict")
                or ckpt.get("state_dict")
                or ckpt
            )
        else:
            state = ckpt

        model = cls.from_config(config)
        model.load_state_dict(state, strict=False)
        model.eval()
        logger.info("Loaded DiffSinger checkpoint from %s", checkpoint_path)
        return model

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def num_parameters(self, trainable_only: bool = True) -> int:
        """Return the number of (trainable) parameters."""
        if trainable_only:
            return sum(p.numel() for p in self.parameters() if p.requires_grad)
        return sum(p.numel() for p in self.parameters())

    def __repr__(self) -> str:
        total = self.num_parameters(trainable_only=False)
        trainable = self.num_parameters(trainable_only=True)
        return (
            f"DiffSinger("
            f"hidden_dim={self.hidden_dim}, "
            f"n_mels={self.n_mels}, "
            f"sample_rate={self.sample_rate}, "
            f"total_params={total:,}, "
            f"trainable_params={trainable:,})"
        )
