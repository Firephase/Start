"""Gravitational wave energy and angular momentum flux absorbed by the horizon.

For a Schwarzschild black hole, the horizon flux is suppressed relative to
the infinity flux by a factor ~ (M/r)^5 (beyond leading order) and becomes
important only near plunge.

Test-mass limit (Chrzanowski-Cohen-Kegeles, Poisson 1993):
  F_H^E / F_inf^E ~ (M Ω)^8 / 64  at leading order (4PN horizon term)
  F_H^E = (1/4) M^2 Ω^6 * r^(-2) ...

Here we implement the leading-order horizon flux from Poisson & Sasaki (1995):
  dE_H/dt = (32/5) η² (M/r)^5 * (v^8 / 4)
           = (8/5) η² v^18   [v = r^(-1/2)]
  dL_H/dt = dE_H/dt / Ω_φ

Reference: Poisson & Sasaki PRD 51 (1995) 5753.
"""

import numpy as np


def flux_E_horizon_circular(r: float) -> float:
    """Leading-order horizon energy flux for circular Schwarzschild orbit.

    F_H^E = (32/5) * (1/4) * v^18 = (8/5) * r^(-9)
    Suppressed by v^8 = r^(-4) relative to the leading infinity flux.
    """
    return (8.0 / 5.0) * r**(-9)


def flux_L_horizon_circular(r: float) -> float:
    """Leading-order horizon angular momentum flux."""
    Omega = r**(-1.5)
    return flux_E_horizon_circular(r) / Omega


def flux_E_horizon(E: float, L: float) -> float:
    """Horizon energy flux given (E, L)."""
    from emri_project.dynamics.inspiral import r_from_EL
    r = r_from_EL(E, L)
    if r < 6.0:
        return 0.0
    return flux_E_horizon_circular(r)


def flux_L_horizon(E: float, L: float) -> float:
    """Horizon angular momentum flux given (E, L)."""
    from emri_project.dynamics.inspiral import r_from_EL
    r = r_from_EL(E, L)
    if r < 6.0:
        return 0.0
    return flux_L_horizon_circular(r)


def horizon_flux_ratio(r: float) -> float:
    """Ratio F_H / F_inf at given orbital radius (test-mass limit)."""
    F_inf = (32.0 / 5.0) * r**(-5)
    F_hor = flux_E_horizon_circular(r)
    return F_hor / F_inf if F_inf > 0 else 0.0
