#!/usr/bin/env python3
"""
evaluate.py
===========
Evaluate a trained generative audio composition checkpoint on a held-out
test set and print a summary table of audio quality metrics.

Metrics computed
----------------
- PESQ   : Perceptual Evaluation of Speech Quality (proxy MOS, wideband)
- STOI   : Short-Time Objective Intelligibility
- Speaker similarity : cosine similarity between WavLM speaker embeddings
- Pitch accuracy     : mean absolute error (MAE) of fundamental frequency (F0)
- WER                : Word Error Rate of generated lyrics vs. reference
- MCD                : Mel Cepstral Distortion

Usage
-----
    python scripts/evaluate.py \\
        --checkpoint /app/models/ckpt_epoch100.pt \\
        --test-manifest /data/manifests/test.json \\
        --output-dir /tmp/eval_outputs \\
        --device cuda
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import torch

warnings.filterwarnings("ignore", category=UserWarning)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SAMPLE_RATE = 22050   # model sample rate
SR_PESQ     = 16000   # PESQ requires 16 kHz
SR_SPEAKER  = 16000   # WavLM requires 16 kHz
F0_HOP      = 256     # hop length for CREPE / pyin
TARGET_SIM  = 0.85    # speaker similarity threshold


# =============================================================================
# Audio utilities
# =============================================================================


def load_audio(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Load audio file, resample to ``sr``, return mono float32 array."""
    import librosa

    wav, _ = librosa.load(path, sr=sr, mono=True)
    return wav.astype(np.float32)


def resample(wav: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    import librosa

    if orig_sr == target_sr:
        return wav
    return librosa.resample(wav, orig_sr=orig_sr, target_sr=target_sr)


# =============================================================================
# Metric functions
# =============================================================================


def compute_pesq(ref: np.ndarray, deg: np.ndarray, sr: int = SR_PESQ) -> float:
    """
    Compute PESQ (wideband) score in range [-0.5, 4.5].
    Requires the ``pesq`` package.
    """
    try:
        from pesq import pesq  # type: ignore[import]
    except ImportError:
        logger.warning("pesq package not installed — skipping PESQ")
        return float("nan")

    # Align lengths
    min_len = min(len(ref), len(deg))
    return float(pesq(sr, ref[:min_len], deg[:min_len], "wb"))


def compute_stoi(ref: np.ndarray, deg: np.ndarray, sr: int = SAMPLE_RATE) -> float:
    """Compute extended STOI (eSTOI) score in range [0, 1]."""
    try:
        from pystoi import stoi  # type: ignore[import]
    except ImportError:
        logger.warning("pystoi package not installed — skipping STOI")
        return float("nan")

    min_len = min(len(ref), len(deg))
    return float(stoi(ref[:min_len], deg[:min_len], sr, extended=True))


def compute_mcd(ref: np.ndarray, deg: np.ndarray, sr: int = SAMPLE_RATE, n_mfcc: int = 13) -> float:
    """
    Mel Cepstral Distortion (dB) — lower is better.
    MCD = (10 / ln(10)) * sqrt(2 * sum((mc_ref - mc_deg)^2))
    """
    import librosa

    C = 10.0 / np.log(10.0)

    def mfcc(wav: np.ndarray) -> np.ndarray:
        # Use log-mel MFCC coefficients 1..n_mfcc (skip C0)
        return librosa.feature.mfcc(y=wav, sr=sr, n_mfcc=n_mfcc + 1)[1:]

    mc_ref = mfcc(ref)
    mc_deg = mfcc(deg)

    # Align frame count
    min_frames = min(mc_ref.shape[1], mc_deg.shape[1])
    mc_ref = mc_ref[:, :min_frames]
    mc_deg = mc_deg[:, :min_frames]

    diff = mc_ref - mc_deg
    mcd_per_frame = C * np.sqrt(2.0 * np.sum(diff**2, axis=0))
    return float(np.mean(mcd_per_frame))


def compute_f0_rmse(ref_wav: np.ndarray, deg_wav: np.ndarray, sr: int = SAMPLE_RATE) -> float:
    """
    Root Mean Square Error of fundamental frequency (F0) in Hz.

    Uses librosa's pyin estimator.  Returns NaN if voiced frames < 10.
    Computes RMSE directly on Hz values over mutually voiced frames.

    Args:
        ref_wav: Reference waveform (mono float32).
        deg_wav: Degraded/synthesised waveform (mono float32).
        sr: Sample rate in Hz.

    Returns:
        F0 RMSE in Hz, or NaN if insufficient voiced frames.
    """
    import librosa

    hop = F0_HOP
    fmin, fmax = librosa.note_to_hz("C2"), librosa.note_to_hz("C7")

    f0_ref, voiced_ref, _ = librosa.pyin(ref_wav, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop, fill_na=0.0)
    f0_deg, voiced_deg, _ = librosa.pyin(deg_wav, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop, fill_na=0.0)

    f0_ref = np.nan_to_num(f0_ref, nan=0.0)
    f0_deg = np.nan_to_num(f0_deg, nan=0.0)

    min_frames = min(len(f0_ref), len(f0_deg))
    f0_ref, f0_deg = f0_ref[:min_frames], f0_deg[:min_frames]
    voiced_ref, voiced_deg = voiced_ref[:min_frames], voiced_deg[:min_frames]

    # Only evaluate on mutually voiced frames
    mask = voiced_ref & voiced_deg
    if mask.sum() < 10:
        return float("nan")

    diff = f0_ref[mask] - f0_deg[mask]
    return float(np.sqrt(np.mean(diff ** 2)))


def compute_f0_mae(ref_wav: np.ndarray, deg_wav: np.ndarray, sr: int = SAMPLE_RATE) -> float:
    """
    Mean Absolute Error of fundamental frequency (F0) in cents.
    Uses librosa's pyin estimator.  Returns NaN if voiced frames < 10.
    """
    import librosa

    hop = F0_HOP
    fmin, fmax = librosa.note_to_hz("C2"), librosa.note_to_hz("C7")

    f0_ref, voiced_ref, _ = librosa.pyin(ref_wav, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop)
    f0_deg, voiced_deg, _ = librosa.pyin(deg_wav, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop)

    min_frames = min(len(f0_ref), len(f0_deg))
    f0_ref, f0_deg = f0_ref[:min_frames], f0_deg[:min_frames]
    voiced_ref, voiced_deg = voiced_ref[:min_frames], voiced_deg[:min_frames]

    # Only evaluate on mutually voiced frames
    mask = voiced_ref & voiced_deg
    if mask.sum() < 10:
        return float("nan")

    # Convert to cents for scale-invariant comparison
    def hz_to_cents(hz: np.ndarray) -> np.ndarray:
        return 1200.0 * np.log2(np.maximum(hz, 1e-6) / 440.0)

    cents_ref = hz_to_cents(f0_ref[mask])
    cents_deg = hz_to_cents(f0_deg[mask])
    return float(np.mean(np.abs(cents_ref - cents_deg)))


def compute_speaker_similarity(
    ref_wav: np.ndarray,
    deg_wav: np.ndarray,
    encoder: torch.nn.Module,
    device: torch.device,
    sr: int = SR_SPEAKER,
) -> float:
    """
    Cosine similarity between WavLM speaker embeddings.
    Returns value in [-1, 1]; target >= 0.85.
    """
    encoder.eval()

    def embed(wav: np.ndarray) -> torch.Tensor:
        t = torch.from_numpy(wav).unsqueeze(0).to(device)  # (1, T)
        with torch.no_grad():
            emb = encoder(t)  # (1, emb_dim)
        return emb.squeeze(0)

    e_ref = embed(ref_wav)
    e_deg = embed(deg_wav)
    sim = torch.nn.functional.cosine_similarity(e_ref.unsqueeze(0), e_deg.unsqueeze(0))
    return float(sim.item())


def compute_wer(ref_text: str, hyp_text: str) -> float:
    """
    Word Error Rate using the ``jiwer`` library.
    Returns a float in [0, 1+].
    """
    try:
        import jiwer  # type: ignore[import]
    except ImportError:
        logger.warning("jiwer package not installed — skipping WER")
        return float("nan")

    transforms = jiwer.Compose(
        [
            jiwer.ToLowerCase(),
            jiwer.RemovePunctuation(),
            jiwer.RemoveMultipleSpaces(),
            jiwer.Strip(),
            jiwer.SentencesToListOfWords(),
        ]
    )
    return float(jiwer.wer(ref_text, hyp_text, truth_transform=transforms, hypothesis_transform=transforms))


# =============================================================================
# Model / pipeline loading
# =============================================================================


def load_speaker_encoder(checkpoint_path: str, device: torch.device) -> torch.nn.Module:
    """Load the WavLMSpeakerEncoder from a checkpoint."""
    from models.speaker_encoder.model import WavLMSpeakerEncoder  # type: ignore[import]

    encoder = WavLMSpeakerEncoder.from_pretrained(checkpoint_path)
    encoder = encoder.to(device)
    encoder.eval()
    return encoder


def load_pipeline(checkpoint_path: str, device: torch.device):
    """Load the full AudioPipeline for inference."""
    try:
        from core.pipeline import AudioPipeline, PipelineConfig  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("core.pipeline not found — ensure PYTHONPATH is set.") from exc

    config = PipelineConfig(
        models_dir=str(Path(checkpoint_path).parent),
        device=str(device),
    )
    pipeline = AudioPipeline(config)
    pipeline.load_checkpoint(checkpoint_path)
    return pipeline


# =============================================================================
# Evaluation loop
# =============================================================================


def evaluate(
    checkpoint: str,
    test_manifest: str,
    output_dir: str,
    device_str: str = "cuda",
    max_samples: int | None = None,
) -> dict[str, float]:
    """
    Run evaluation over the test manifest.

    Parameters
    ----------
    checkpoint:
        Path to model checkpoint (.pt file).
    test_manifest:
        Path to test manifest JSON (list of dicts with keys:
        ``reference_wav``, ``input_wav``, ``reference_lyrics``).
    output_dir:
        Directory where synthesised audio is written.
    device_str:
        ``"cuda"`` or ``"cpu"``.
    max_samples:
        Cap evaluation at this many samples (useful for quick checks).

    Returns
    -------
    dict
        Aggregated metric means.
    """
    device = torch.device(device_str if torch.cuda.is_available() and device_str == "cuda" else "cpu")
    logger.info("Device: %s", device)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Load test manifest
    with open(test_manifest, "r") as fh:
        samples: list[dict[str, Any]] = json.load(fh)
    if max_samples is not None:
        samples = samples[:max_samples]
    logger.info("Evaluating %d samples", len(samples))

    # Load models
    logger.info("Loading speaker encoder …")
    speaker_enc = load_speaker_encoder(checkpoint, device)

    logger.info("Loading inference pipeline …")
    pipeline = load_pipeline(checkpoint, device)

    # Metric accumulators
    pesq_scores: list[float] = []
    stoi_scores: list[float] = []
    sim_scores: list[float] = []
    f0_maes: list[float] = []
    f0_rmses: list[float] = []
    wer_scores: list[float] = []
    mcd_scores: list[float] = []

    for idx, sample in enumerate(samples):
        ref_path = sample["reference_wav"]
        inp_path = sample.get("input_wav", ref_path)
        ref_lyrics = sample.get("reference_lyrics", "")

        syn_path = str(output_path / f"syn_{idx:05d}.wav")

        # Run synthesis
        try:
            result = pipeline.run(
                input_paths=[inp_path],
                output_path=syn_path,
                job_id=f"eval_{idx:05d}",
            )
        except Exception as exc:
            logger.warning("Sample %d synthesis failed: %s", idx, exc)
            continue

        syn_lyrics = result.get("lyrics", "")

        # Load waveforms
        ref_wav_native = load_audio(ref_path, sr=SAMPLE_RATE)
        syn_wav_native = load_audio(syn_path, sr=SAMPLE_RATE)
        ref_wav_16k = resample(ref_wav_native, SAMPLE_RATE, SR_PESQ)
        syn_wav_16k = resample(syn_wav_native, SAMPLE_RATE, SR_PESQ)
        ref_wav_spk = resample(ref_wav_native, SAMPLE_RATE, SR_SPEAKER)
        syn_wav_spk = resample(syn_wav_native, SAMPLE_RATE, SR_SPEAKER)

        # Compute metrics
        pesq_scores.append(compute_pesq(ref_wav_16k, syn_wav_16k, sr=SR_PESQ))
        stoi_scores.append(compute_stoi(ref_wav_native, syn_wav_native, sr=SAMPLE_RATE))
        sim_scores.append(compute_speaker_similarity(ref_wav_spk, syn_wav_spk, speaker_enc, device))
        f0_maes.append(compute_f0_mae(ref_wav_native, syn_wav_native, sr=SAMPLE_RATE))
        f0_rmses.append(compute_f0_rmse(ref_wav_native, syn_wav_native, sr=SAMPLE_RATE))
        mcd_scores.append(compute_mcd(ref_wav_native, syn_wav_native, sr=SAMPLE_RATE))
        if ref_lyrics:
            wer_scores.append(compute_wer(ref_lyrics, syn_lyrics))

        if (idx + 1) % 10 == 0:
            logger.info("Processed %d / %d samples", idx + 1, len(samples))

    def nanmean(vals: list[float]) -> float:
        arr = np.array(vals, dtype=np.float64)
        return float(np.nanmean(arr)) if len(arr) > 0 else float("nan")

    results = {
        "pesq":               nanmean(pesq_scores),
        "stoi":               nanmean(stoi_scores),
        "speaker_similarity": nanmean(sim_scores),
        "f0_mae_cents":       nanmean(f0_maes),
        "f0_rmse_hz":         nanmean(f0_rmses),
        "mcd_db":             nanmean(mcd_scores),
        "wer":                nanmean(wer_scores) if wer_scores else float("nan"),
        "n_samples":          len(pesq_scores),
    }
    return results


# =============================================================================
# Results display
# =============================================================================


def print_results_table(results: dict[str, float], checkpoint: str) -> None:
    """Print a formatted results table to stdout."""
    SEP = "─" * 52

    print(f"\n{SEP}")
    print(f"  Evaluation Results")
    print(f"  Checkpoint : {Path(checkpoint).name}")
    print(f"  Samples    : {int(results['n_samples'])}")
    print(f"{SEP}")
    print(f"  {'Metric':<28} {'Score':>10}  {'Target':>8}")
    print(f"{SEP}")

    rows = [
        ("PESQ (wideband, ↑)",     results["pesq"],               "≥ 3.5"),
        ("STOI (eSTOI, ↑)",        results["stoi"],               "≥ 0.85"),
        ("Speaker Similarity (↑)", results["speaker_similarity"], "≥ 0.85"),
        ("F0 MAE / cents (↓)",     results["f0_mae_cents"],       "≤ 50"),
        ("F0 RMSE / Hz (↓)",       results["f0_rmse_hz"],         "≤ 25"),
        ("MCD / dB (↓)",           results["mcd_db"],             "≤ 6.0"),
        ("WER (↓)",                results["wer"],                "≤ 0.10"),
    ]

    for label, value, target in rows:
        val_str = f"{value:.4f}" if not np.isnan(value) else "  N/A  "
        print(f"  {label:<28} {val_str:>10}  {target:>8}")

    print(f"{SEP}\n")

    # Highlight pass/fail
    speaker_sim = results["speaker_similarity"]
    if not np.isnan(speaker_sim):
        status = "PASS" if speaker_sim >= TARGET_SIM else "FAIL"
        print(f"  Speaker similarity target ({TARGET_SIM}): {status}")
        print()


# =============================================================================
# Entry point
# =============================================================================


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate generative audio composition model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        help="Path to model checkpoint (.pt file or directory)",
    )
    parser.add_argument(
        "--test-manifest",
        required=True,
        help="Path to test manifest JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/eval_outputs",
        help="Directory to write synthesised audio files",
    )
    parser.add_argument(
        "--device",
        default="cuda",
        choices=["cuda", "cpu"],
        help="Compute device",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Limit evaluation to this many samples (for quick runs)",
    )
    parser.add_argument(
        "--save-results",
        default=None,
        help="If set, save results JSON to this path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not Path(args.checkpoint).exists():
        sys.exit(f"Checkpoint not found: {args.checkpoint}")
    if not Path(args.test_manifest).exists():
        sys.exit(f"Test manifest not found: {args.test_manifest}")

    results = evaluate(
        checkpoint=args.checkpoint,
        test_manifest=args.test_manifest,
        output_dir=args.output_dir,
        device_str=args.device,
        max_samples=args.max_samples,
    )

    print_results_table(results, args.checkpoint)

    if args.save_results:
        with open(args.save_results, "w") as fh:
            json.dump(results, fh, indent=2)
        logger.info("Results saved to %s", args.save_results)


if __name__ == "__main__":
    main()
