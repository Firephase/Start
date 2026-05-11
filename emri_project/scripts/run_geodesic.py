#!/usr/bin/env python3
"""Script: run a geodesic orbit and produce diagnostic plots.

Usage:
    python scripts/run_geodesic.py --r0 10 --mode circular --tau_max 500
    python scripts/run_geodesic.py --r0 10 --mode eccentric --r_peri 7 --tau_max 2000
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from emri_project.dynamics.geodesic_solver import (
    ic_circular, ic_perturbed_circular, ic_eccentric, integrate_geodesic
)
from emri_project.observables.diagnostics import orbit_summary
from emri_project.observables.frequencies import orbital_frequencies
from emri_project.plotting.orbits import (
    plot_effective_potential, plot_orbit_trajectory, plot_hamiltonian_drift
)


def parse_args():
    p = argparse.ArgumentParser(description="Run Schwarzschild geodesic orbit")
    p.add_argument("--r0", type=float, default=10.0, help="Initial radius")
    p.add_argument("--mode", choices=["circular", "perturbed", "eccentric"],
                   default="circular")
    p.add_argument("--r_peri", type=float, default=7.0,
                   help="Pericenter for eccentric mode")
    p.add_argument("--tau_max", type=float, default=2000.0)
    p.add_argument("--n_points", type=int, default=20000)
    p.add_argument("--output_dir", type=Path, default=Path("output"))
    return p.parse_args()


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[EMRI] Running geodesic: mode={args.mode}, r0={args.r0}")

    if args.mode == "circular":
        state0, E, L = ic_circular(args.r0)
    elif args.mode == "perturbed":
        state0, E, L = ic_perturbed_circular(args.r0)
    else:
        state0, E, L = ic_eccentric(r_apo=args.r0, r_peri=args.r_peri)

    print(f"[EMRI] E={E:.6f}, L={L:.6f}")

    sol = integrate_geodesic(state0, E, L, tau_max=args.tau_max,
                             n_points=args.n_points)
    print(f"[EMRI] Integration: {sol.message}, {len(sol.tau)} points")

    summary = orbit_summary(sol)
    print("\n=== ORBIT SUMMARY ===")
    for k, v in summary.items():
        print(f"  {k:25s}: {v:.6g}")

    if args.mode == "eccentric":
        freqs = orbital_frequencies(E, L)
        print("\n=== ORBITAL FREQUENCIES ===")
        for k, v in freqs.items():
            print(f"  {k:20s}: {v:.6g}")

    # Plots
    fig_veff = plot_effective_potential(L, E=E, r_range=(2.5, args.r0 * 2))
    fig_veff.savefig(args.output_dir / "veff.png", dpi=150)
    plt.close(fig_veff)

    fig_traj = plot_orbit_trajectory(sol)
    fig_traj.savefig(args.output_dir / "trajectory.png", dpi=150)
    plt.close(fig_traj)

    fig_drift = plot_hamiltonian_drift(sol)
    fig_drift.savefig(args.output_dir / "hamiltonian_drift.png", dpi=150)
    plt.close(fig_drift)

    # Save trajectory
    np.savez(
        args.output_dir / "trajectory.npz",
        tau=sol.tau, t=sol.t, r=sol.r, phi=sol.phi, pr=sol.pr,
        E=np.array([sol.E]), L=np.array([sol.L])
    )
    print(f"\n[EMRI] Outputs saved to {args.output_dir}/")


if __name__ == "__main__":
    main()
