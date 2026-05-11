"""EOB inspiral integrator.

Integrates the EOB equations of motion for a quasi-circular inspiral from
an initial radius r0 down to the ISCO (r = 6 M in Schwarzschild coordinates).

State vector: [r, p_r, φ, p_φ]

The ODE is driven by:
    - Conservative Hamiltonian forces (via EOBHamiltonian.rhs)
    - Radiation-reaction azimuthal force dp_φ/dt = -η · dL/dt
      (via EOBRadiationReaction.azimuthal_force)

The integration terminates when r drops below 6.05 M (slightly outside
the Schwarzschild ISCO to avoid the divergence in the circular angular
momentum).
"""
from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

from .config import EOBConfig, EOBState
from .hamiltonian import EOBHamiltonian
from .radiation_reaction import EOBRadiationReaction


# ---------------------------------------------------------------------------
# ODE right-hand side
# ---------------------------------------------------------------------------

def _eob_rhs(
    t: float,
    state: np.ndarray,
    cfg: EOBConfig,
    ham: EOBHamiltonian,
    rr: EOBRadiationReaction,
) -> np.ndarray:
    """RHS callback for ``scipy.integrate.solve_ivp``.

    Parameters
    ----------
    t : float
        Current time (unused directly; required by the solve_ivp API).
    state : np.ndarray
        Phase-space vector [r, p_r, φ, p_φ].
    cfg : EOBConfig
        EOB configuration (conservative model, flux model, …).
    ham : EOBHamiltonian
        Pre-constructed Hamiltonian evaluator.
    rr : EOBRadiationReaction
        Pre-constructed radiation-reaction handler.

    Returns
    -------
    np.ndarray
        Time derivatives [dr/dt, dp_r/dt, dφ/dt, dp_φ/dt].
    """
    r, pr, phi, pphi = state

    # Build orbit-state dict for the flux model (circular approximation: p ≈ r)
    orbit_state = {
        "r": float(r),
        "p": float(r),
        "e": 0.0,
        "eta": cfg.eta,
    }

    F_phi = rr.azimuthal_force(orbit_state, {}, cfg)
    F_r = rr.radial_force(orbit_state, {}, cfg)

    return ham.rhs(t, state, cfg, F_phi=F_phi, F_r=F_r)


# ---------------------------------------------------------------------------
# ISCO terminal event
# ---------------------------------------------------------------------------

def _isco_event(
    t: float,
    state: np.ndarray,
    cfg: EOBConfig,
    ham: EOBHamiltonian,
    rr: EOBRadiationReaction,
) -> float:
    """Event function: zero-crossing when r passes through r_ISCO + small buffer."""
    return state[0] - 6.05


_isco_event.terminal = True   # type: ignore[attr-defined]
_isco_event.direction = -1    # type: ignore[attr-defined]  # trigger on decreasing r


# ---------------------------------------------------------------------------
# Public integration routine
# ---------------------------------------------------------------------------

def integrate_eob(
    r0: float,
    pphi0: float | None = None,
    cfg: EOBConfig = EOBConfig(),
    t_max: float = 1e7,
    n_points: int = 5000,
) -> EOBState:
    """Integrate an EOB quasi-circular inspiral from initial radius ``r0``.

    The integration proceeds from t = 0 to ``t_max`` (or until the ISCO
    termination event fires) using the DOP853 explicit Runge-Kutta method.

    Parameters
    ----------
    r0 : float
        Initial orbital radius in units of M (must satisfy r0 > 6).
    pphi0 : float | None
        Initial angular momentum p_φ.  Defaults to the Schwarzschild
        circular-orbit value L_circ(r0) = r0 / √(r0 − 3).
    cfg : EOBConfig
        EOB run configuration.
    t_max : float
        Maximum integration time in units of M.
    n_points : int
        Number of output time points (linspace from 0 to t_max).

    Returns
    -------
    EOBState
        Arrays of (t, r, p_r, φ, p_φ, H_eff, H_real) along the integrated
        trajectory.
    """
    ham = EOBHamiltonian()
    rr = EOBRadiationReaction()

    # Default initial angular momentum: circular orbit in Schwarzschild
    if pphi0 is None:
        denom = max(r0 - 3.0, 0.1)
        pphi0 = r0 / np.sqrt(denom)

    # Circular orbit → p_r = 0 initially
    state0 = np.array([float(r0), 0.0, 0.0, float(pphi0)])

    t_eval = np.linspace(0.0, t_max, max(n_points, 2))

    sol = solve_ivp(
        _eob_rhs,
        (0.0, t_max),
        state0,
        method="DOP853",
        t_eval=t_eval,
        events=[_isco_event],
        args=(cfg, ham, rr),
        rtol=1e-9,
        atol=1e-9,
        dense_output=False,
    )

    t = sol.t
    r = sol.y[0]
    pr = sol.y[1]
    phi = sol.y[2]
    pphi = sol.y[3]

    # Evaluate Hamiltonians along the stored trajectory
    heff_arr = np.array(
        [ham.heff(sol.y[:, i], cfg) for i in range(len(t))]
    )
    hreal_arr = np.array(
        [ham.hreal(sol.y[:, i], cfg) for i in range(len(t))]
    )

    return EOBState(
        t=t,
        r=r,
        pr=pr,
        phi=phi,
        pphi=pphi,
        heff=heff_arr,
        hreal=hreal_arr,
    )
