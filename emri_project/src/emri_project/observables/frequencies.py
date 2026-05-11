"""Orbital frequencies for Schwarzschild geodesics.

For circular orbits:
  Ω_φ = dφ/dt = (M/r³)^(1/2) = r^(-3/2) in units M=1
  Ω_r = 0 (circular)

For eccentric orbits, integrate one radial period to get T_r and Δφ:
  T_r = ∮ dr / ṙ
  Δφ = ∮ (dφ/dr) dr
  Ω_r = 2π / T_r
  Ω_φ = Δφ / T_r
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import quad

from emri_project.dynamics.metric import lapse
from emri_project.observables.turning_points import find_turning_points


def omega_phi_circular(r: float) -> float:
    """Ω_φ = r^(-3/2) for circular Schwarzschild orbit."""
    return r**(-1.5)


def orbital_frequencies(E: float, L: float) -> dict[str, float]:
    """Compute Ω_r and Ω_φ for a bound geodesic with given (E, L).

    Uses quadrature over one radial period.
    Returns dict with keys: 'Omega_r', 'Omega_phi', 'T_r', 'Delta_phi'.
    """
    r_peri, r_apo = find_turning_points(E, L)

    if np.isnan(r_peri) or np.isnan(r_apo):
        return {'Omega_r': 0.0, 'Omega_phi': 0.0, 'T_r': np.inf, 'Delta_phi': 0.0}

    def dr_dtau_inv(r: float) -> float:
        """1/ṙ = 1/(f*p_r); from E² = f*(1+L²/r²) + f²*p_r² solve for p_r."""
        f = 1.0 - 2.0 / r
        # p_r² = (E² - f*(1 + L²/r²)) / f²
        pr2 = (E**2 - f * (1.0 + L**2 / r**2)) / f**2
        if pr2 <= 0:
            return 1e12
        return 1.0 / (f * np.sqrt(pr2))

    def dphi_dr(r: float) -> float:
        """dφ/dr = φ̇/ṙ = (L/r²) / (f*p_r)."""
        f = 1.0 - 2.0 / r
        pr2 = (E**2 - f * (1.0 + L**2 / r**2)) / f**2
        if pr2 <= 0:
            return 0.0
        return (L / r**2) / (f * np.sqrt(pr2))

    eps = 1e-4 * (r_apo - r_peri)
    r_lo = r_peri + eps
    r_hi = r_apo - eps

    T_r_half, _ = quad(dr_dtau_inv, r_lo, r_hi, limit=200, epsabs=1e-10, epsrel=1e-10)
    T_r = 2.0 * T_r_half

    Delta_phi_half, _ = quad(dphi_dr, r_lo, r_hi, limit=200, epsabs=1e-10, epsrel=1e-10)
    Delta_phi = 2.0 * Delta_phi_half

    Omega_r = 2.0 * np.pi / T_r if T_r > 0 else 0.0
    Omega_phi = Delta_phi / T_r if T_r > 0 else 0.0

    return {
        'Omega_r': Omega_r,
        'Omega_phi': Omega_phi,
        'T_r': T_r,
        'Delta_phi': Delta_phi,
        'r_peri': r_peri,
        'r_apo': r_apo,
    }
