#!/usr/bin/env python3
"""Parametric scan of circular orbit observables.

Usage:
    python scripts/scan_orbits.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from emri_project.observables.diagnostics import scan_circular_orbits
from emri_project.fluxes.infinity_flux import flux_E_PN_circular
from emri_project.fluxes.horizon_flux import horizon_flux_ratio


def main():
    r_vals = np.linspace(6.1, 50.0, 200)
    scan = scan_circular_orbits(r_vals)

    F_E = np.array([flux_E_PN_circular(r) for r in scan['r']])
    H_ratio = np.array([horizon_flux_ratio(r) for r in scan['r']])

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))

    axes[0, 0].plot(scan['r'], scan['E'], 'b-')
    axes[0, 0].set_xlabel(r'$r/M$'); axes[0, 0].set_ylabel(r'$E(r)$')
    axes[0, 0].set_title('Circular orbit energy'); axes[0, 0].grid(True, alpha=0.3)

    axes[0, 1].plot(scan['r'], scan['L'], 'g-')
    axes[0, 1].set_xlabel(r'$r/M$'); axes[0, 1].set_ylabel(r'$L(r)$')
    axes[0, 1].set_title('Angular momentum'); axes[0, 1].grid(True, alpha=0.3)

    axes[0, 2].plot(scan['r'], scan['Omega_phi'], 'r-')
    axes[0, 2].set_xlabel(r'$r/M$'); axes[0, 2].set_ylabel(r'$\Omega_\phi$')
    axes[0, 2].set_title('Orbital frequency'); axes[0, 2].grid(True, alpha=0.3)

    axes[1, 0].semilogy(scan['r'], F_E, 'b-')
    axes[1, 0].set_xlabel(r'$r/M$'); axes[1, 0].set_ylabel(r'$\dot{E}_\infty$')
    axes[1, 0].set_title('GW flux to infinity'); axes[1, 0].grid(True, alpha=0.3)

    axes[1, 1].semilogy(scan['r'], H_ratio, 'r-')
    axes[1, 1].set_xlabel(r'$r/M$'); axes[1, 1].set_ylabel(r'$\dot{E}_H/\dot{E}_\infty$')
    axes[1, 1].set_title('Horizon flux fraction'); axes[1, 1].grid(True, alpha=0.3)

    axes[1, 2].plot(scan['r'], scan['binding_energy'], 'k-')
    axes[1, 2].axhline(0, color='gray', ls='--')
    axes[1, 2].set_xlabel(r'$r/M$'); axes[1, 2].set_ylabel(r'$E-1$')
    axes[1, 2].set_title('Binding energy'); axes[1, 2].grid(True, alpha=0.3)

    fig.suptitle('Schwarzschild circular orbit scan', fontsize=14)
    fig.tight_layout()

    out = Path("output")
    out.mkdir(exist_ok=True)
    fig.savefig(out / "circular_orbit_scan.png", dpi=150)
    plt.close(fig)

    np.savetxt(
        out / "circular_scan.csv",
        np.column_stack([scan['r'], scan['E'], scan['L'], scan['Omega_phi'], F_E, H_ratio]),
        header="r,E,L,Omega_phi,flux_inf,horizon_ratio",
        delimiter=",", comments=""
    )
    print(f"Scan saved to {out}/")


if __name__ == "__main__":
    main()
