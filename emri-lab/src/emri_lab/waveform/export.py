"""Export utilities for waveform results."""
from __future__ import annotations

import json
import numpy as np
from pathlib import Path

from .result import WaveformResult, ModeAmplitudeTable


def export_waveform_csv(result: WaveformResult, path: str | Path) -> Path:
    """Export h+(t), hx(t), phase(t) to CSV."""
    path = Path(path)
    header = "time,h_plus,h_cross,phase,amplitude_envelope"
    data = np.column_stack([
        result.time,
        result.h_plus,
        result.h_cross,
        result.phase,
        result.amplitude_envelope,
    ])
    np.savetxt(path, data, delimiter=",", header=header, comments="")
    return path


def export_waveform_npy(result: WaveformResult, path: str | Path) -> Path:
    """Export waveform arrays to .npz file.

    The returned path is the actual file written by np.savez (which appends .npz
    if not already present).
    """
    path = Path(path)
    np.savez(
        path,
        time=result.time,
        h_plus=result.h_plus,
        h_cross=result.h_cross,
        phase=result.phase,
        amplitude_envelope=result.amplitude_envelope,
    )
    # np.savez appends .npz when it is not already the suffix
    if path.suffix != ".npz":
        path = path.with_suffix(path.suffix + ".npz")
    return path


def export_mode_table_json(table: ModeAmplitudeTable, path: str | Path) -> Path:
    """Export mode amplitude table to JSON."""
    path = Path(path)
    data = {
        "modes": [str(m) for m in table.modes],
        "amplitudes": [float(a) for a in table.amplitudes],
        "phases": [float(p) for p in table.phases],
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


def export_plot_bundle(result: WaveformResult, out_dir: str | Path) -> Path:
    """Save diagnostic plots (waveform, phase, amplitude envelope) to directory."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # h+ and hx
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    ax1.plot(result.time, result.h_plus)
    ax1.set_ylabel("h+")
    ax2.plot(result.time, result.h_cross)
    ax2.set_ylabel("hx")
    ax2.set_xlabel("t (M)")
    fig.tight_layout()
    fig.savefig(out_dir / "waveform.png", dpi=150)
    plt.close(fig)

    # Phase evolution
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(result.time, result.phase)
    ax.set_xlabel("t (M)")
    ax.set_ylabel("Phase (rad)")
    fig.tight_layout()
    fig.savefig(out_dir / "phase.png", dpi=150)
    plt.close(fig)

    # Amplitude envelope
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(result.time, result.amplitude_envelope)
    ax.set_xlabel("t (M)")
    ax.set_ylabel("Amplitude envelope")
    fig.tight_layout()
    fig.savefig(out_dir / "amplitude.png", dpi=150)
    plt.close(fig)

    return out_dir
