"""Diagnostics and parameter scan tools for orbit observables."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from emri_project.dynamics.geodesic_solver import (
    OrbitSolution, circular_E, circular_L, effective_potential
)
from emri_project.observables.turning_points import find_turning_points
from emri_project.observables.frequencies import orbital_frequencies


def orbit_summary(sol: OrbitSolution) -> dict:
    """Compute summary diagnostics for an integrated orbit."""
    H_drift = sol.hamiltonian_drift()
    return {
        'E': sol.E,
        'L': sol.L,
        'r_min': float(np.min(sol.r)),
        'r_max': float(np.max(sol.r)),
        'tau_total': float(sol.tau[-1]),
        'H_drift_max': float(np.max(np.abs(H_drift))),
        'H_drift_rms': float(np.sqrt(np.mean(H_drift**2))),
        'n_orbits_approx': float(sol.phi[-1] / (2.0 * np.pi)),
    }


def scan_circular_orbits(r_values: NDArray) -> dict[str, NDArray]:
    """Parametric scan of circular orbit observables over radii r > 6."""
    r_valid = r_values[r_values > 6.01]
    E_arr = np.array([circular_E(r) for r in r_valid])
    L_arr = np.array([circular_L(r) for r in r_valid])
    Omega_arr = r_valid**(-1.5)  # Keplerian-like: Ω = r^(-3/2)
    return {
        'r': r_valid,
        'E': E_arr,
        'L': L_arr,
        'Omega_phi': Omega_arr,
        'binding_energy': E_arr - 1.0,  # negative for bound orbits
    }


def scan_eccentric_orbits(
    p_values: NDArray,
    e_values: NDArray,
) -> list[dict]:
    """Scan over (p, e) grid and compute orbital frequencies."""
    results = []
    for p in p_values:
        for e in e_values:
            r_peri = p / (1.0 + e)
            r_apo = p / (1.0 - e)
            if r_peri < 4.0 or r_apo > 1000.0:
                continue
            try:
                from emri_project.dynamics.geodesic_solver import ic_eccentric
                _state0, E, L = ic_eccentric(r_apo, r_peri)
                freqs = orbital_frequencies(E, L)
                results.append({'p': p, 'e': e, 'E': E, 'L': L, **freqs})
            except Exception:
                pass
    return results
