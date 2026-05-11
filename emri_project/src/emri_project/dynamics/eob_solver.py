"""EOB (Effective-One-Body) Hamiltonian solver for EMRI.

Replaces the geodesic Hamiltonian with the EOB Hamiltonian while keeping
the same integration architecture. In the limit η→0 recovers geodesic dynamics.

EOB Hamiltonian (non-spinning, equatorial):
  H_eff = sqrt(A(r) * (μ² + p_φ²/r² + p_r²/D(r)))
  H_EOB = M * sqrt(1 + 2η*(H_eff/μ - 1))

In reduced units (μ=M=1, η→0):
  H_eff = sqrt(A * (1 + p_φ²/r² + p_r²))   [D=1 at leading order]
  H_EOB → H_eff  (geodesic limit)

A(r) = 1 - 2/r + η * a_1sf(r) + ...
Here we implement the η=0 baseline (exact geodesic) and η≠0 PN-augmented version.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from emri_project.constants import RTOL, ATOL
from emri_project.dynamics.metric import lapse, dlapse_dr


# ---------------------------------------------------------------------------
# EOB potentials
# ---------------------------------------------------------------------------

def eob_A(r: NDArray, eta: float = 0.0) -> NDArray:
    """EOB A-potential. At η=0: Schwarzschild lapse."""
    A0 = lapse(r)
    if eta == 0.0:
        return A0
    # 5PN Padé-resummed A for small eta (simplified leading correction)
    # Based on Buonanno-Damour 1999 / Damour-Nagar 2014
    # A(r) ≈ 1 - 2/r + 2η/r³ (1PN self-force inspired correction)
    return A0 + eta * (2.0 / r**3)


def eob_D(r: NDArray, eta: float = 0.0) -> NDArray:
    """EOB D-potential (appears in p_r² term). D=1 in simplest gauge."""
    return np.ones_like(r)


def eob_dA_dr(r: NDArray, eta: float = 0.0) -> NDArray:
    """dA/dr."""
    dA0 = dlapse_dr(r)
    if eta == 0.0:
        return dA0
    return dA0 - 6.0 * eta / r**4


# ---------------------------------------------------------------------------
# EOB Hamiltonian and equations of motion
# ---------------------------------------------------------------------------

def eob_H_eff(r: NDArray, pr: NDArray, pphi: float, eta: float) -> NDArray:
    """H_eff = sqrt(A * (1 + p_φ²/r² + p_r²/D))."""
    A = eob_A(r, eta)
    D = eob_D(r, eta)
    return np.sqrt(A * (1.0 + pphi**2 / r**2 + pr**2 / D))


def eob_H_real(r: NDArray, pr: NDArray, pphi: float, eta: float) -> NDArray:
    """H_EOB = (1/η)*sqrt(1 + 2η*(H_eff - 1)) - 1/η.

    Limit η→0: H_EOB → H_eff - 1 + 1/2 (shift to match geodesic convention).
    """
    H_eff = eob_H_eff(r, pr, pphi, eta)
    if eta < 1e-15:
        return H_eff - 1.0
    return (1.0 / eta) * np.sqrt(1.0 + 2.0 * eta * (H_eff - 1.0)) - 1.0 / eta


def eob_rhs(tau: float, state: NDArray, pphi: float, eta: float) -> NDArray:
    """EOB Hamilton equations (Poisson bracket structure).

    state = [t, r, phi, pr]
    Canonical pair: (r, pr), (φ, p_φ), (t, p_t=-H_EOB)
    """
    _t, r, _phi, pr = state
    A = eob_A(r, eta)
    D = eob_D(r, eta)
    dA = eob_dA_dr(r, eta)
    H_eff = eob_H_eff(r, pr, pphi, eta)

    # dH_eff/dp_r = A*p_r/(D*H_eff)
    dHeff_dpr = A * pr / (D * H_eff)
    # dH_eff/dr
    dHeff_dr = (dA * (1.0 + pphi**2 / r**2 + pr**2 / D)
                - 2.0 * A * pphi**2 / r**3) / (2.0 * H_eff)

    if eta < 1e-15:
        dHreal_dpr = dHeff_dpr
        dHreal_dr = dHeff_dr
    else:
        sqrt_arg = 1.0 + 2.0 * eta * (H_eff - 1.0)
        dHreal_dpr = dHeff_dpr / np.sqrt(sqrt_arg)
        dHreal_dr = dHeff_dr / np.sqrt(sqrt_arg)

    dr_dtau   = dHreal_dpr
    dphi_dtau = pphi / (r**2 * H_eff) if eta < 1e-15 else pphi / (r**2 * H_eff / np.sqrt(1.0 + 2.0 * eta * (H_eff - 1.0)))
    dt_dtau   = 1.0  # coordinate time ~ proper time at leading order
    dpr_dtau  = -dHreal_dr

    return np.array([dt_dtau, dr_dtau, dphi_dtau, dpr_dtau])


def eob_circular_L(r: float, eta: float = 0.0) -> float:
    """L for circular EOB orbit: dH/dr = 0 at p_r=0."""
    from scipy.optimize import brentq
    A = eob_A(np.array([r]), eta)[0]
    dA = eob_dA_dr(np.array([r]), eta)[0]
    # dH_eff/dr = 0 at p_r=0:
    # dA*(1 + L²/r²) - 2*A*L²/r³ = 0
    # L² = dA * r³ / (2A - dA*r)
    numer = dA * r**3
    denom = 2.0 * A - dA * r
    if denom <= 0:
        raise ValueError(f"No circular orbit at r={r} for eta={eta}")
    return np.sqrt(numer / denom)


def integrate_eob(
    r0: float,
    eta: float = 1e-5,
    tau_max: float = 5000.0,
    n_points: int = 50000,
    rtol: float = RTOL,
    atol: float = ATOL,
) -> dict:
    """Integrate EOB orbit starting from circular orbit at r0."""
    pphi = eob_circular_L(r0, eta)
    state0 = np.array([0.0, r0, 0.0, 0.0])

    def plunge_event(tau: float, y: NDArray, pphi: float, eta: float) -> float:
        return y[1] - 2.1
    plunge_event.terminal = True  # type: ignore[attr-defined]
    plunge_event.direction = -1.0  # type: ignore[attr-defined]

    tau_span = (0.0, tau_max)
    tau_eval = np.linspace(0.0, tau_max, n_points)

    sol = solve_ivp(
        eob_rhs,
        tau_span,
        state0,
        args=(pphi, eta),
        method="DOP853",
        t_eval=tau_eval,
        rtol=rtol,
        atol=atol,
        events=[plunge_event],
    )
    return {
        'tau': sol.t,
        't': sol.y[0],
        'r': sol.y[1],
        'phi': sol.y[2],
        'pr': sol.y[3],
        'pphi': pphi,
        'eta': eta,
        'success': sol.success,
    }
