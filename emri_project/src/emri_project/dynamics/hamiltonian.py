"""Super-Hamiltonian and Hamilton equations for Schwarzschild geodesics.

H = (1/2)(- E²/f(r) + f(r)*p_r² + L²/r²)

Timelike constraint: H = -1/2
E = -p_t (conserved energy per unit mass)
L = p_φ  (conserved angular momentum per unit mass)

Hamilton equations (with λ = proper time τ):
  ṙ    = ∂H/∂p_r = f(r) * p_r
  φ̇    = ∂H/∂p_φ = L/r²
  ṫ    = ∂H/∂p_t = E/f(r)   (using p_t = -E)
  ṗ_r  = -∂H/∂r = -(1/2)(2E²/r³ ... ) [see below]

∂H/∂r = (1/2)(E²*f'/f² + f'*p_r² - 2L²/r³)
      = (1/2)(2E²/r³/f² * ... )  — computed analytically
"""

import numpy as np
from numpy.typing import NDArray

from emri_project.dynamics.metric import lapse, dlapse_dr


def superhamiltonian(r: NDArray, pr: NDArray, E: float, L: float) -> NDArray:
    """H = (1/2)(-E²/f + f*p_r² + L²/r²)."""
    f = lapse(r)
    return 0.5 * (-E**2 / f + f * pr**2 + L**2 / r**2)


def dH_dr(r: NDArray, pr: NDArray, E: float, L: float) -> NDArray:
    """∂H/∂r = (1/2)(E²*f'/f² + f'*p_r² - 2L²/r³)."""
    f = lapse(r)
    fp = dlapse_dr(r)
    return 0.5 * (E**2 * fp / f**2 + fp * pr**2 - 2.0 * L**2 / r**3)


def geodesic_rhs(tau: float, state: NDArray, E: float, L: float) -> NDArray:
    """Right-hand side of Hamilton equations.

    state = [t, r, phi, pr]
    Returns d/dτ [t, r, phi, pr]
    """
    _t, r, _phi, pr = state
    f = lapse(r)

    dt_dtau  = E / f
    dr_dtau  = f * pr
    dphi_dtau = L / r**2
    dpr_dtau  = -dH_dr(r, pr, E, L)

    return np.array([dt_dtau, dr_dtau, dphi_dtau, dpr_dtau])


def hamiltonian_constraint(state: NDArray, E: float, L: float) -> float:
    """Return H + 1/2; should be 0 for timelike geodesics."""
    _t, r, _phi, pr = state
    return float(superhamiltonian(r, pr, E, L)) + 0.5
