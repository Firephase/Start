#!/usr/bin/env python3
"""
Train DiffSinger SVS model.
Usage: python training/train_svs.py --config configs/training/svs_training.yaml
"""

import argparse
import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml
import lightning as L
import wandb
from torch import Tensor
from torch.utils.data import DataLoader, Dataset, ConcatDataset
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from lightning.pytorch.callbacks import ModelCheckpoint, LearningRateMonitor
from lightning.pytorch.loggers import WandbLogger
from lightning.pytorch.strategies import DDPStrategy

# Local imports (assumed to exist in the project)
from training.losses.mel_loss import MultiScaleMelLoss, MelLoss
from training.losses.discriminator import (
    MultiPeriodDiscriminator,
    MultiScaleDiscriminator,
    discriminator_loss,
    generator_loss,
    feature_loss,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Placeholder model interfaces (implement in models/ package)
# ---------------------------------------------------------------------------

class DiffSingerModel(nn.Module):
    """
    Placeholder for the full DiffSinger model.

    Expected interface:
        forward(phonemes, durations, f0, energy, speaker_id)
            -> {"mel": Tensor, "dur_pred": Tensor, "f0_pred": Tensor, "energy_pred": Tensor}
        diffusion_loss(mel_target, phonemes, durations, f0, energy, speaker_id)
            -> Tensor  (training-time diffusion objective)
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__()
        # Instantiate from config in a real implementation
        self.config = config

    def forward(self, *args: Any, **kwargs: Any) -> Dict[str, Tensor]:
        raise NotImplementedError("Replace with real DiffSinger implementation.")

    def diffusion_loss(self, *args: Any, **kwargs: Any) -> Tensor:
        raise NotImplementedError("Replace with real DiffSinger implementation.")


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------

class _BaseAudioDataset(Dataset):
    """Shared base for SVS datasets."""

    def __init__(
        self,
        root: str,
        config: Dict[str, Any],
        split: str = "train",
    ) -> None:
        self.root = Path(root)
        self.config = config
        self.split = split
        self.sample_rate: int = config.get("sample_rate", 22050)
        self.n_mels: int = config.get("n_mels", 80)
        self.hop_length: int = config.get("hop_length", 256)
        self.items: List[Dict[str, Any]] = []
        self._load_metadata()

    def _load_metadata(self) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> Dict[str, Tensor]:
        raise NotImplementedError


class OpenSingerSVSDataset(_BaseAudioDataset):
    """
    OpenSinger dataset for SVS training.

    Expected directory layout:
        {root}/{singer_id}/{song_name}/{sentence_id}.wav
        {root}/{singer_id}/{song_name}/{sentence_id}.txt

    Returns tensors for: mel, f0, energy, duration, phonemes, speaker_id.
    """

    def _load_metadata(self) -> None:
        for singer_dir in sorted(self.root.iterdir()):
            if not singer_dir.is_dir():
                continue
            singer_id = singer_dir.name
            for song_dir in sorted(singer_dir.iterdir()):
                if not song_dir.is_dir():
                    continue
                for wav_path in sorted(song_dir.glob("*.wav")):
                    txt_path = wav_path.with_suffix(".txt")
                    if not txt_path.exists():
                        continue
                    self.items.append(
                        {
                            "wav": wav_path,
                            "txt": txt_path,
                            "singer_id": singer_id,
                            "song": song_dir.name,
                        }
                    )
        log.info("[OpenSinger] %d items loaded (split=%s)", len(self.items), self.split)

    def __getitem__(self, idx: int) -> Dict[str, Tensor]:
        item = self.items[idx]
        # In a real implementation: load audio, extract mel/f0/energy/phonemes
        # Here we return dummy tensors with correct shapes.
        T = 128  # example mel frames
        P = 20   # example phoneme length
        return {
            "mel": torch.zeros(self.n_mels, T),
            "f0": torch.zeros(T),
            "energy": torch.zeros(T),
            "duration": torch.zeros(P),
            "phonemes": torch.zeros(P, dtype=torch.long),
            "speaker_id": torch.tensor(int(item["singer_id"].replace("singer", "0") or 0), dtype=torch.long),
        }


class VocalSetSVSDataset(_BaseAudioDataset):
    """
    VocalSet dataset adapter.

    Directory layout:
        {root}/{singer}/{technique}/{vowel}/{exercise}.wav
    """

    def _load_metadata(self) -> None:
        for singer_dir in sorted(self.root.iterdir()):
            if not singer_dir.is_dir():
                continue
            for wav_path in singer_dir.rglob("*.wav"):
                self.items.append(
                    {
                        "wav": wav_path,
                        "singer_id": singer_dir.name,
                    }
                )
        log.info("[VocalSet] %d items loaded (split=%s)", len(self.items), self.split)

    def __getitem__(self, idx: int) -> Dict[str, Tensor]:
        item = self.items[idx]
        T = 128
        P = 20
        singer_hash = hash(item["singer_id"]) % 1000
        return {
            "mel": torch.zeros(self.n_mels, T),
            "f0": torch.zeros(T),
            "energy": torch.zeros(T),
            "duration": torch.zeros(P),
            "phonemes": torch.zeros(P, dtype=torch.long),
            "speaker_id": torch.tensor(singer_hash, dtype=torch.long),
        }


def _collate_fn(batch: List[Dict[str, Tensor]]) -> Dict[str, Tensor]:
    """Pad variable-length tensors in the batch."""
    keys = batch[0].keys()
    out: Dict[str, Any] = {}
    for key in keys:
        tensors = [item[key] for item in batch]
        if tensors[0].dim() == 0:
            out[key] = torch.stack(tensors)
        elif tensors[0].dim() == 1:
            max_len = max(t.size(0) for t in tensors)
            padded = torch.stack(
                [F.pad(t, (0, max_len - t.size(0))) for t in tensors]
            )
            out[key] = padded
        else:  # 2-D (mel)
            max_len = max(t.size(1) for t in tensors)
            padded = torch.stack(
                [F.pad(t, (0, max_len - t.size(1))) for t in tensors]
            )
            out[key] = padded
    return out


# ---------------------------------------------------------------------------
# Lightning DataModule
# ---------------------------------------------------------------------------

class SVSDataModule(L.LightningDataModule):
    """
    DataModule for SVS training.

    Supports OpenSinger, VocalSet, and additional custom datasets specified
    in the configuration file.

    Config keys:
        data:
            opensinger_root: /path/to/opensinger
            vocalset_root:   /path/to/vocalset
            custom_datasets: []  # list of {type: ..., root: ...}
            batch_size: 16
            num_workers: 8
            sample_rate: 22050
            n_mels: 80
            hop_length: 256
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__()
        self.config = config
        self.data_cfg = config["data"]

    def setup(self, stage: Optional[str] = None) -> None:
        datasets_train: List[Dataset] = []
        datasets_val: List[Dataset] = []

        dataset_cfg = self.data_cfg

        if dataset_cfg.get("opensinger_root"):
            datasets_train.append(
                OpenSingerSVSDataset(dataset_cfg["opensinger_root"], dataset_cfg, split="train")
            )
            datasets_val.append(
                OpenSingerSVSDataset(dataset_cfg["opensinger_root"], dataset_cfg, split="val")
            )

        if dataset_cfg.get("vocalset_root"):
            datasets_train.append(
                VocalSetSVSDataset(dataset_cfg["vocalset_root"], dataset_cfg, split="train")
            )
            datasets_val.append(
                VocalSetSVSDataset(dataset_cfg["vocalset_root"], dataset_cfg, split="val")
            )

        if not datasets_train:
            raise RuntimeError(
                "No datasets configured. Set at least one of: "
                "opensinger_root, vocalset_root in config.data"
            )

        self.train_dataset = ConcatDataset(datasets_train)
        self.val_dataset = ConcatDataset(datasets_val)

        log.info(
            "Dataset sizes: train=%d, val=%d",
            len(self.train_dataset),
            len(self.val_dataset),
        )

    def train_dataloader(self) -> DataLoader:
        return DataLoader(
            self.train_dataset,
            batch_size=self.data_cfg.get("batch_size", 16),
            shuffle=True,
            num_workers=self.data_cfg.get("num_workers", 8),
            pin_memory=True,
            collate_fn=_collate_fn,
            drop_last=True,
            persistent_workers=True,
        )

    def val_dataloader(self) -> DataLoader:
        return DataLoader(
            self.val_dataset,
            batch_size=self.data_cfg.get("batch_size", 16),
            shuffle=False,
            num_workers=self.data_cfg.get("num_workers", 8),
            pin_memory=True,
            collate_fn=_collate_fn,
            drop_last=False,
            persistent_workers=True,
        )


# ---------------------------------------------------------------------------
# Lightning Module
# ---------------------------------------------------------------------------

class SVSLightningModule(L.LightningModule):
    """
    DiffSinger SVS Lightning training module.

    Training objective:
        L_total = L_diffusion + L_dur + L_pitch + L_energy + L_adv + L_feat

    where:
        L_diffusion  — DDPM noise prediction loss (denoising score matching)
        L_dur        — Duration predictor L2 loss
        L_pitch      — F0 predictor L1 loss
        L_energy     — Energy predictor L1 loss
        L_adv        — GAN generator adversarial loss (MPD + MSD)
        L_feat       — Feature matching loss

    Discriminators are updated every step via manual optimization.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__()
        self.save_hyperparameters(config)
        self.config = config
        self.automatic_optimization = False  # manual for GAN training

        model_cfg = config.get("model", {})
        self.generator = DiffSingerModel(model_cfg)
        self.mpd = MultiPeriodDiscriminator()
        self.msd = MultiScaleDiscriminator()

        self.mel_loss = MultiScaleMelLoss(
            sample_rate=config["data"].get("sample_rate", 22050),
            n_mels=config["data"].get("n_mels", 80),
        )
        self.train_cfg = config.get("training", {})

    # ------------------------------------------------------------------
    # Optimizers & schedulers
    # ------------------------------------------------------------------

    def configure_optimizers(self):
        lr_gen = self.train_cfg.get("lr_generator", 2e-4)
        lr_disc = self.train_cfg.get("lr_discriminator", 2e-4)
        betas = tuple(self.train_cfg.get("betas", [0.8, 0.99]))
        weight_decay = self.train_cfg.get("weight_decay", 0.01)
        max_steps = self.train_cfg.get("max_steps", 300_000)

        opt_g = AdamW(
            self.generator.parameters(),
            lr=lr_gen,
            betas=betas,
            weight_decay=weight_decay,
        )
        opt_d = AdamW(
            list(self.mpd.parameters()) + list(self.msd.parameters()),
            lr=lr_disc,
            betas=betas,
            weight_decay=weight_decay,
        )

        sched_g = CosineAnnealingLR(opt_g, T_max=max_steps, eta_min=1e-6)
        sched_d = CosineAnnealingLR(opt_d, T_max=max_steps, eta_min=1e-6)

        return (
            [opt_g, opt_d],
            [
                {"scheduler": sched_g, "interval": "step"},
                {"scheduler": sched_d, "interval": "step"},
            ],
        )

    # ------------------------------------------------------------------
    # Training step
    # ------------------------------------------------------------------

    def training_step(
        self, batch: Dict[str, Tensor], batch_idx: int
    ) -> None:
        opt_g, opt_d = self.optimizers()
        sched_g, sched_d = self.lr_schedulers()

        mel_target: Tensor = batch["mel"]           # (B, n_mels, T)
        phonemes: Tensor = batch["phonemes"]        # (B, P)
        durations: Tensor = batch["duration"]       # (B, P)
        f0: Tensor = batch["f0"]                   # (B, T)
        energy: Tensor = batch["energy"]            # (B, T)
        speaker_id: Tensor = batch["speaker_id"]   # (B,)

        # ---- Generator forward ----------------------------------------
        # In a full implementation, generator returns predicted mel + auxiliary
        # targets. Here we illustrate the expected interface.
        try:
            outputs = self.generator(phonemes, durations, f0, energy, speaker_id)
            mel_pred: Tensor = outputs["mel"]
            dur_pred: Tensor = outputs.get("dur_pred", durations)
            f0_pred: Tensor = outputs.get("f0_pred", f0)
            energy_pred: Tensor = outputs.get("energy_pred", energy)
            diff_loss: Tensor = self.generator.diffusion_loss(
                mel_target, phonemes, durations, f0, energy, speaker_id
            )
        except NotImplementedError:
            # Stub path for testing the training harness
            mel_pred = mel_target.clone().detach().requires_grad_(True)
            dur_pred = durations
            f0_pred = f0
            energy_pred = energy
            diff_loss = torch.zeros(1, device=self.device)

        # Align lengths
        min_t = min(mel_pred.size(-1), mel_target.size(-1))
        mel_pred_t = mel_pred[..., :min_t]
        mel_target_t = mel_target[..., :min_t]

        # Duration loss
        loss_dur = F.mse_loss(dur_pred.float(), durations.float())

        # Pitch loss
        loss_pitch = F.l1_loss(f0_pred.float(), f0.float())

        # Energy loss
        loss_energy = F.l1_loss(energy_pred.float(), energy.float())

        # ---- Discriminator update --------------------------------------
        opt_d.zero_grad()

        # We need a 1-D waveform for the discriminators; use mel as proxy
        # In a full system the vocoder would produce waveforms here.
        # Here we sum across mel bins as a placeholder.
        wav_real = mel_target_t.sum(dim=1, keepdim=True)   # (B, 1, T)
        wav_fake = mel_pred_t.sum(dim=1, keepdim=True).detach()

        real_mpd, gen_mpd, rfm_mpd, gfm_mpd = self.mpd(wav_real, wav_fake)
        real_msd, gen_msd, rfm_msd, gfm_msd = self.msd(wav_real, wav_fake)

        loss_disc_mpd, _, _ = discriminator_loss(real_mpd, gen_mpd)
        loss_disc_msd, _, _ = discriminator_loss(real_msd, gen_msd)
        loss_disc = loss_disc_mpd + loss_disc_msd

        self.manual_backward(loss_disc)
        self.clip_gradients(opt_d, gradient_clip_val=1.0)
        opt_d.step()

        # ---- Generator update -----------------------------------------
        opt_g.zero_grad()

        wav_fake_g = mel_pred_t.sum(dim=1, keepdim=True)

        _, gen_mpd_g, rfm_mpd_g, gfm_mpd_g = self.mpd(wav_real, wav_fake_g)
        _, gen_msd_g, rfm_msd_g, gfm_msd_g = self.msd(wav_real, wav_fake_g)

        loss_gen_mpd, _ = generator_loss(gen_mpd_g)
        loss_gen_msd, _ = generator_loss(gen_msd_g)
        loss_feat_mpd = feature_loss(rfm_mpd_g, gfm_mpd_g)
        loss_feat_msd = feature_loss(rfm_msd_g, gfm_msd_g)

        loss_adv = loss_gen_mpd + loss_gen_msd
        loss_feat = loss_feat_mpd + loss_feat_msd

        w = self.train_cfg.get("loss_weights", {})
        loss_gen_total = (
            w.get("diffusion", 1.0) * diff_loss
            + w.get("duration", 1.0) * loss_dur
            + w.get("pitch", 1.0) * loss_pitch
            + w.get("energy", 0.5) * loss_energy
            + w.get("adversarial", 1.0) * loss_adv
            + w.get("feature", 2.0) * loss_feat
        )

        self.manual_backward(loss_gen_total)
        self.clip_gradients(opt_g, gradient_clip_val=1.0)
        opt_g.step()

        sched_g.step()
        sched_d.step()

        self.log_dict(
            {
                "train/loss_gen": loss_gen_total,
                "train/loss_disc": loss_disc,
                "train/loss_diffusion": diff_loss,
                "train/loss_dur": loss_dur,
                "train/loss_pitch": loss_pitch,
                "train/loss_energy": loss_energy,
                "train/loss_adv": loss_adv,
                "train/loss_feat": loss_feat,
            },
            on_step=True,
            on_epoch=False,
            prog_bar=True,
            sync_dist=True,
        )

    # ------------------------------------------------------------------
    # Validation step
    # ------------------------------------------------------------------

    def validation_step(
        self, batch: Dict[str, Tensor], batch_idx: int
    ) -> Dict[str, Tensor]:
        mel_target: Tensor = batch["mel"]
        phonemes: Tensor = batch["phonemes"]
        durations: Tensor = batch["duration"]
        f0: Tensor = batch["f0"]
        energy: Tensor = batch["energy"]
        speaker_id: Tensor = batch["speaker_id"]

        with torch.no_grad():
            try:
                outputs = self.generator(phonemes, durations, f0, energy, speaker_id)
                mel_pred = outputs["mel"]
            except NotImplementedError:
                mel_pred = mel_target.clone()

        min_t = min(mel_pred.size(-1), mel_target.size(-1))
        mel_pred = mel_pred[..., :min_t]
        mel_target_t = mel_target[..., :min_t]

        # Mel reconstruction loss (used as validation proxy metric)
        val_mel_loss = F.l1_loss(mel_pred, mel_target_t)
        self.log("val/mel_loss", val_mel_loss, sync_dist=True, prog_bar=True)

        # Log audio samples to W&B on first validation batch
        if batch_idx == 0 and self.logger is not None:
            self._log_audio_samples(mel_pred, mel_target_t)

        return {"val_mel_loss": val_mel_loss}

    def _log_audio_samples(
        self,
        mel_pred: Tensor,
        mel_target: Tensor,
        n_samples: int = 4,
    ) -> None:
        """Log mel spectrograms as W&B images."""
        if not isinstance(self.logger, WandbLogger):
            return
        import matplotlib.pyplot as plt

        n = min(n_samples, mel_pred.size(0))
        figs = []
        for i in range(n):
            fig, axes = plt.subplots(1, 2, figsize=(12, 3))
            axes[0].imshow(mel_target[i].cpu().numpy(), aspect="auto", origin="lower")
            axes[0].set_title("Target mel")
            axes[1].imshow(mel_pred[i].cpu().float().numpy(), aspect="auto", origin="lower")
            axes[1].set_title("Predicted mel")
            plt.tight_layout()
            figs.append(wandb.Image(fig))
            plt.close(fig)

        self.logger.experiment.log(
            {"val/mel_spectrograms": figs, "global_step": self.global_step}
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train DiffSinger SVS model.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/training/svs_training.yaml",
        help="Path to YAML training config.",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Path to checkpoint to resume from.",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _load_config(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main() -> None:
    args = _parse_args()
    L.seed_everything(args.seed, workers=True)

    config = _load_config(args.config)

    # Loggers & callbacks
    wandb_cfg = config.get("wandb", {})
    logger = WandbLogger(
        project=wandb_cfg.get("project", "generative-audio-svs"),
        name=wandb_cfg.get("run_name", None),
        config=config,
    )

    train_cfg = config.get("training", {})
    checkpoint_dir = train_cfg.get("checkpoint_dir", "checkpoints/svs")
    callbacks = [
        ModelCheckpoint(
            dirpath=checkpoint_dir,
            filename="svs-{epoch:04d}-{val/mel_loss:.4f}",
            monitor="val/mel_loss",
            mode="min",
            save_top_k=5,
            save_last=True,
        ),
        LearningRateMonitor(logging_interval="step"),
    ]

    trainer = L.Trainer(
        max_steps=train_cfg.get("max_steps", 300_000),
        accelerator="gpu",
        devices=train_cfg.get("devices", 8),
        strategy=DDPStrategy(find_unused_parameters=False),
        precision="bf16-mixed",
        gradient_clip_val=None,  # handled manually in training_step
        logger=logger,
        callbacks=callbacks,
        log_every_n_steps=train_cfg.get("log_every_n_steps", 50),
        val_check_interval=train_cfg.get("val_check_interval", 2000),
        accumulate_grad_batches=train_cfg.get("accumulate_grad_batches", 1),
        sync_batchnorm=True,
        benchmark=True,
    )

    model = SVSLightningModule(config)
    datamodule = SVSDataModule(config)

    trainer.fit(model, datamodule=datamodule, ckpt_path=args.resume)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
