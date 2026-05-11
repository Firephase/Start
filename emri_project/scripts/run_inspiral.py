#!/usr/bin/env python3
"""Script: run adiabatic inspiral and produce plots.

Usage:
    python scripts/run_inspiral.py --r0 15 --eta 1e-5 --t_max 1e7
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from emri_project.dynamics.geodesic_solver import circular_E, circular_L
from emri_project.dynamics.inspiral import integrate_inspiral
from emri_project.waveform.interfaces import waveform_from_inspiral
from emri_project.plotting.fluxes import plot_inspiral_track
from emri_project.plotting.waveforms import plot_waveform, plot_waveform_spectrum


def parse_args():
    p = argparse.ArgumentParser(description="Run EMRI adiabatic inspiral")
    p.add_argument("--r0", type=float, default=15.0)
    p.add_argument("--eta", type=float, default=1e-5)
    p.add_argument("--t_max", type=float, default=5e6)
    p.add_argument("--horizon_flux", action="store_true")
    p.add_argument("--output_dir", type=Path, default=Path("output"))
    return p.parse_args()


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[EMRI] Inspiral: r0={args.r0}, η={args.eta:.2e}")

    E0 = circular_E(args.r0)
    L0 = circular_L(args.r0)
    print(f"[EMRI] Initial: E={E0:.6f}, L={L0:.6f}")

    sol = integrate_inspiral(
        E0, L0, eta=args.eta,
        t_max=args.t_max,
        n_points=5000,
        use_horizon_flux=args.horizon_flux,
    )

    print(f"[EMRI] Inspiral done: {len(sol.t)} points, plunged={sol.plunged}")
    print(f"[EMRI] Final r_circ = {sol.r_circ[-1]:.3f} M")

    wf = waveform_from_inspiral(sol.t, sol.r_circ, args.eta, distance=1e6)
    print(f"[EMRI] Waveform: {len(wf.t)} points, SNR proxy={wf.snr_proxy():.3e}")

    fig_insp = plot_inspiral_track(sol)
    fig_insp.savefig(args.output_dir / "inspiral_track.png", dpi=150)
    plt.close(fig_insp)

    fig_wf = plot_waveform(wf)
    fig_wf.savefig(args.output_dir / "waveform.png", dpi=150)
    plt.close(fig_wf)

    fig_spec = plot_waveform_spectrum(wf)
    fig_spec.savefig(args.output_dir / "waveform_spectrum.png", dpi=150)
    plt.close(fig_spec)

    np.savez(
        args.output_dir / "inspiral.npz",
        t=sol.t, E=sol.E, L=sol.L, r=sol.r_circ
    )
    np.savez(
        args.output_dir / "waveform.npz",
        t=wf.t, h_plus=wf.h_plus, h_cross=wf.h_cross, phase=wf.phase
    )
    print(f"[EMRI] Outputs saved to {args.output_dir}/")


if __name__ == "__main__":
    main()
