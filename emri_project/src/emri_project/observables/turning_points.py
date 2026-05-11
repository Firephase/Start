"""Turning point finder for radial motion.

Turning points r_min, r_max defined by: V_eff(r) = E²
V_eff(r) = f(r) * (1 + L²/r²) = (1 - 2/r) * (1 + L²/r²)

For bound orbits: E < 1 (total energy < rest mass energy).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq

from emri_project.dynamics.metric import lapse


def _veff(r: float, L: float) -> float:
    f = 1.0 - 2.0 / r
    return f * (1.0 + L**2 / r**2)


def _circular_radii_from_L(L: float) -> tuple[float, float]:
    """Compute stable and unstable circular orbit radii from L.

    From dV_eff/dr = 0: r² - L²r + 3L² = 0
    Solutions: r = L²/2 ± (L/2)*sqrt(L²-12)
    Returns (r_unstable, r_stable) where r_stable > 6 for L > 2√3.
    """
    L2 = L**2
    disc = L2 - 12.0
    if disc < 0:
        return float('nan'), float('nan')
    sqrt_disc = np.sqrt(disc)
    r_unstable = 0.5 * (L2 - L * sqrt_disc)
    r_stable   = 0.5 * (L2 + L * sqrt_disc)
    return r_unstable, r_stable


def find_turning_points(E: float, L: float) -> tuple[float, float]:
    """Find r_peri (pericenter) and r_apo (apocenter) for a bound orbit.

    Solves V_eff(r) = E² via root finding with analytically derived brackets.

    V_eff has a local MIN at r_stable (stable circular orbit) and a local MAX
    at r_unstable (unstable circular orbit). For an eccentric bound orbit:
      - r_peri lies in [r_unstable, r_stable]  (V_eff decreasing there)
      - r_apo  lies in [r_stable, ∞)           (V_eff increasing toward 1)

    Returns (r_peri, r_apo).
    """
    E2 = E**2

    def residual(r: float) -> float:
        return _veff(r, L) - E2

    r_unstable, r_stable = _circular_radii_from_L(L)

    if np.isnan(r_stable):
        return float('nan'), float('nan')

    v_min = _veff(r_stable, L)

    # Circular orbit: E² matches the potential minimum
    if abs(E2 - v_min) < 1e-9 * max(abs(v_min), 1e-30):
        return r_stable, r_stable

    # r_peri: V_eff decreases from local max (r_unstable) to min (r_stable)
    try:
        lo = max(r_unstable + 1e-4, 2.1)
        hi = r_stable - 1e-4
        if residual(lo) * residual(hi) < 0:
            r_peri = brentq(residual, lo, hi)
        else:
            r_peri = float('nan')
    except ValueError:
        r_peri = float('nan')

    # r_apo: V_eff increases from min (r_stable) to 1 at infinity
    try:
        lo_apo = r_stable + 1e-4
        hi_apo = 1e6
        if residual(lo_apo) * residual(hi_apo) < 0:
            r_apo = brentq(residual, lo_apo, hi_apo)
        else:
            r_apo = float('nan')
    except ValueError:
        r_apo = float('nan')

    return r_peri, r_apo


def turning_points_from_pe(p: float, e: float) -> tuple[float, float]:
    """Compute (r_peri, r_apo) from (p, e) parametrization.

    p = semi-latus rectum, e = eccentricity.
    r_peri = p/(1+e), r_apo = p/(1-e)
    """
    return p / (1.0 + e), p / (1.0 - e)


def pe_from_turning_points(r_peri: float, r_apo: float) -> tuple[float, float]:
    """Compute (p, e) from (r_peri, r_apo)."""
    p = 2.0 * r_peri * r_apo / (r_peri + r_apo)
    e = (r_apo - r_peri) / (r_apo + r_peri)
    return p, e
