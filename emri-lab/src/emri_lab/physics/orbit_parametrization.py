"""Orbit parametrization utilities for Schwarzschild geodesics.

All quantities are in geometrized units G = c = M = 1.

Schwarzschild metric function:  f(r) = 1 - 2/r
Circular orbit conserved quantities:
    E_circ(r) = (r - 2) / sqrt(r * (r - 3))
    L_circ(r) = r / sqrt(r - 3)

The (p, e) semi-latus / eccentricity parametrization:
    r(χ_r) = p / (1 + e cos χ_r)
    r_peri  = p / (1 + e)
    r_apo   = p / (1 - e)
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import fsolve

from ..domain.enums import OrbitType


# ---------------------------------------------------------------------------
# Schwarzschild helpers
# ---------------------------------------------------------------------------

def _f(r: float) -> float:
    """Schwarzschild lapse function f(r) = 1 - 2/r."""
    return 1.0 - 2.0 / r


def _circular_E(r: float) -> float:
    """Specific energy of a circular orbit at r."""
    return (r - 2.0) / np.sqrt(r * (r - 3.0))


def _circular_L(r: float) -> float:
    """Specific angular momentum of a circular orbit at r."""
    return r / np.sqrt(r - 3.0)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pe_to_EL(p: float, e: float) -> tuple[float, float]:
    """Compute conserved specific energy E and angular momentum L from (p, e).

    For circular orbits (e < 1e-6) the closed-form circular expressions are
    used directly.  For eccentric orbits the turning-point conditions

        L² = r² (E² / f(r) - 1)   at r = r_peri  and  r = r_apo

    are solved simultaneously with ``scipy.optimize.fsolve``.

    Parameters
    ----------
    p : float
        Semi-latus rectum (must satisfy p > 6 + 2*e for a bound orbit).
    e : float
        Eccentricity, 0 ≤ e < 1.

    Returns
    -------
    E : float
        Specific energy (dimensionless, E < 1 for bound orbits).
    L : float
        Specific angular momentum (units of M).
    """
    if e < 1e-6:
        # Circular limit: use p as the orbital radius.
        return _circular_E(p), _circular_L(p)

    r1 = p / (1.0 + e)  # periapsis
    r2 = p / (1.0 - e)  # apoapsis

    def equations(x: np.ndarray) -> np.ndarray:
        E_val, L_val = x
        # At turning points dr/dτ = 0  →  V_eff(r) = E²
        # V_eff(r) = f(r) * (1 + L²/r²)  →  L² = r²(E²/f(r) - 1)
        eq1 = L_val ** 2 - r1 ** 2 * (E_val ** 2 / _f(r1) - 1.0)
        eq2 = L_val ** 2 - r2 ** 2 * (E_val ** 2 / _f(r2) - 1.0)
        return np.array([eq1, eq2])

    # Initial guess from midpoint circular orbit
    r_mid = 0.5 * (r1 + r2)
    E0 = _circular_E(r_mid)
    L0 = _circular_L(r_mid)

    sol, info, ier, msg = fsolve(equations, [E0, L0], full_output=True)
    if ier != 1:
        raise RuntimeError(
            f"pe_to_EL failed for p={p}, e={e}: {msg}\n"
            f"fsolve info: {info}"
        )

    E, L = sol
    # Ensure physical sign conventions: E > 0, L > 0 (prograde)
    return float(abs(E)), float(abs(L))


def pe_to_canonical(
    p: float,
    e: float,
    chi_r: float,
    phi0: float = 0.0,
) -> dict[str, float]:
    """Convert (p, e, χ_r) to a canonical phase-space point.

    The radial coordinate and its conjugate momentum are computed from the
    energy constraint; the azimuthal coordinate is set to ``phi0``.

    Parameters
    ----------
    p, e : float
        Orbital parameters.
    chi_r : float
        Radial anomaly angle (radians).
    phi0 : float
        Initial azimuthal angle φ₀ (radians).

    Returns
    -------
    dict with keys 'r', 'phi', 'pr', 'E', 'L'.
    """
    E, L = pe_to_EL(p, e)

    r = p / (1.0 + e * np.cos(chi_r))
    fr = _f(r)

    # From the geodesic energy constraint (per unit rest mass):
    #   (dr/dτ)² = E² - f(r)(1 + L²/r²)
    # → pr = μ * dr/dτ  (here μ=1 in geometrized units, so pr = dr/dτ)
    under = E ** 2 - fr * (1.0 + L ** 2 / r ** 2)
    # Clamp tiny negative residuals from floating-point noise
    pr = float(np.sqrt(max(under, 0.0)))

    return {
        "r": float(r),
        "phi": float(phi0),
        "pr": pr,
        "E": E,
        "L": L,
    }


def classify_orbit(p: float, e: float) -> OrbitType:
    """Classify an orbit by its (p, e) parameters.

    Rules
    -----
    - p ≤ 6 + 2e                   → PLUNGING
    - e < 1e-6  and  p > 6         → CIRCULAR_STABLE
    - e < 1e-6  and  p ≤ 6         → CIRCULAR_UNSTABLE
    - otherwise                    → BOUND_ECCENTRIC
    """
    separatrix = 6.0 + 2.0 * e
    if p <= separatrix:
        return OrbitType.PLUNGING
    if e < 1e-6:
        if p > 6.0:
            return OrbitType.CIRCULAR_STABLE
        return OrbitType.CIRCULAR_UNSTABLE
    return OrbitType.BOUND_ECCENTRIC


def EL_to_pe(E: float, L: float) -> tuple[float, float]:
    """Invert the (E, L) → (p, e) map by finding the turning points.

    The turning points r₁ (periapsis) and r₂ (apoapsis) satisfy
        E² = f(r)(1 + L²/r²)
    i.e. the effective potential V_eff(r) = f(r)(1 + L²/r²) equals E².

    Parameters
    ----------
    E : float
        Specific energy (0 < E < 1 for bound orbits).
    L : float
        Specific angular momentum (L > 0 for prograde).

    Returns
    -------
    p : float
        Semi-latus rectum.
    e : float
        Eccentricity.
    """
    # V_eff(r) = f(r)(1 + L²/r²) = (1 - 2/r)(1 + L²/r²)
    # Turning points: V_eff(r) = E²
    # Rearranged: r³ - r²/E² * (1 + E²*0) ... easier to root-find numerically.

    def veff_minus_E2(r: float) -> float:
        return _f(r) * (1.0 + L ** 2 / r ** 2) - E ** 2

    # Search in a bracketed range; for bound orbits r is between ~2 and large r.
    # We scan for sign changes to locate r_peri and r_apo.
    r_search = np.linspace(2.01, 200.0, 10000)
    v_arr = np.array([veff_minus_E2(r) for r in r_search])

    # Find indices where the function changes sign
    sign_changes = np.where(np.diff(np.sign(v_arr)))[0]

    if len(sign_changes) < 2:
        raise ValueError(
            f"Could not find two turning points for E={E}, L={L}. "
            "Check that the orbit is bound (0 < E < 1)."
        )

    from scipy.optimize import brentq

    r_roots = []
    for idx in sign_changes[:2]:
        root = brentq(veff_minus_E2, r_search[idx], r_search[idx + 1])
        r_roots.append(root)

    r_peri, r_apo = sorted(r_roots[:2])

    # Recover p and e from turning points
    p = 2.0 * r_peri * r_apo / (r_peri + r_apo)
    e = (r_apo - r_peri) / (r_apo + r_peri)

    return float(p), float(e)
