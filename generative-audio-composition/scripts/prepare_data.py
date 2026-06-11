#!/usr/bin/env python3
"""
prepare_data.py
===============
Data preparation pipeline for generative audio composition training.

Steps
-----
1. Scan dataset directories for audio files.
2. Run Montreal Forced Aligner (MFA) to extract phoneme alignments for
   singing data (OpenSinger, VocalSet).
3. Extract and cache acoustic features per file:
      - Log-mel spectrogram
      - Fundamental frequency (F0) contour
      - Energy envelope
      - Speaker embeddings (WavLM-ECAPA)
4. Split into train / val / test sets.
5. Write manifest JSON files consumed by the DataLoader.

Usage
-----
    python scripts/prepare_data.py \\
        --data-dir /data/audio \\
        --output-dir /data/processed \\
        --manifest-dir /data/manifests \\
        --speaker-encoder-ckpt /app/models/speaker_encoder/model.pt \\
        --workers 8
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SAMPLE_RATE    = 22050
HOP_LENGTH     = 256
WIN_LENGTH     = 1024
N_FFT          = 1024
N_MELS         = 80
FMIN           = 0.0
FMAX           = 8000.0
F0_MIN         = 65.0     # Hz — low limit for F0 (below bass voice)
F0_MAX         = 1100.0   # Hz — upper limit for F0 (above soprano)

SPLIT_RATIOS   = {"train": 0.85, "val": 0.075, "test": 0.075}

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}

# Datasets with phoneme alignment requirements
ALIGNMENT_DATASETS = {"opensinger", "vocalset"}

# ── Argument parsing ──────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prepare training data for generative audio composition",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--data-dir",    required=True, help="Root directory of raw datasets")
    p.add_argument("--output-dir",  required=True, help="Directory for extracted features (.npy)")
    p.add_argument("--manifest-dir",required=True, help="Directory for manifest JSON files")
    p.add_argument(
        "--speaker-encoder-ckpt",
        default=None,
        help="Path to WavLMSpeakerEncoder checkpoint for embedding extraction",
    )
    p.add_argument("--workers", type=int, default=os.cpu_count() or 4, help="Parallel worker count")
    p.add_argument("--seed",    type=int, default=42,   help="Random seed for splits")
    p.add_argument("--device",  default="cuda",         help="cuda or cpu (for speaker encoder)")
    p.add_argument(
        "--skip-mfa",
        action="store_true",
        help="Skip MFA alignment (use if TextGrid files already exist)",
    )
    p.add_argument(
        "--skip-features",
        action="store_true",
        help="Skip feature extraction (use if .npy caches already exist)",
    )
    p.add_argument(
        "--datasets",
        nargs="+",
        default=["opensinger", "vocalset", "fma", "musdb18hq"],
        help="Datasets to include",
    )
    return p.parse_args()


# =============================================================================
# Step 1 — Dataset scanning
# =============================================================================


# Datasets for which BPM/key extraction is appropriate (music, not singing)
MUSIC_DATASETS = {"fma", "musdb18hq", "musdb", "mtg-jamendo", "gtzan"}

# Datasets for which G2P / phoneme alignment is appropriate
SINGING_DATASETS = {"opensinger", "vocalset"}


def extract_bpm_and_key(wav: np.ndarray, sr: int = SAMPLE_RATE) -> dict[str, Any]:
    """
    Extract tempo (BPM) and musical key from an audio waveform.

    Uses librosa for BPM estimation and the Krumhansl-Schmuckler algorithm
    (via chroma CQT) for key detection.

    Parameters
    ----------
    wav : np.ndarray
        Mono float32 waveform.
    sr : int
        Sample rate.

    Returns
    -------
    dict with keys:
        ``bpm``         : float  – estimated tempo in BPM
        ``key``         : str    – e.g. "G major"
        ``mode``        : str    – "major" or "minor"
        ``key_confidence`` : float – Pearson r in [0, 1]
    """
    import librosa

    result: dict[str, Any] = {
        "bpm": None,
        "key": None,
        "mode": None,
        "key_confidence": None,
    }

    # BPM estimation
    try:
        tempo, _ = librosa.beat.beat_track(y=wav, sr=sr, units="time")
        result["bpm"] = round(float(np.atleast_1d(tempo)[0]), 2)
    except Exception as exc:
        logger.debug("BPM extraction failed: %s", exc)

    # Key estimation via Krumhansl-Schmuckler
    try:
        chroma = librosa.feature.chroma_cqt(y=wav, sr=sr, bins_per_octave=36)
        chroma_mean = chroma.mean(axis=1)  # (12,)

        KS_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        KS_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
        NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

        best_r = -np.inf
        best_root = 0
        best_mode = "major"

        for root in range(12):
            r_maj = float(np.corrcoef(chroma_mean, np.roll(KS_MAJOR, root))[0, 1])
            r_min = float(np.corrcoef(chroma_mean, np.roll(KS_MINOR, root))[0, 1])
            if r_maj > best_r:
                best_r, best_root, best_mode = r_maj, root, "major"
            if r_min > best_r:
                best_r, best_root, best_mode = r_min, root, "minor"

        result["key"] = f"{NOTE_NAMES[best_root]} {best_mode}"
        result["mode"] = best_mode
        result["key_confidence"] = round(float(np.clip(best_r, 0.0, 1.0)), 4)
    except Exception as exc:
        logger.debug("Key detection failed: %s", exc)

    return result


def scan_dataset(dataset_dir: Path, dataset_name: str) -> list[dict[str, Any]]:
    """
    Recursively scan ``dataset_dir`` for audio files.

    Returns
    -------
    list of dicts with keys:
        ``path``, ``dataset``, ``speaker_id``, ``duration_approx``
    """
    records: list[dict[str, Any]] = []

    for audio_path in sorted(dataset_dir.rglob("*")):
        if audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue

        # Attempt to infer speaker ID from directory structure
        # Convention: dataset_dir/<speaker_id>/<utterance>.wav
        rel = audio_path.relative_to(dataset_dir)
        speaker_id = rel.parts[0] if len(rel.parts) > 1 else "unknown"

        records.append(
            {
                "path": str(audio_path),
                "dataset": dataset_name,
                "speaker_id": f"{dataset_name}_{speaker_id}",
                "duration_approx": None,  # filled during feature extraction
            }
        )

    logger.info("  %s: found %d audio files in %s", dataset_name, len(records), dataset_dir)
    return records


def scan_all_datasets(data_dir: Path, datasets: list[str]) -> list[dict[str, Any]]:
    """Scan all requested dataset directories."""
    all_records: list[dict[str, Any]] = []

    for dataset_name in datasets:
        dataset_dir = data_dir / dataset_name
        if not dataset_dir.exists():
            logger.warning("Dataset directory not found, skipping: %s", dataset_dir)
            continue
        records = scan_dataset(dataset_dir, dataset_name)
        all_records.extend(records)

    logger.info("Total audio files found: %d", len(all_records))
    return all_records


# =============================================================================
# Step 2 — MFA phoneme alignment
# =============================================================================


def run_mfa_alignment(data_dir: Path, dataset_name: str, mfa_output_dir: Path) -> None:
    """
    Run Montreal Forced Aligner on ``data_dir`` for ``dataset_name``.

    Expects MFA to be installed and available on PATH.
    Produces TextGrid files in ``mfa_output_dir``.
    """
    corpus_dir = data_dir / dataset_name
    textgrid_dir = mfa_output_dir / dataset_name
    textgrid_dir.mkdir(parents=True, exist_ok=True)

    # Check if TextGrids already exist
    existing = list(textgrid_dir.rglob("*.TextGrid"))
    if existing:
        logger.info("MFA: TextGrids already exist for %s (%d files) — skipping", dataset_name, len(existing))
        return

    logger.info("Running MFA alignment for %s …", dataset_name)

    # MFA align command:
    #   mfa align <corpus_dir> english_mfa english_mfa <output_dir>
    # The acoustic model and dictionary are assumed to be pre-downloaded via:
    #   mfa model download acoustic english_mfa
    #   mfa model download dictionary english_mfa
    cmd = [
        "mfa", "align",
        str(corpus_dir),
        "english_mfa",          # dictionary
        "english_mfa",          # acoustic model
        str(textgrid_dir),
        "--clean",
        "--num_jobs", str(min(8, os.cpu_count() or 4)),
        "--quiet",
    ]

    logger.info("MFA command: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0:
            logger.warning(
                "MFA alignment for %s exited with code %d:\n%s",
                dataset_name,
                result.returncode,
                result.stderr[-2000:],
            )
        else:
            produced = list(textgrid_dir.rglob("*.TextGrid"))
            logger.info("MFA alignment complete for %s: %d TextGrids", dataset_name, len(produced))
    except FileNotFoundError:
        logger.warning(
            "MFA not found on PATH — phoneme alignment skipped for %s. "
            "Install with: pip install montreal-forced-aligner",
            dataset_name,
        )
    except subprocess.TimeoutExpired:
        logger.error("MFA alignment timed out for %s", dataset_name)


def run_mfa_for_all(data_dir: Path, datasets: list[str], mfa_output_dir: Path) -> None:
    for dataset_name in datasets:
        if dataset_name in ALIGNMENT_DATASETS:
            run_mfa_alignment(data_dir, dataset_name, mfa_output_dir)


# =============================================================================
# Step 3 — Feature extraction
# =============================================================================


def extract_mel_spectrogram(wav: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Return log-mel spectrogram of shape (n_mels, T)."""
    import librosa

    mel = librosa.feature.melspectrogram(
        y=wav, sr=sr,
        n_fft=N_FFT, hop_length=HOP_LENGTH, win_length=WIN_LENGTH,
        n_mels=N_MELS, fmin=FMIN, fmax=FMAX,
        power=1.0,  # amplitude, not power
    )
    log_mel = np.log(np.clip(mel, 1e-5, None))
    return log_mel.astype(np.float32)


def extract_f0(wav: np.ndarray, sr: int = SAMPLE_RATE) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract F0 and voiced flag using pyin.

    Returns
    -------
    f0 : (T,) float32  — fundamental frequency in Hz (0 for unvoiced)
    voiced : (T,) bool
    """
    import librosa

    f0, voiced_flag, _ = librosa.pyin(
        wav,
        fmin=F0_MIN,
        fmax=F0_MAX,
        sr=sr,
        hop_length=HOP_LENGTH,
        fill_na=0.0,
    )
    f0 = np.nan_to_num(f0, nan=0.0).astype(np.float32)
    return f0, voiced_flag.astype(bool)


def extract_energy(wav: np.ndarray) -> np.ndarray:
    """
    Frame-level RMS energy envelope of shape (T,).
    Computed from the same frames as the mel spectrogram.
    """
    import librosa

    rms = librosa.feature.rms(y=wav, frame_length=WIN_LENGTH, hop_length=HOP_LENGTH)
    return rms[0].astype(np.float32)


def _extract_features_for_record(
    record: dict[str, Any],
    output_dir: Path,
    speaker_encoder,
    device,
) -> dict[str, Any] | None:
    """
    Extract all features for a single audio file and cache them as .npy files.

    Returns an updated record dict (with cache paths and duration).
    """
    import librosa
    import torch

    audio_path = Path(record["path"])
    cache_stem = output_dir / record["dataset"] / record["speaker_id"] / audio_path.stem
    cache_stem.parent.mkdir(parents=True, exist_ok=True)

    mel_path     = cache_stem.with_suffix(".mel.npy")
    f0_path      = cache_stem.with_suffix(".f0.npy")
    energy_path  = cache_stem.with_suffix(".energy.npy")
    spk_path     = cache_stem.with_suffix(".spk.npy")

    try:
        wav, _ = librosa.load(str(audio_path), sr=SAMPLE_RATE, mono=True)
    except Exception as exc:
        logger.warning("Failed to load %s: %s", audio_path, exc)
        return None

    duration = float(len(wav)) / SAMPLE_RATE
    if duration < 0.5:
        logger.debug("Skipping very short file: %s (%.2fs)", audio_path, duration)
        return None

    # Mel spectrogram
    if not mel_path.exists():
        mel = extract_mel_spectrogram(wav)
        np.save(str(mel_path), mel)

    # F0
    if not f0_path.exists():
        f0, voiced = extract_f0(wav)
        np.save(str(f0_path), np.stack([f0, voiced.astype(np.float32)], axis=0))

    # Energy
    if not energy_path.exists():
        energy = extract_energy(wav)
        np.save(str(energy_path), energy)

    # Speaker embedding
    if not spk_path.exists() and speaker_encoder is not None:
        try:
            import torch

            wav_16k = librosa.resample(wav, orig_sr=SAMPLE_RATE, target_sr=16000)
            t = torch.from_numpy(wav_16k).unsqueeze(0).to(device)
            with torch.no_grad():
                emb = speaker_encoder(t).squeeze(0).cpu().numpy()
            np.save(str(spk_path), emb)
        except Exception as exc:
            logger.warning("Speaker embedding failed for %s: %s", audio_path, exc)

    # BPM / key extraction for music datasets (not singing datasets)
    bpm_info: dict[str, Any] = {}
    if record.get("dataset", "") in MUSIC_DATASETS:
        try:
            bpm_info = extract_bpm_and_key(wav, sr=SAMPLE_RATE)
        except Exception as exc:
            logger.debug("BPM/key extraction failed for %s: %s", audio_path, exc)

    updated = {
        **record,
        "duration": round(duration, 3),
        "mel_path": str(mel_path),
        "f0_path": str(f0_path),
        "energy_path": str(energy_path),
        "spk_path": str(spk_path) if spk_path.exists() else None,
        **bpm_info,
    }
    return updated


def extract_all_features(
    records: list[dict[str, Any]],
    output_dir: Path,
    speaker_encoder_ckpt: str | None,
    device_str: str,
    num_workers: int,
) -> list[dict[str, Any]]:
    """Extract features for all records, optionally in parallel."""
    import torch

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load speaker encoder (once, in the main process — passed as a closure)
    speaker_encoder = None
    device = torch.device(device_str if torch.cuda.is_available() and device_str == "cuda" else "cpu")

    if speaker_encoder_ckpt:
        logger.info("Loading speaker encoder from %s …", speaker_encoder_ckpt)
        try:
            from models.speaker_encoder.model import WavLMSpeakerEncoder  # type: ignore[import]

            speaker_encoder = WavLMSpeakerEncoder.from_pretrained(speaker_encoder_ckpt)
            speaker_encoder = speaker_encoder.to(device).eval()
            logger.info("Speaker encoder loaded on %s", device)
        except Exception as exc:
            logger.warning("Could not load speaker encoder: %s — skipping embeddings", exc)

    logger.info("Extracting features for %d files …", len(records))
    updated_records: list[dict[str, Any]] = []
    failed = 0

    # Feature extraction is CPU-bound (librosa) — use processes for parallelism.
    # However speaker encoder needs the main GPU, so we run it sequentially.
    if speaker_encoder is not None or num_workers == 1:
        # Sequential path (required when speaker encoder is active)
        for idx, record in enumerate(records):
            result = _extract_features_for_record(record, output_dir, speaker_encoder, device)
            if result is not None:
                updated_records.append(result)
            else:
                failed += 1
            if (idx + 1) % 500 == 0:
                logger.info("  %d / %d processed, %d skipped", idx + 1, len(records), failed)
    else:
        # Parallel path (no GPU speaker encoder)
        from functools import partial

        fn = partial(
            _extract_features_for_record,
            output_dir=output_dir,
            speaker_encoder=None,
            device=device,
        )
        with ProcessPoolExecutor(max_workers=num_workers) as pool:
            futures = {pool.submit(fn, r): r for r in records}
            for done_idx, future in enumerate(as_completed(futures)):
                try:
                    result = future.result()
                    if result is not None:
                        updated_records.append(result)
                    else:
                        failed += 1
                except Exception as exc:
                    failed += 1
                    logger.warning("Feature extraction error: %s", exc)
                if (done_idx + 1) % 500 == 0:
                    logger.info("  %d / %d processed", done_idx + 1, len(records))

    logger.info(
        "Feature extraction complete: %d succeeded, %d skipped/failed",
        len(updated_records),
        failed,
    )
    return updated_records


# =============================================================================
# Step 4 — Train / val / test split
# =============================================================================


def split_records(
    records: list[dict[str, Any]],
    seed: int,
    ratios: dict[str, float] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Split records into train/val/test, stratified by speaker_id.

    Returns dict with keys ``train``, ``val``, ``test``.
    """
    if ratios is None:
        ratios = SPLIT_RATIOS

    rng = random.Random(seed)

    # Group by speaker
    by_speaker: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_speaker.setdefault(rec["speaker_id"], []).append(rec)

    splits: dict[str, list[dict[str, Any]]] = {"train": [], "val": [], "test": []}

    for speaker_id, speaker_records in by_speaker.items():
        rng.shuffle(speaker_records)
        n = len(speaker_records)
        n_val  = max(1, round(n * ratios["val"]))
        n_test = max(1, round(n * ratios["test"]))
        n_train = n - n_val - n_test

        splits["test"].extend(speaker_records[:n_test])
        splits["val"].extend(speaker_records[n_test : n_test + n_val])
        splits["train"].extend(speaker_records[n_test + n_val :])

    for split_name, split_records_list in splits.items():
        rng.shuffle(split_records_list)
        logger.info("  %s: %d samples", split_name, len(split_records_list))

    return splits


# =============================================================================
# Step 5 — Write manifest files
# =============================================================================


def write_manifests(
    splits: dict[str, list[dict[str, Any]]],
    manifest_dir: Path,
) -> None:
    """Write one JSON manifest per split."""
    manifest_dir.mkdir(parents=True, exist_ok=True)

    for split_name, records in splits.items():
        manifest_path = manifest_dir / f"{split_name}.json"
        with open(manifest_path, "w") as fh:
            json.dump(records, fh, indent=2)
        total_hours = sum(r.get("duration", 0.0) for r in records) / 3600.0
        logger.info(
            "Wrote %s manifest: %d samples, %.2f hours → %s",
            split_name,
            len(records),
            total_hours,
            manifest_path,
        )


# =============================================================================
# Entry point
# =============================================================================


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    data_dir    = Path(args.data_dir)
    output_dir  = Path(args.output_dir)
    manifest_dir = Path(args.manifest_dir)

    if not data_dir.exists():
        sys.exit(f"Data directory not found: {data_dir}")

    # ── Step 1: Scan ──────────────────────────────────────────────────────────
    logger.info("Step 1: Scanning dataset directories …")
    records = scan_all_datasets(data_dir, args.datasets)

    if not records:
        sys.exit("No audio files found. Check --data-dir and --datasets arguments.")

    # ── Step 2: MFA alignment ─────────────────────────────────────────────────
    if not args.skip_mfa:
        logger.info("Step 2: Running MFA phoneme alignment …")
        mfa_output_dir = output_dir / "textgrids"
        run_mfa_for_all(data_dir, args.datasets, mfa_output_dir)
    else:
        logger.info("Step 2: MFA skipped (--skip-mfa)")

    # ── Step 3: Feature extraction ────────────────────────────────────────────
    if not args.skip_features:
        logger.info("Step 3: Extracting acoustic features …")
        records = extract_all_features(
            records,
            output_dir=output_dir / "features",
            speaker_encoder_ckpt=args.speaker_encoder_ckpt,
            device_str=args.device,
            num_workers=args.workers,
        )
    else:
        logger.info("Step 3: Feature extraction skipped (--skip-features)")

    # ── Step 4: Split ─────────────────────────────────────────────────────────
    logger.info("Step 4: Splitting into train/val/test …")
    splits = split_records(records, seed=args.seed)

    # ── Step 5: Write manifests ───────────────────────────────────────────────
    logger.info("Step 5: Writing manifests …")
    write_manifests(splits, manifest_dir)

    # ── Statistics report ─────────────────────────────────────────────────────
    _print_statistics(records, splits)

    logger.info("Data preparation complete.")


def _print_statistics(
    all_records: list[dict[str, Any]],
    splits: dict[str, list[dict[str, Any]]],
) -> None:
    """Print a summary table of dataset statistics to stdout."""
    SEP = "─" * 70

    print(f"\n{SEP}")
    print("  Dataset Preparation Statistics")
    print(f"{SEP}")

    # Per-dataset breakdown
    by_dataset: dict[str, list[dict[str, Any]]] = {}
    for rec in all_records:
        ds = rec.get("dataset", "unknown")
        by_dataset.setdefault(ds, []).append(rec)

    print(f"\n  {'Dataset':<20} {'Files':>8} {'Hours':>8} {'Speakers':>10}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*10}")

    total_files = 0
    total_hours = 0.0
    for ds_name in sorted(by_dataset):
        ds_recs = by_dataset[ds_name]
        n_files = len(ds_recs)
        hours = sum(r.get("duration", 0.0) for r in ds_recs) / 3600.0
        n_speakers = len({r.get("speaker_id", "unknown") for r in ds_recs})
        print(f"  {ds_name:<20} {n_files:>8d} {hours:>8.2f} {n_speakers:>10d}")
        total_files += n_files
        total_hours += hours

    print(f"  {'TOTAL':<20} {total_files:>8d} {total_hours:>8.2f}")

    # Split summary
    print(f"\n{SEP}")
    print("  Train / Val / Test Split")
    print(f"{SEP}")
    print(f"\n  {'Split':<10} {'Files':>8} {'Hours':>8}")
    print(f"  {'-'*10} {'-'*8} {'-'*8}")

    for split_name in ("train", "val", "test"):
        sp_recs = splits.get(split_name, [])
        n = len(sp_recs)
        h = sum(r.get("duration", 0.0) for r in sp_recs) / 3600.0
        print(f"  {split_name:<10} {n:>8d} {h:>8.2f}")

    # BPM statistics for music datasets
    music_recs = [r for r in all_records if r.get("dataset") in MUSIC_DATASETS and r.get("bpm")]
    if music_recs:
        bpms = np.array([r["bpm"] for r in music_recs], dtype=np.float32)
        print(f"\n{SEP}")
        print("  Music Metadata (BPM / Key)")
        print(f"{SEP}")
        print(f"\n  BPM stats: mean={bpms.mean():.1f}, std={bpms.std():.1f}, "
              f"min={bpms.min():.1f}, max={bpms.max():.1f}")

        key_counts: dict[str, int] = {}
        for r in music_recs:
            k = r.get("key", "unknown")
            if k:
                key_counts[k] = key_counts.get(k, 0) + 1

        top_keys = sorted(key_counts.items(), key=lambda x: -x[1])[:5]
        print(f"  Top keys: {', '.join(f'{k} ({v})' for k, v in top_keys)}")

    print(f"\n{SEP}\n")


if __name__ == "__main__":
    main()
