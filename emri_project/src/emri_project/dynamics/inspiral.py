"""Adiabatic inspiral engine for EMRI.

Strategy: at each moment the orbit is instantaneously geodesic with parameters
(E, L). These evolve slowly due to gravitational wave emission:
  dE/dt = -F_E(E, L)   [flux to infinity + horizon]
  dL/dt = -F_L(E, L)

We solve ODEs for (E(t), L(t)) using the flux models from emri_project.fluxes,
then reconstruct the instantaneous orbit at each step.

Separatrix condition for Schwarzschild: last stable orbit is at p = 6 + 2e,
where p is semi-latus rectum and e is eccentricity.
For circular: e=0, so separatrix is p = 6, i.e. r = 6 = r_ISCO.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from emri_project.constants import RTOL, ATOL, R_ISCO
from emri_project.fluxes.infinity_flux import flux_E_infinity, flux_L_infinity
from emri_project.fluxes.horizon_flux import flux_E_horizon, flux_L_horizon


# ---------------------------------------------------------------------------
# Separatrix and plunge detection
# ---------------------------------------------------------------------------

def r_from_EL(E: float, L: float) -> float:
    """Estimate stable circular orbit radius from E, L.

    E(r) = (r-2)/sqrt(r*(r-3)) is monotone increasing on (6, ∞).
    So E² = (r-2)²/(r*(r-3)) has a unique root on (6, ∞) for E in (sqrt(8/9), 1).
    """
    from scipy.optimize import brentq

    def residual(r: float) -> float:
        return (r - 2.0)**2 / (r * (r - 3.0)) - E**2

    try:
        # E²(r) is monotone increasing on [6, ∞): bracket there for stable orbit
        r = brentq(residual, R_ISCO + 0.01, 1e6)
    except ValueError:
        r = R_ISCO
    return r


def is_plunging(E: float, L: float) -> bool:
    """Return True if orbit has crossed the separatrix (ISCO)."""
    r = r_from_EL(E, L)
    return r < R_ISCO + 0.01


# ---------------------------------------------------------------------------
# Inspiral ODE system
# ---------------------------------------------------------------------------

def inspiral_rhs(
    t: float,
    state: NDArray,
    eta: float,
    use_horizon_flux: bool = False,
) -> NDArray:
    """dE/dt and dL/dt from radiation reaction.

    state = [E, L]
    eta = mu/M (mass ratio)
    """
    E, L = state

    # Flux functions return power (positive = energy lost)
    dE_inf = flux_E_infinity(E, L)
    dL_inf = flux_L_infinity(E, L)

    if use_horizon_flux:
        dE_hor = flux_E_horizon(E, L)
        dL_hor = flux_L_horizon(E, L)
    else:
        dE_hor = 0.0
        dL_hor = 0.0

    # Scale by mass ratio: rates ∝ η² but in reduced units ∝ η
    dE_dt = -eta * (dE_inf + dE_hor)
    dL_dt = -eta * (dL_inf + dL_hor)

    return np.array([dE_dt, dL_dt])


# ---------------------------------------------------------------------------
# Inspiral result
# ---------------------------------------------------------------------------

@dataclass
class InspiralSolution:
    """Adiabatic inspiral trajectory in (E, L) space and radius."""
    t: NDArray
    E: NDArray
    L: NDArray
    r_circ: NDArray  # instantaneous circular orbit radius
    plunged: bool
    message: str

    @property
    def Omega_phi(self) -> NDArray:
        """Azimuthal angular frequency Ω_φ = dφ/dt ≈ 1/r^(3/2) for circular orbit."""
        return 1.0 / self.r_circ**1.5

    @property
    def frequency_gw(self) -> NDArray:
        """Gravitational wave frequency f_GW = 2 * f_orb."""
        return 2.0 * self.Omega_phi / (2.0 * np.pi)


# ---------------------------------------------------------------------------
# Main inspiral integrator
# ---------------------------------------------------------------------------

def integrate_inspiral(
    E0: float,
    L0: float,
    eta: float = 1e-5,
    t_max: float = 1e7,
    n_points: int = 10000,
    use_horizon_flux: bool = False,
    rtol: float = 1e-10,
    atol: float = 1e-10,
) -> InspiralSolution:
    """Integrate adiabatic inspiral from (E0, L0).

    Returns InspiralSolution with t, E(t), L(t), r_circ(t).
    """
    state0 = np.array([E0, L0])
    t_span = (0.0, t_max)
    t_eval = np.linspace(0.0, t_max, n_points)

    # Termination: orbit crosses ISCO
    def isco_event(t: float, y: NDArray, eta: float, use_horizon_flux: bool) -> float:
        E, L = y
        r = r_from_EL(E, L)
        return r - R_ISCO - 0.05
    isco_event.terminal = True  # type: ignore[attr-defined]
    isco_event.direction = -1.0  # type: ignore[attr-defined]

    sol = solve_ivp(
        inspiral_rhs,
        t_span,
        state0,
        args=(eta, use_horizon_flux),
        method="DOP853",
        t_eval=t_eval,
        rtol=rtol,
        atol=atol,
        events=[isco_event],
    )

    E_arr = sol.y[0]
    L_arr = sol.y[1]
    r_arr = np.array([r_from_EL(E, L) for E, L in zip(E_arr, L_arr)])

    return InspiralSolution(
        t=sol.t,
        E=E_arr,
        L=L_arr,
        r_circ=r_arr,
        plunged=len(sol.t_events[0]) > 0,
        message=sol.message,
    )
