#!/usr/bin/env python3
"""
Fine-tune MusicGen-large on curated music dataset using PEFT LoRA adapters.
Usage: python training/train_musicgen.py --config configs/training/musicgen_training.yaml
"""

import argparse
import logging
import math
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
from torch.utils.data import DataLoader, Dataset, ConcatDataset
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from tqdm import tqdm

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Try importing optional heavy dependencies gracefully
# ---------------------------------------------------------------------------

try:
    from transformers import AutoProcessor, MusicgenForConditionalGeneration
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False
    log.warning("transformers not installed; model loading will fail.")

try:
    from peft import LoraConfig, get_peft_model, TaskType, PeftModel
    HAS_PEFT = True
except ImportError:
    HAS_PEFT = False
    log.warning("peft not installed; LoRA wrapping will be skipped.")

try:
    import wandb
    HAS_WANDB = True
except ImportError:
    HAS_WANDB = False


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

class FMADataset(Dataset):
    """
    FMA Large dataset (106 k tracks).

    Expected directory layout:
        {root}/tracks/          — audio files in {track_id:06d}.mp3 format
        {root}/metadata/tracks.csv
        {root}/metadata/genres.csv

    Returns dicts with keys:
        audio            (torch.Tensor) — (1, samples) float32 waveform
        text_description (str)          — generated text prompt
        genre            (str)          — primary genre label
        duration         (float)        — clip duration in seconds
    """

    SEGMENT_DURATION: float = 30.0   # seconds per clip

    def __init__(
        self,
        root: str,
        split: str = "train",
        sample_rate: int = 32000,
        segment_duration: float = 30.0,
        max_samples: Optional[int] = None,
    ) -> None:
        self.root = Path(root)
        self.split = split
        self.sample_rate = sample_rate
        self.segment_samples = int(segment_duration * sample_rate)
        self.items: List[Dict[str, Any]] = []
        self._load_metadata(max_samples)

    # ------------------------------------------------------------------

    def _load_metadata(self, max_samples: Optional[int]) -> None:
        """Parse tracks.csv and genres.csv to build the item list."""
        tracks_csv = self.root / "metadata" / "tracks.csv"
        genres_csv = self.root / "metadata" / "genres.csv"

        if not tracks_csv.exists():
            log.warning("FMA metadata not found at %s; using empty dataset.", tracks_csv)
            return

        try:
            import pandas as pd
        except ImportError:
            log.error("pandas is required for FMA metadata loading.")
            return

        # FMA tracks.csv has multi-level header rows; read with header=[0,1]
        tracks = pd.read_csv(tracks_csv, index_col=0, header=[0, 1])

        # Build genre id -> title map
        genre_map: Dict[int, str] = {}
        if genres_csv.exists():
            genres_df = pd.read_csv(genres_csv, index_col=0)
            genre_map = genres_df["title"].to_dict()

        # Filter by split
        split_col = ("set", "split")
        if split_col in tracks.columns:
            mask = tracks[split_col] == self.split
            tracks = tracks[mask]

        for track_id, row in tracks.iterrows():
            audio_path = self._track_path(track_id)
            if not audio_path.exists():
                continue

            genre_id = None
            genre_name = "unknown"
            try:
                genre_id = int(row[("track", "genre_top")])
                genre_name = genre_map.get(genre_id, str(genre_id))
            except (KeyError, ValueError, TypeError):
                pass

            title = str(row.get(("track", "title"), "")).strip() or "unknown"
            artist = str(row.get(("artist", "name"), "")).strip() or "unknown"
            tags = str(row.get(("track", "tags"), "")).strip()

            text_desc = self._build_text(title, artist, genre_name, tags)

            self.items.append(
                {
                    "path": audio_path,
                    "track_id": track_id,
                    "genre": genre_name,
                    "text": text_desc,
                }
            )
            if max_samples and len(self.items) >= max_samples:
                break

        log.info("[FMA] %d tracks loaded (split=%s)", len(self.items), self.split)

    def _track_path(self, track_id: int) -> Path:
        tid_str = f"{track_id:06d}"
        return self.root / "tracks" / tid_str[:3] / f"{tid_str}.mp3"

    @staticmethod
    def _build_text(title: str, artist: str, genre: str, tags: str) -> str:
        """Construct a natural-language prompt from track metadata."""
        parts = []
        if genre and genre != "unknown":
            parts.append(f"a {genre} track")
        if artist and artist != "unknown":
            parts.append(f"by {artist}")
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()][:3]
            if tag_list:
                parts.append("with themes of " + ", ".join(tag_list))
        return " ".join(parts) if parts else "an instrumental music piece"

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        item = self.items[idx]
        audio = self._load_audio(item["path"])
        return {
            "audio": audio,
            "text_description": item["text"],
            "genre": item["genre"],
            "duration": audio.shape[-1] / self.sample_rate,
        }

    def _load_audio(self, path: Path) -> Tensor:
        """Load audio, resample, convert to mono, and extract a random 30-s segment."""
        try:
            import torchaudio
            waveform, sr = torchaudio.load(str(path))
            if sr != self.sample_rate:
                waveform = torchaudio.functional.resample(waveform, sr, self.sample_rate)
            # Convert to mono
            if waveform.size(0) > 1:
                waveform = waveform.mean(dim=0, keepdim=True)
            # Random 30-second segment
            total = waveform.size(-1)
            if total >= self.segment_samples:
                start = random.randint(0, total - self.segment_samples)
                waveform = waveform[:, start : start + self.segment_samples]
            else:
                waveform = F.pad(waveform, (0, self.segment_samples - total))
            return waveform  # (1, segment_samples)
        except Exception as exc:
            log.warning("Failed to load %s: %s", path, exc)
            return torch.zeros(1, self.segment_samples)


class MUSDB18Dataset(Dataset):
    """
    MUSDB18 stems dataset for multi-track conditioning.

    Expected directory:
        {root}/train/{track_name}/mixture.wav
        {root}/train/{track_name}/vocals.wav  (etc.)

    Returns mono mixture + auto-generated text prompt.
    """

    STEMS = ("mixture", "drums", "bass", "other", "vocals")

    def __init__(
        self,
        root: str,
        split: str = "train",
        sample_rate: int = 32000,
        segment_duration: float = 30.0,
    ) -> None:
        self.root = Path(root)
        self.split = split
        self.sample_rate = sample_rate
        self.segment_samples = int(segment_duration * sample_rate)
        self.items = self._collect_tracks()

    def _collect_tracks(self) -> List[Path]:
        split_dir = self.root / self.split
        if not split_dir.exists():
            log.warning("MUSDB18 split directory not found: %s", split_dir)
            return []
        tracks = sorted(split_dir.iterdir())
        log.info("[MUSDB18] %d tracks (split=%s)", len(tracks), self.split)
        return tracks

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        track_dir = self.items[idx]
        audio = self._load_stem(track_dir / "mixture.wav")
        active_stems = [
            s for s in self.STEMS[1:]
            if (track_dir / f"{s}.wav").exists()
        ]
        text = self._build_text(track_dir.name, active_stems)
        return {
            "audio": audio,
            "text_description": text,
            "genre": "mixed",
            "duration": audio.shape[-1] / self.sample_rate,
        }

    def _build_text(self, name: str, stems: List[str]) -> str:
        parts = ["a music mixture"]
        if stems:
            parts.append("containing " + ", ".join(stems))
        return " ".join(parts)

    def _load_stem(self, path: Path) -> Tensor:
        try:
            import torchaudio
            w, sr = torchaudio.load(str(path))
            if sr != self.sample_rate:
                w = torchaudio.functional.resample(w, sr, self.sample_rate)
            if w.size(0) > 1:
                w = w.mean(dim=0, keepdim=True)
            total = w.size(-1)
            if total >= self.segment_samples:
                start = random.randint(0, total - self.segment_samples)
                w = w[:, start : start + self.segment_samples]
            else:
                w = F.pad(w, (0, self.segment_samples - total))
            return w
        except Exception as exc:
            log.warning("Failed to load %s: %s", path, exc)
            return torch.zeros(1, self.segment_samples)


class MTGJamendoDataset(Dataset):
    """
    MTG-Jamendo dataset with mood/instrument tags used as text prompts.

    Expected directory:
        {root}/audio/          — mp3 files
        {root}/metadata/       — autotagging_moodtheme-*.tsv
    """

    def __init__(
        self,
        root: str,
        split: str = "train",
        sample_rate: int = 32000,
        segment_duration: float = 30.0,
    ) -> None:
        self.root = Path(root)
        self.split = split
        self.sample_rate = sample_rate
        self.segment_samples = int(segment_duration * sample_rate)
        self.items: List[Dict[str, Any]] = []
        self._load_metadata()

    def _load_metadata(self) -> None:
        meta_dir = self.root / "metadata"
        if not meta_dir.exists():
            log.warning("MTG-Jamendo metadata not found at %s", meta_dir)
            return
        tsv_files = list(meta_dir.glob(f"autotagging_moodtheme-{self.split}*.tsv"))
        if not tsv_files:
            tsv_files = list(meta_dir.glob("autotagging_moodtheme*.tsv"))
        for tsv in tsv_files:
            with open(tsv) as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) < 2:
                        continue
                    track_id = parts[0]
                    tags = parts[1:]
                    audio_path = self.root / "audio" / f"{track_id}.mp3"
                    if not audio_path.exists():
                        continue
                    text = self._tags_to_text(tags)
                    self.items.append({"path": audio_path, "text": text, "tags": tags})
        log.info("[MTG-Jamendo] %d tracks (split=%s)", len(self.items), self.split)

    @staticmethod
    def _tags_to_text(tags: List[str]) -> str:
        clean = [t.replace("---", " ").replace("-", " ") for t in tags[:5]]
        if not clean:
            return "an ambient music piece"
        return "music with " + ", ".join(clean) + " mood"

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        item = self.items[idx]
        audio = self._load_audio(item["path"])
        return {
            "audio": audio,
            "text_description": item["text"],
            "genre": "mood",
            "duration": audio.shape[-1] / self.sample_rate,
        }

    def _load_audio(self, path: Path) -> Tensor:
        try:
            import torchaudio
            w, sr = torchaudio.load(str(path))
            if sr != self.sample_rate:
                w = torchaudio.functional.resample(w, sr, self.sample_rate)
            if w.size(0) > 1:
                w = w.mean(dim=0, keepdim=True)
            total = w.size(-1)
            if total >= self.segment_samples:
                start = random.randint(0, total - self.segment_samples)
                w = w[:, start : start + self.segment_samples]
            else:
                w = F.pad(w, (0, self.segment_samples - total))
            return w
        except Exception as exc:
            log.warning("Failed to load %s: %s", path, exc)
            return torch.zeros(1, self.segment_samples)


# ---------------------------------------------------------------------------
# Collate
# ---------------------------------------------------------------------------

def _collate_music(batch: List[Dict[str, Any]]) -> Dict[str, Any]:
    audios = torch.stack([item["audio"] for item in batch])  # (B, 1, T)
    texts = [item["text_description"] for item in batch]
    genres = [item["genre"] for item in batch]
    return {"audio": audios, "text": texts, "genre": genres}


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

class MusicGenFinetuner:
    """
    Fine-tune MusicGen-large with LoRA adapters via HuggingFace PEFT.

    Config keys (training.musicgen):
        model_name:         "facebook/musicgen-large"
        lora_r:             16
        lora_alpha:         32
        lora_dropout:       0.05
        target_modules:     ["q_proj", "v_proj"]
        lr:                 3e-5
        batch_size:         4
        accumulation_steps: 8
        max_steps:          50000
        warmup_steps:       500
        output_dir:         "checkpoints/musicgen"
        save_every:         2000
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
                project=config.get("wandb", {}).get("project", "musicgen-finetune"),
                config=config,
            )

    def _build_model(self) -> None:
        if not HAS_TRANSFORMERS:
            raise ImportError("transformers is required.")

        model_name = self.train_cfg.get("model_name", "facebook/musicgen-large")
        log.info("Loading %s ...", model_name)
        self.processor = AutoProcessor.from_pretrained(model_name)
        self.model = MusicgenForConditionalGeneration.from_pretrained(
            model_name, torch_dtype=torch.bfloat16
        )

        if HAS_PEFT:
            lora_cfg = LoraConfig(
                r=self.train_cfg.get("lora_r", 16),
                lora_alpha=self.train_cfg.get("lora_alpha", 32),
                lora_dropout=self.train_cfg.get("lora_dropout", 0.05),
                target_modules=self.train_cfg.get(
                    "target_modules", ["q_proj", "v_proj"]
                ),
                bias="none",
            )
            self.model = get_peft_model(self.model, lora_cfg)
            self.model.print_trainable_parameters()
        else:
            log.warning("peft not available; training all parameters.")

        self.model = self.model.to(self.device)

    def _build_datasets(self) -> None:
        datasets: List[Dataset] = []

        if self.data_cfg.get("fma_root"):
            datasets.append(
                FMADataset(
                    self.data_cfg["fma_root"],
                    split="train",
                    sample_rate=self.data_cfg.get("sample_rate", 32000),
                    segment_duration=self.data_cfg.get("segment_duration", 30.0),
                    max_samples=self.data_cfg.get("fma_max_samples", None),
                )
            )
        if self.data_cfg.get("musdb_root"):
            datasets.append(
                MUSDB18Dataset(
                    self.data_cfg["musdb_root"],
                    split="train",
                    sample_rate=self.data_cfg.get("sample_rate", 32000),
                    segment_duration=self.data_cfg.get("segment_duration", 30.0),
                )
            )
        if self.data_cfg.get("mtg_root"):
            datasets.append(
                MTGJamendoDataset(
                    self.data_cfg["mtg_root"],
                    split="train",
                    sample_rate=self.data_cfg.get("sample_rate", 32000),
                    segment_duration=self.data_cfg.get("segment_duration", 30.0),
                )
            )

        if not datasets:
            raise RuntimeError("No datasets configured. Set fma_root / musdb_root / mtg_root.")

        combined = ConcatDataset(datasets)
        self.loader = DataLoader(
            combined,
            batch_size=self.train_cfg.get("batch_size", 4),
            shuffle=True,
            num_workers=self.data_cfg.get("num_workers", 4),
            collate_fn=_collate_music,
            pin_memory=True,
            drop_last=True,
        )
        log.info("Total training samples: %d", len(combined))

    def _build_optimizer(self) -> None:
        lr = self.train_cfg.get("lr", 3e-5)
        self.optimizer = AdamW(
            filter(lambda p: p.requires_grad, self.model.parameters()),
            lr=lr,
            betas=(0.9, 0.999),
            weight_decay=self.train_cfg.get("weight_decay", 0.01),
        )
        max_steps = self.train_cfg.get("max_steps", 50_000)
        warmup = self.train_cfg.get("warmup_steps", 500)
        self.scheduler = self._cosine_with_warmup(max_steps, warmup)

    def _cosine_with_warmup(self, max_steps: int, warmup_steps: int):
        def lr_lambda(step: int) -> float:
            if step < warmup_steps:
                return float(step) / max(1, warmup_steps)
            progress = (step - warmup_steps) / max(1, max_steps - warmup_steps)
            return max(0.0, 0.5 * (1.0 + math.cos(math.pi * progress)))
        from torch.optim.lr_scheduler import LambdaLR
        return LambdaLR(self.optimizer, lr_lambda)

    # ------------------------------------------------------------------
    # Main training loop
    # ------------------------------------------------------------------

    def train(self) -> None:
        max_steps = self.train_cfg.get("max_steps", 50_000)
        accum_steps = self.train_cfg.get("accumulation_steps", 8)
        save_every = self.train_cfg.get("save_every", 2000)
        output_dir = Path(self.train_cfg.get("output_dir", "checkpoints/musicgen"))
        output_dir.mkdir(parents=True, exist_ok=True)

        self.model.train()
        global_step = 0
        accum_loss = 0.0
        self.optimizer.zero_grad()

        pbar = tqdm(total=max_steps, desc="MusicGen fine-tuning")

        while global_step < max_steps:
            for batch in self.loader:
                if global_step >= max_steps:
                    break

                audio: Tensor = batch["audio"].to(self.device, dtype=torch.bfloat16)
                texts: List[str] = batch["text"]

                # Encode text prompts
                inputs = self.processor(
                    text=texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=256,
                )
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                # MusicGen uses EnCodec tokens as decoder input; encode audio
                # The model handles this internally when audio_values is passed.
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    outputs = self.model(
                        **inputs,
                        audio_values=audio,
                        labels=None,  # will be derived from audio_values internally
                    )
                    loss = outputs.loss / accum_steps

                loss.backward()
                accum_loss += loss.item()

                if (global_step + 1) % accum_steps == 0:
                    torch.nn.utils.clip_grad_norm_(
                        self.model.parameters(),
                        max_norm=self.train_cfg.get("grad_clip", 1.0),
                    )
                    self.optimizer.step()
                    self.scheduler.step()
                    self.optimizer.zero_grad()

                    if HAS_WANDB and wandb.run is not None:
                        wandb.log(
                            {
                                "train/loss": accum_loss,
                                "train/lr": self.scheduler.get_last_lr()[0],
                            },
                            step=global_step,
                        )
                    accum_loss = 0.0

                global_step += 1
                pbar.update(1)
                pbar.set_postfix(loss=f"{loss.item() * accum_steps:.4f}")

                if global_step % save_every == 0:
                    self._save_checkpoint(output_dir, global_step)

        pbar.close()
        self._save_checkpoint(output_dir, global_step, is_final=True)
        log.info("Training complete.")

    def _save_checkpoint(
        self,
        output_dir: Path,
        step: int,
        is_final: bool = False,
    ) -> None:
        tag = "final" if is_final else f"step-{step:07d}"
        save_path = output_dir / tag

        if HAS_PEFT and isinstance(self.model, PeftModel):
            # Save only LoRA adapter weights for efficient deployment
            self.model.save_pretrained(str(save_path))
            log.info("Saved LoRA adapter to %s", save_path)
        else:
            self.model.save_pretrained(str(save_path))
            log.info("Saved full model to %s", save_path)

        if HAS_WANDB and wandb.run is not None:
            wandb.log({"checkpoint": str(save_path)}, step=step)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune MusicGen with LoRA.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/training/musicgen_training.yaml",
        help="Path to YAML config.",
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
    finetuner = MusicGenFinetuner(config)
    finetuner.train()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    main()
