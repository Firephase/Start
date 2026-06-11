#!/usr/bin/env python3
"""
Train WavLM-ECAPA speaker encoder with GE2E loss.
Usage: python training/train_speaker_encoder.py --config configs/training/speaker_training.yaml
"""

import argparse
import collections
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
from torch import Tensor
from torch.utils.data import DataLoader, Dataset, Sampler
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from tqdm import tqdm

from training.losses.speaker_loss import GeneralizedEndToEndLoss

log = logging.getLogger(__name__)

try:
    import wandb
    HAS_WANDB = True
except ImportError:
    HAS_WANDB = False

try:
    from transformers import WavLMModel, WavLMConfig
    HAS_WAVLM = True
except ImportError:
    HAS_WAVLM = False
    log.warning("transformers not installed; WavLM backbone will be unavailable.")


# ---------------------------------------------------------------------------
# Speaker Encoder Model
# ---------------------------------------------------------------------------

class ECAPAHead(nn.Module):
    """
    Lightweight ECAPA-TDNN projection head applied on top of WavLM features.

    Aggregates frame-level features into a fixed-size speaker embedding using
    attentive statistics pooling.

    Args:
        input_dim: Dimension of incoming frame features.
        hidden_dim: Intermediate projection dimension.
        embed_dim: Final embedding dimension.
    """

    def __init__(
        self,
        input_dim: int = 1024,
        hidden_dim: int = 512,
        embed_dim: int = 256,
    ) -> None:
        super().__init__()
        self.proj = nn.Linear(input_dim, hidden_dim)

        # Attentive statistics pooling
        self.attention = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.Tanh(),
            nn.Linear(hidden_dim // 4, 1),
        )

        # Final embedding projection (mean + std -> 2 * hidden_dim)
        self.bn = nn.BatchNorm1d(hidden_dim * 2)
        self.fc = nn.Linear(hidden_dim * 2, embed_dim)

    def forward(self, x: Tensor) -> Tensor:
        """
        Args:
            x: Frame features of shape (B, T, input_dim).

        Returns:
            Speaker embedding of shape (B, embed_dim).
        """
        h = F.relu(self.proj(x))  # (B, T, hidden_dim)

        # Attentive statistics pooling
        attn = self.attention(h)  # (B, T, 1)
        attn = F.softmax(attn, dim=1)  # (B, T, 1)

        mean = (attn * h).sum(dim=1)                            # (B, hidden_dim)
        std = ((attn * (h - mean.unsqueeze(1)) ** 2).sum(dim=1) + 1e-6).sqrt()

        pooled = torch.cat([mean, std], dim=-1)                 # (B, 2*hidden_dim)
        pooled = self.bn(pooled)
        embed = self.fc(pooled)                                  # (B, embed_dim)
        return embed


class WavLMECAPASpeakerEncoder(nn.Module):
    """
    Speaker encoder: WavLM backbone + ECAPA attentive pooling head.

    Produces L2-normalized speaker embeddings.

    Args:
        wavlm_model_name: HuggingFace model id for WavLM.
        embed_dim: Output embedding dimensionality.
        freeze_feature_extractor: Freeze WavLM CNN feature extractor.
        freeze_transformer_layers: Number of WavLM transformer layers to freeze (0 = none).
    """

    def __init__(
        self,
        wavlm_model_name: str = "microsoft/wavlm-large",
        embed_dim: int = 256,
        freeze_feature_extractor: bool = True,
        freeze_transformer_layers: int = 6,
    ) -> None:
        super().__init__()

        if not HAS_WAVLM:
            raise ImportError("transformers is required for WavLM backbone.")

        self.wavlm = WavLMModel.from_pretrained(wavlm_model_name)
        hidden_size = self.wavlm.config.hidden_size

        if freeze_feature_extractor:
            self.wavlm.feature_extractor._freeze_parameters()

        for i, layer in enumerate(self.wavlm.encoder.layers):
            if i < freeze_transformer_layers:
                for param in layer.parameters():
                    param.requires_grad = False

        self.head = ECAPAHead(
            input_dim=hidden_size,
            hidden_dim=512,
            embed_dim=embed_dim,
        )

    def forward(self, input_values: Tensor, attention_mask: Optional[Tensor] = None) -> Tensor:
        """
        Args:
            input_values: Raw waveform (B, T), normalized to [-1, 1].
            attention_mask: Optional mask (B, T).

        Returns:
            L2-normalized speaker embeddings (B, embed_dim).
        """
        outputs = self.wavlm(
            input_values=input_values,
            attention_mask=attention_mask,
            output_hidden_states=False,
        )
        hidden = outputs.last_hidden_state  # (B, T', hidden_size)
        embed = self.head(hidden)           # (B, embed_dim)
        return F.normalize(embed, p=2, dim=-1)


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

class SpeakerDataset(Dataset):
    """
    Multi-corpus speaker dataset combining VoxCeleb2, LibriSpeech, and VocalSet.

    Builds a flat index of (speaker_id, utterance_path) pairs, assigns
    integer class labels, and supports per-speaker lookup for GE2E batching.

    Args:
        corpora: Dict mapping corpus name to root directory path.
                 Supported keys: "voxceleb2", "librispeech", "vocalset".
        sample_rate: Target sample rate.
        max_duration: Maximum utterance duration in seconds (longer clips are trimmed).
        min_duration: Minimum acceptable duration in seconds.
    """

    def __init__(
        self,
        corpora: Dict[str, str],
        sample_rate: int = 16000,
        max_duration: float = 10.0,
        min_duration: float = 1.5,
    ) -> None:
        self.sample_rate = sample_rate
        self.max_samples = int(max_duration * sample_rate)
        self.min_samples = int(min_duration * sample_rate)

        # utterances: list of (global_speaker_idx, path)
        self.utterances: List[Tuple[int, Path]] = []
        # speaker_to_utts: speaker_idx -> [list of utterance global indices]
        self.speaker_to_utts: Dict[int, List[int]] = collections.defaultdict(list)

        self._load_all(corpora)

    def _load_all(self, corpora: Dict[str, str]) -> None:
        speaker_label_counter = 0

        for corpus_name, root in corpora.items():
            root_path = Path(root)
            if not root_path.exists():
                log.warning("%s root not found: %s", corpus_name, root_path)
                continue

            if corpus_name == "voxceleb2":
                n = self._load_voxceleb2(root_path, speaker_label_counter)
            elif corpus_name == "librispeech":
                n = self._load_librispeech(root_path, speaker_label_counter)
            elif corpus_name == "vocalset":
                n = self._load_vocalset(root_path, speaker_label_counter)
            else:
                log.warning("Unknown corpus: %s", corpus_name)
                n = 0

            speaker_label_counter += n
            log.info("[%s] added %d speakers", corpus_name, n)

        self.num_speakers = speaker_label_counter
        log.info(
            "Total: %d utterances, %d speakers",
            len(self.utterances),
            self.num_speakers,
        )

    def _add_speaker_wavs(
        self,
        wavs: List[Path],
        speaker_idx: int,
    ) -> None:
        for wav in wavs:
            utt_idx = len(self.utterances)
            self.utterances.append((speaker_idx, wav))
            self.speaker_to_utts[speaker_idx].append(utt_idx)

    def _load_voxceleb2(self, root: Path, base_idx: int) -> int:
        """
        VoxCeleb2 layout: {root}/dev/aac/{speaker_id}/{video_id}/{utt_id}.m4a
        """
        dev_root = root / "dev" / "aac"
        if not dev_root.exists():
            dev_root = root  # fallback
        n_speakers = 0
        for spk_dir in sorted(dev_root.iterdir()):
            if not spk_dir.is_dir():
                continue
            wavs = list(spk_dir.rglob("*.wav")) + list(spk_dir.rglob("*.m4a"))
            if not wavs:
                continue
            spk_idx = base_idx + n_speakers
            self._add_speaker_wavs(wavs, spk_idx)
            n_speakers += 1
        return n_speakers

    def _load_librispeech(self, root: Path, base_idx: int) -> int:
        """
        LibriSpeech layout: {root}/{subset}/{speaker_id}/{chapter_id}/{utt}.flac
        """
        n_speakers = 0
        local_spk_map: Dict[str, int] = {}
        for flac in root.rglob("*.flac"):
            spk_str = flac.parent.parent.name
            if spk_str not in local_spk_map:
                local_spk_map[spk_str] = base_idx + n_speakers
                n_speakers += 1
            spk_idx = local_spk_map[spk_str]
            utt_idx = len(self.utterances)
            self.utterances.append((spk_idx, flac))
            self.speaker_to_utts[spk_idx].append(utt_idx)
        return n_speakers

    def _load_vocalset(self, root: Path, base_idx: int) -> int:
        """
        VocalSet layout: {root}/{singer}/{technique}/{vowel}/*.wav
        """
        n_speakers = 0
        local_spk_map: Dict[str, int] = {}
        for wav in root.rglob("*.wav"):
            singer = wav.parts[-4] if len(wav.parts) >= 4 else wav.parent.name
            if singer not in local_spk_map:
                local_spk_map[singer] = base_idx + n_speakers
                n_speakers += 1
            spk_idx = local_spk_map[singer]
            utt_idx = len(self.utterances)
            self.utterances.append((spk_idx, wav))
            self.speaker_to_utts[spk_idx].append(utt_idx)
        return n_speakers

    def __len__(self) -> int:
        return len(self.utterances)

    def __getitem__(self, idx: int) -> Dict[str, Tensor]:
        speaker_idx, path = self.utterances[idx]
        audio = self._load_wav(path)
        return {
            "audio": audio,
            "speaker_id": torch.tensor(speaker_idx, dtype=torch.long),
        }

    def _load_wav(self, path: Path) -> Tensor:
        try:
            import torchaudio
            waveform, sr = torchaudio.load(str(path))
            if sr != self.sample_rate:
                waveform = torchaudio.functional.resample(waveform, sr, self.sample_rate)
            # Mono
            if waveform.size(0) > 1:
                waveform = waveform.mean(dim=0, keepdim=True)
            waveform = waveform.squeeze(0)  # (T,)
            # Trim / pad
            if waveform.size(0) > self.max_samples:
                start = random.randint(0, waveform.size(0) - self.max_samples)
                waveform = waveform[start : start + self.max_samples]
            elif waveform.size(0) < self.min_samples:
                waveform = F.pad(waveform, (0, self.min_samples - waveform.size(0)))
            return waveform  # (T,)
        except Exception as exc:
            log.warning("Failed to load %s: %s", path, exc)
            return torch.zeros(self.max_samples)


# ---------------------------------------------------------------------------
# GE2E Batch Sampler
# ---------------------------------------------------------------------------

class GE2ESampler(Sampler):
    """
    Batch sampler for GE2E training.

    Samples N speakers per batch, then M utterances per speaker.
    Output batch indices form N*M consecutive utterance indices.

    Args:
        speaker_to_utts: Mapping from speaker index to list of utterance indices.
        n_speakers: Number of speakers per batch.
        m_utterances: Number of utterances per speaker.
        drop_speakers_below: Skip speakers with fewer utterances than this.
    """

    def __init__(
        self,
        speaker_to_utts: Dict[int, List[int]],
        n_speakers: int = 64,
        m_utterances: int = 10,
        drop_speakers_below: int = 5,
    ) -> None:
        self.n = n_speakers
        self.m = m_utterances
        # Filter speakers with enough utterances
        self.eligible = [
            spk for spk, utts in speaker_to_utts.items()
            if len(utts) >= drop_speakers_below
        ]
        self.speaker_to_utts = {
            spk: speaker_to_utts[spk] for spk in self.eligible
        }
        log.info(
            "GE2ESampler: %d eligible speakers (N=%d, M=%d)",
            len(self.eligible),
            n_speakers,
            m_utterances,
        )

    def __iter__(self):
        speakers = self.eligible.copy()
        random.shuffle(speakers)
        for i in range(0, len(speakers) - self.n + 1, self.n):
            batch_spks = speakers[i : i + self.n]
            batch_indices: List[int] = []
            for spk in batch_spks:
                utts = self.speaker_to_utts[spk]
                chosen = random.choices(utts, k=self.m)
                batch_indices.extend(chosen)
            yield batch_indices

    def __len__(self) -> int:
        return len(self.eligible) // self.n


def _ge2e_collate(batch: List[Dict[str, Tensor]]) -> Dict[str, Tensor]:
    max_len = max(item["audio"].size(0) for item in batch)
    audios = torch.stack(
        [F.pad(item["audio"], (0, max_len - item["audio"].size(0))) for item in batch]
    )
    labels = torch.stack([item["speaker_id"] for item in batch])
    return {"audio": audios, "speaker_id": labels}


# ---------------------------------------------------------------------------
# Evaluation: Equal Error Rate
# ---------------------------------------------------------------------------

@torch.no_grad()
def compute_eer(
    model: nn.Module,
    val_dataset: SpeakerDataset,
    n_trials: int = 5000,
    device: torch.device = torch.device("cpu"),
) -> float:
    """
    Estimate Equal Error Rate (EER) via random trial pairs.

    Args:
        model: Speaker encoder to evaluate.
        val_dataset: Validation dataset.
        n_trials: Number of speaker pairs to evaluate.
        device: Torch device.

    Returns:
        EER as a float in [0, 1].
    """
    model.eval()
    from sklearn.metrics import roc_curve  # type: ignore

    # Sample embeddings for a subset of speakers
    spk_to_embed: Dict[int, List[Tensor]] = collections.defaultdict(list)
    max_utts_per_spk = 5

    for spk_idx, utt_indices in val_dataset.speaker_to_utts.items():
        chosen = random.sample(utt_indices, min(max_utts_per_spk, len(utt_indices)))
        for utt_idx in chosen:
            item = val_dataset[utt_idx]
            audio = item["audio"].unsqueeze(0).to(device)
            embed = model(audio)
            spk_to_embed[spk_idx].append(embed.squeeze(0).cpu())

    eligible_spks = [s for s, e in spk_to_embed.items() if len(e) >= 2]
    if len(eligible_spks) < 2:
        log.warning("Not enough speakers for EER computation.")
        return float("nan")

    scores: List[float] = []
    labels: List[int] = []

    for _ in range(n_trials):
        if random.random() < 0.5:
            # Same-speaker pair (positive)
            spk = random.choice(eligible_spks)
            e1, e2 = random.sample(spk_to_embed[spk], 2)
            label = 1
        else:
            # Different-speaker pair (negative)
            spk1, spk2 = random.sample(eligible_spks, 2)
            e1 = random.choice(spk_to_embed[spk1])
            e2 = random.choice(spk_to_embed[spk2])
            label = 0

        score = F.cosine_similarity(e1.unsqueeze(0), e2.unsqueeze(0)).item()
        scores.append(score)
        labels.append(label)

    fpr, tpr, thresholds = roc_curve(labels, scores)
    fnr = 1.0 - tpr
    eer_threshold_idx = np.nanargmin(np.abs(fnr - fpr))
    eer = float(np.mean([fpr[eer_threshold_idx], fnr[eer_threshold_idx]]))
    return eer


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

class SpeakerEncoderTrainer:
    """
    Full training loop for WavLM-ECAPA speaker encoder.

    Config keys (training.speaker):
        wavlm_model:            "microsoft/wavlm-large"
        embed_dim:              256
        freeze_feature_extractor: true
        freeze_transformer_layers: 6
        n_speakers_per_batch:   64
        m_utterances_per_speaker: 10
        ge2e_variant:           "softmax"
        lr:                     1e-4
        weight_decay:           0.01
        max_steps:              100000
        warmup_steps:           2000
        val_every:              5000
        eer_n_trials:           10000
        output_dir:             "checkpoints/speaker_encoder"
        save_every:             5000
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.train_cfg = config.get("training", {})
        self.data_cfg = config.get("data", {})
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self._build_model()
        self._build_datasets()
        self._build_optimizer()

        if HAS_WANDB and config.get("wandb", {}).get("enabled", True):
            wandb.init(
                project=config.get("wandb", {}).get("project", "speaker-encoder"),
                config=config,
            )

    def _build_model(self) -> None:
        t = self.train_cfg
        self.model = WavLMECAPASpeakerEncoder(
            wavlm_model_name=t.get("wavlm_model", "microsoft/wavlm-large"),
            embed_dim=t.get("embed_dim", 256),
            freeze_feature_extractor=t.get("freeze_feature_extractor", True),
            freeze_transformer_layers=t.get("freeze_transformer_layers", 6),
        ).to(self.device)

        self.ge2e_loss = GeneralizedEndToEndLoss(
            variant=t.get("ge2e_variant", "softmax")
        ).to(self.device)

        total = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        log.info("Trainable parameters: %d", total)

    def _build_datasets(self) -> None:
        corpora = self.data_cfg.get("corpora", {})
        sample_rate = self.data_cfg.get("sample_rate", 16000)

        self.train_dataset = SpeakerDataset(
            corpora=corpora,
            sample_rate=sample_rate,
            max_duration=self.data_cfg.get("max_duration", 10.0),
            min_duration=self.data_cfg.get("min_duration", 1.5),
        )

        t = self.train_cfg
        sampler = GE2ESampler(
            speaker_to_utts=self.train_dataset.speaker_to_utts,
            n_speakers=t.get("n_speakers_per_batch", 64),
            m_utterances=t.get("m_utterances_per_speaker", 10),
        )
        self.loader = DataLoader(
            self.train_dataset,
            batch_sampler=sampler,
            num_workers=self.data_cfg.get("num_workers", 8),
            collate_fn=_ge2e_collate,
            pin_memory=True,
        )

        # Validation: use a held-out subset of speakers
        # Simple approach: reserve last 10% of speakers
        all_spks = list(self.train_dataset.speaker_to_utts.keys())
        val_spks = set(all_spks[int(0.9 * len(all_spks)):])
        self.val_dataset = SpeakerDataset(
            corpora=corpora,
            sample_rate=sample_rate,
            max_duration=self.data_cfg.get("max_duration", 10.0),
            min_duration=self.data_cfg.get("min_duration", 1.5),
        )
        # Filter to val speakers only (in-place for simplicity)
        self.val_dataset.utterances = [
            (spk, p) for spk, p in self.val_dataset.utterances if spk in val_spks
        ]
        self.val_dataset.speaker_to_utts = {
            spk: utts for spk, utts in self.val_dataset.speaker_to_utts.items()
            if spk in val_spks
        }

    def _build_optimizer(self) -> None:
        params = list(self.model.parameters()) + list(self.ge2e_loss.parameters())
        self.optimizer = AdamW(
            params,
            lr=self.train_cfg.get("lr", 1e-4),
            weight_decay=self.train_cfg.get("weight_decay", 0.01),
        )
        max_steps = self.train_cfg.get("max_steps", 100_000)
        self.scheduler = CosineAnnealingLR(
            self.optimizer,
            T_max=max_steps,
            eta_min=1e-6,
        )

    def train(self) -> None:
        max_steps = self.train_cfg.get("max_steps", 100_000)
        val_every = self.train_cfg.get("val_every", 5_000)
        save_every = self.train_cfg.get("save_every", 5_000)
        output_dir = Path(self.train_cfg.get("output_dir", "checkpoints/speaker_encoder"))
        output_dir.mkdir(parents=True, exist_ok=True)

        self.model.train()
        global_step = 0

        pbar = tqdm(total=max_steps, desc="Speaker encoder training")

        while global_step < max_steps:
            for batch in self.loader:
                if global_step >= max_steps:
                    break

                audio: Tensor = batch["audio"].to(self.device)    # (N*M, T)
                labels: Tensor = batch["speaker_id"].to(self.device)  # (N*M,)

                self.optimizer.zero_grad()

                with torch.autocast("cuda", dtype=torch.bfloat16, enabled=torch.cuda.is_available()):
                    embeddings = self.model(audio)  # (N*M, embed_dim)
                    loss = self.ge2e_loss(embeddings, labels)

                loss.backward()
                nn.utils.clip_grad_norm_(
                    list(self.model.parameters()) + list(self.ge2e_loss.parameters()),
                    max_norm=3.0,
                )
                self.optimizer.step()
                self.scheduler.step()

                global_step += 1
                pbar.update(1)
                pbar.set_postfix(loss=f"{loss.item():.4f}")

                if HAS_WANDB and wandb.run is not None:
                    wandb.log(
                        {
                            "train/ge2e_loss": loss.item(),
                            "train/lr": self.scheduler.get_last_lr()[0],
                        },
                        step=global_step,
                    )

                if global_step % val_every == 0:
                    eer = compute_eer(
                        self.model,
                        self.val_dataset,
                        n_trials=self.train_cfg.get("eer_n_trials", 5000),
                        device=self.device,
                    )
                    log.info("Step %d | EER: %.4f", global_step, eer)
                    if HAS_WANDB and wandb.run is not None:
                        wandb.log({"val/eer": eer}, step=global_step)
                    self.model.train()

                if global_step % save_every == 0:
                    self._save(output_dir, global_step)

        pbar.close()
        self._save(output_dir, global_step, is_final=True)
        log.info("Training complete.")

    def _save(self, output_dir: Path, step: int, is_final: bool = False) -> None:
        tag = "final" if is_final else f"step-{step:07d}"
        ckpt_path = output_dir / f"{tag}.pt"
        torch.save(
            {
                "step": step,
                "model_state": self.model.state_dict(),
                "ge2e_state": self.ge2e_loss.state_dict(),
                "optimizer_state": self.optimizer.state_dict(),
                "config": self.config,
            },
            ckpt_path,
        )
        log.info("Checkpoint saved: %s", ckpt_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train WavLM-ECAPA speaker encoder.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/training/speaker_training.yaml",
        help="Path to YAML config.",
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
    with open(path) as f:
        return yaml.safe_load(f)


def main() -> None:
    args = _parse_args()
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)

    config = _load_config(args.config)
    trainer = SpeakerEncoderTrainer(config)

    if args.resume:
        ckpt = torch.load(args.resume, map_location="cpu")
        trainer.model.load_state_dict(ckpt["model_state"])
        trainer.ge2e_loss.load_state_dict(ckpt["ge2e_state"])
        trainer.optimizer.load_state_dict(ckpt["optimizer_state"])
        log.info("Resumed from %s (step %d)", args.resume, ckpt.get("step", 0))

    trainer.train()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    main()
