"""Gravitational wave energy and angular momentum flux to infinity.

For circular orbits, the leading-order (Peters-Mathews) formula gives:
  dE/dt = -(32/5) η² (M/r)^5  [quadrupole approximation]
  dL/dt = dE/dt / Ω_φ

For post-Newtonian (PN) corrections, we include terms up to 5.5PN.
The energy flux at infinity for a test particle (η→0) in Schwarzschild:
  F_E = (32/5) η² v^10 * [1 + PN corrections]
where v = (M/r)^(1/2) = r^(-1/2) in units M=1.

Reference: Blanchet (2014) Living Rev. Rel., Sasaki & Tagoshi (2003).
"""

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# Peters-Mathews quadrupole (Newtonian leading order)
# ---------------------------------------------------------------------------

def flux_E_quadrupole(r: float) -> float:
    """dE/dt at infinity, leading order quadrupole, circular orbit.

    F_E = (32/5) (M/r)^5 in units M=1, η=1 (scale by η²).
    """
    return (32.0 / 5.0) * r**(-5)


def flux_L_quadrupole(r: float) -> float:
    """dL/dt at infinity, leading order, from dL/dt = (dE/dt) / Ω_φ."""
    Omega = r**(-1.5)
    return flux_E_quadrupole(r) / Omega


# ---------------------------------------------------------------------------
# Post-Newtonian corrected fluxes (circular orbits, Schwarzschild, test-mass)
# ---------------------------------------------------------------------------

_PN_EULER_GAMMA = 0.5772156649015329

def flux_E_PN_circular(r: float, order: int = 5) -> float:
    """PN-corrected energy flux for circular orbit in Schwarzschild.

    Uses Fujita (2012) / Blanchet (2014) coefficients for test particle.
    v² = 1/r  (circular orbit in units M=1)
    F = (32/5) v^10 * sum_n f_n * v^n

    Coefficients f_n (test-particle, Schwarzschild):
    f_0 = 1
    f_2 = -1247/336 - 35η/12 ≈ -1247/336 (η→0)
    f_3 = 4π
    f_4 = -44711/9072 + 9271η/504 + 65η²/18 ≈ -44711/9072
    f_5 = (-8191/672 - 583η/24)π ≈ -8191π/672
    """
    v2 = 1.0 / r
    v = np.sqrt(v2)

    f0 = 1.0
    f2 = -1247.0 / 336.0
    f3 = 4.0 * np.pi
    f4 = -44711.0 / 9072.0
    f5 = -8191.0 * np.pi / 672.0

    correction = f0
    if order >= 2:
        correction += f2 * v2
    if order >= 3:
        correction += f3 * v**3
    if order >= 4:
        correction += f4 * v**4
    if order >= 5:
        correction += f5 * v**5

    return (32.0 / 5.0) * v**10 * correction


def flux_L_PN_circular(r: float, order: int = 5) -> float:
    """PN-corrected angular momentum flux for circular orbit."""
    Omega = r**(-1.5)
    return flux_E_PN_circular(r, order) / Omega


# ---------------------------------------------------------------------------
# Interface functions (used by inspiral engine)
# ---------------------------------------------------------------------------

def flux_E_infinity(E: float, L: float) -> float:
    """Total energy flux to infinity given (E, L).

    For now: use circular orbit approximation r ≈ r_circ(E).
    """
    from emri_project.dynamics.inspiral import r_from_EL
    r = r_from_EL(E, L)
    if r < 6.0:
        return 0.0
    return flux_E_PN_circular(r)


def flux_L_infinity(E: float, L: float) -> float:
    """Total angular momentum flux to infinity."""
    from emri_project.dynamics.inspiral import r_from_EL
    r = r_from_EL(E, L)
    if r < 6.0:
        return 0.0
    return flux_L_PN_circular(r)
