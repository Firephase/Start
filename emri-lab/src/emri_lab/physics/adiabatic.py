"""Adiabatic inspiral integration in the (p, e) orbital element space.

Under the adiabatic approximation the orbital parameters evolve on the
radiation-reaction timescale according to

    [dp/dt]   =  J(p,e)^{-1}  ·  [dE/dt]
    [de/dt]                        [dL/dt]

where J = ∂(E,L)/∂(p,e) is computed by finite differences and dE/dt, dL/dt
come from the chosen flux model scaled by the mass ratio η.

All quantities are in geometrized units G = c = M = 1.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp
from typing import TYPE_CHECKING

from ..domain.enums import FluxModelId
from ..domain.models import InspiralResult, OrbitParams, PhysicsConfig
from .orbit_parametrization import pe_to_EL
from .fluxes import get_flux_model, BaseFluxModel

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Jacobian and rate-of-change helpers
# ---------------------------------------------------------------------------

_FD_STEP_P = 1e-5  # finite-difference step for ∂/∂p
_FD_STEP_E = 1e-7  # finite-difference step for ∂/∂e


def _jacobian_EL_pe(p: float, e: float) -> np.ndarray:
    """Compute the 2×2 Jacobian J = ∂(E,L)/∂(p,e) by central finite differences.

    Parameters
    ----------
    p, e : float
        Orbital parameters at which to evaluate the Jacobian.

    Returns
    -------
    J : np.ndarray, shape (2, 2)
        [[∂E/∂p, ∂E/∂e],
         [∂L/∂p, ∂L/∂e]]
    """
    # Step sizes — adapt to avoid unphysical regions
    hp = _FD_STEP_P * max(p, 1.0)
    he = _FD_STEP_E * max(e, 1e-4) if e > 1e-6 else _FD_STEP_P

    # ∂(E,L)/∂p — central difference
    E_p_fwd, L_p_fwd = pe_to_EL(p + hp, e)
    E_p_bwd, L_p_bwd = pe_to_EL(p - hp, e)
    dEdp = (E_p_fwd - E_p_bwd) / (2.0 * hp)
    dLdp = (L_p_fwd - L_p_bwd) / (2.0 * hp)

    # ∂(E,L)/∂e — central difference (clamp e so it stays in (0,1))
    e_fwd = min(e + he, 0.9999)
    e_bwd = max(e - he, 0.0)
    # ensure the step is symmetric; if not (near e=0), fall back to forward diff
    actual_he = 0.5 * (e_fwd - e_bwd)

    E_e_fwd, L_e_fwd = pe_to_EL(p, e_fwd)
    E_e_bwd, L_e_bwd = pe_to_EL(p, e_bwd)
    dEde = (E_e_fwd - E_e_bwd) / (2.0 * actual_he)
    dLde = (L_e_fwd - L_e_bwd) / (2.0 * actual_he)

    return np.array([[dEdp, dEde],
                     [dLdp, dLde]])


def dpde_rates(
    p: float,
    e: float,
    dEdt: float,
    dLdt: float,
) -> tuple[float, float]:
    """Compute dp/dt and de/dt from energy/angular-momentum fluxes.

    Inverts the Jacobian J = ∂(E,L)/∂(p,e):

        [dp/dt, de/dt]^T = J^{-1} · [dE/dt, dL/dt]^T

    Parameters
    ----------
    p, e : float
        Current orbital parameters.
    dEdt, dLdt : float
        Energy and angular-momentum loss rates (positive = lost to GWs).

    Returns
    -------
    dpdt, dedt : float
        Rates of change of the semi-latus rectum and eccentricity.
    """
    J = _jacobian_EL_pe(p, e)
    flux_vec = np.array([-dEdt, -dLdt])  # negative: orbit loses E and L
    try:
        rates = np.linalg.solve(J, flux_vec)
    except np.linalg.LinAlgError:
        # Fallback: use pseudo-inverse if J is singular (near separatrix)
        rates = np.linalg.lstsq(J, flux_vec, rcond=None)[0]
    return float(rates[0]), float(rates[1])


# ---------------------------------------------------------------------------
# ODE right-hand side
# ---------------------------------------------------------------------------

def adiabatic_rhs_pe(
    t: float,
    state: list[float],
    eta: float,
    flux_model: BaseFluxModel,
) -> list[float]:
    """RHS for the adiabatic (p, e) ODE system.

    Parameters
    ----------
    t : float
        Current coordinate time (unused explicitly, but required by solve_ivp).
    state : list[float]
        [p, e] — current orbital parameters.
    eta : float
        Mass ratio μ/M.
    flux_model : BaseFluxModel
        Instantiated flux model.

    Returns
    -------
    list[float]
        [dp/dt, de/dt]
    """
    p, e = state

    # Clamp e to avoid unphysical values
    e = max(e, 0.0)
    e = min(e, 0.9999)

    # Fluxes scaled by η (mass ratio enters as η² in Peters formula,
    # but the leading-order test-mass inspiral has η scaling in the force)
    # The standard convention: dE/dt_phys = η² * F_E(p,e) for test-mass
    dEdt = eta ** 2 * flux_model.flux_E(p, e)
    dLdt = eta ** 2 * flux_model.flux_L(p, e)

    dpdt, dedt = dpde_rates(p, e, dEdt, dLdt)
    return [dpdt, dedt]


# ---------------------------------------------------------------------------
# Inspiral integrator
# ---------------------------------------------------------------------------

def integrate_adiabatic_pe(
    orbit: OrbitParams,
    config: PhysicsConfig,
    t_max: float = 1e9,
    n_points: int = 5000,
) -> InspiralResult:
    """Integrate the adiabatic inspiral in (p, e) space.

    Integration stops when the orbit reaches the separatrix
    p ≤ 6 + 2*e + 0.05 (a small margin before the last stable orbit).

    Parameters
    ----------
    orbit : OrbitParams
        Initial orbital parameters (p₀, e₀).
    config : PhysicsConfig
        Physics configuration (η, flux model, ODE tolerances).
    t_max : float
        Maximum coordinate time to integrate over (geometrized units).
    n_points : int
        Number of output points (dense output via ``t_eval``).

    Returns
    -------
    InspiralResult
        Full inspiral trajectory and metadata.
    """
    flux_model = get_flux_model(config.flux_model)

    p0, e0 = orbit.p, orbit.e

    # --- Separatrix / plunge event (terminal) ---------------------------------
    def separatrix_event(t: float, state: list[float]) -> float:
        """Zero crossing when p = 6 + 2*e + margin."""
        p, e = state
        return p - (6.0 + 2.0 * max(e, 0.0) + 0.05)

    separatrix_event.terminal = True   # type: ignore[attr-defined]
    separatrix_event.direction = -1.0  # type: ignore[attr-defined]  # approaching from above

    # --- Eccentricity floor event (non-terminal guard) -----------------------
    def ecc_floor_event(t: float, state: list[float]) -> float:
        """Keep e ≥ 0 (non-terminal; integration continues)."""
        _, e = state
        return e

    ecc_floor_event.terminal = False   # type: ignore[attr-defined]
    ecc_floor_event.direction = -1.0   # type: ignore[attr-defined]

    t_span = (0.0, t_max)
    t_eval = np.linspace(0.0, t_max, n_points)

    sol = solve_ivp(
        fun=adiabatic_rhs_pe,
        t_span=t_span,
        y0=[p0, e0],
        method="DOP853",
        t_eval=t_eval,
        events=[separatrix_event, ecc_floor_event],
        rtol=config.rtol,
        atol=config.atol,
        args=(config.eta, flux_model),
        dense_output=False,
    )

    t_arr = sol.t
    p_arr = sol.y[0]
    e_arr = np.maximum(sol.y[1], 0.0)  # clamp floor

    # Determine whether we hit the separatrix
    plunged = (sol.status == 1) and (len(sol.t_events[0]) > 0)

    if sol.status == 0:
        message = "Integration completed: reached t_max without plunge."
    elif plunged:
        message = (
            f"Inspiral reached separatrix p = 6 + 2e + 0.05 at "
            f"t = {t_arr[-1]:.4g}, p = {p_arr[-1]:.4f}, e = {e_arr[-1]:.4f}."
        )
    else:
        message = f"Integration stopped: {sol.message}"

    # Compute E(t) and L(t) along the trajectory
    E_arr = np.array([pe_to_EL(p, e)[0] for p, e in zip(p_arr, e_arr)])
    L_arr = np.array([pe_to_EL(p, e)[1] for p, e in zip(p_arr, e_arr)])

    # Representative circular radius: r_circ = p (exact for e=0, approximate otherwise)
    r_circ = p_arr.copy()

    return InspiralResult(
        t=t_arr,
        p_arr=p_arr,
        e_arr=e_arr,
        E_arr=E_arr,
        L_arr=L_arr,
        r_circ=r_circ,
        plunged=plunged,
        message=message,
    )
