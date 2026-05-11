"""Geodesic solver for test-particle motion in Schwarzschild spacetime.

Solves Hamilton equations using scipy.integrate.solve_ivp with high-order
adaptive integrator (DOP853). Provides:
- Initial condition generators (circular, perturbed, eccentric)
- Orbit integration with event detection (plunge, turning points)
- Hamiltonian / energy / angular momentum drift diagnostics
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from emri_project.constants import R_ISCO, RTOL, ATOL
from emri_project.dynamics.hamiltonian import geodesic_rhs, superhamiltonian
from emri_project.dynamics.metric import lapse


# ---------------------------------------------------------------------------
# Circular orbit helpers
# ---------------------------------------------------------------------------

def circular_E(r: float) -> float:
    """E for circular orbit at r > 3 (Schwarzschild)."""
    return (r - 2.0) / np.sqrt(r * (r - 3.0))


def circular_L(r: float) -> float:
    """L for circular orbit at r > 3 (Schwarzschild)."""
    return r / np.sqrt(r - 3.0)


def effective_potential(r: NDArray, E: float, L: float) -> NDArray:
    """V_eff(r) = f(r)*(1 + L²/r²).  Turning points: V_eff = E²."""
    f = lapse(r)
    return f * (1.0 + L**2 / r**2)


# ---------------------------------------------------------------------------
# Initial conditions
# ---------------------------------------------------------------------------

def ic_circular(r0: float) -> tuple[NDArray, float, float]:
    """Initial state [t,r,φ,pr] for a circular orbit at r0."""
    if r0 <= R_ISCO:
        raise ValueError(f"r0={r0} <= r_ISCO=6; unstable circular orbit.")
    E = circular_E(r0)
    L = circular_L(r0)
    state0 = np.array([0.0, r0, 0.0, 0.0])
    return state0, E, L


def ic_perturbed_circular(r0: float, dr: float = 0.1) -> tuple[NDArray, float, float]:
    """Perturb circular orbit slightly in r, keep same E, L."""
    state0, E, L = ic_circular(r0)
    state0[1] += dr
    return state0, E, L


def ic_eccentric(r_apo: float, r_peri: float) -> tuple[NDArray, float, float]:
    """Eccentric bound orbit with given apocenter and pericenter.

    At turning points: p_r = 0 and E² = V_eff(r).
    Solve for E, L from V_eff(r_apo) = V_eff(r_peri) = E².
    """
    if r_peri < 4.0 or r_apo <= r_peri:
        raise ValueError("Invalid apocenter/pericenter for bound orbit.")

    def equations(EL: NDArray) -> NDArray:
        E, L = EL
        f_apo = lapse(r_apo)
        f_peri = lapse(r_peri)
        Veff_apo = f_apo * (1.0 + L**2 / r_apo**2) - E**2
        Veff_peri = f_peri * (1.0 + L**2 / r_peri**2) - E**2
        return np.array([Veff_apo, Veff_peri])

    from scipy.optimize import fsolve
    E0 = circular_E(0.5 * (r_apo + r_peri))
    L0 = circular_L(0.5 * (r_apo + r_peri))
    EL, info, ier, msg = fsolve(equations, [E0, L0], full_output=True)
    if ier != 1:
        raise RuntimeError(f"ic_eccentric failed: {msg}")
    E, L = float(EL[0]), float(EL[1])
    state0 = np.array([0.0, r_apo, 0.0, 0.0])
    return state0, E, L


# ---------------------------------------------------------------------------
# Orbit result container
# ---------------------------------------------------------------------------

@dataclass
class OrbitSolution:
    """Container for integrated geodesic trajectory."""
    tau: NDArray
    t: NDArray
    r: NDArray
    phi: NDArray
    pr: NDArray
    E: float
    L: float
    success: bool
    message: str

    @property
    def x(self) -> NDArray:
        return self.r * np.cos(self.phi)

    @property
    def y(self) -> NDArray:
        return self.r * np.sin(self.phi)

    def hamiltonian_drift(self) -> NDArray:
        """H(τ) + 1/2; should be 0."""
        return superhamiltonian(self.r, self.pr, self.E, self.L) + 0.5

    def energy_drift(self) -> NDArray:
        """Relative drift of E: always 0 for geodesic (conserved by construction)."""
        return np.zeros_like(self.tau)

    def angular_momentum_drift(self) -> NDArray:
        """Relative drift of L: always 0 for geodesic."""
        return np.zeros_like(self.tau)


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def integrate_geodesic(
    state0: NDArray,
    E: float,
    L: float,
    tau_max: float = 5000.0,
    n_points: int = 50000,
    rtol: float = RTOL,
    atol: float = ATOL,
    method: str = "DOP853",
) -> OrbitSolution:
    """Integrate Schwarzschild geodesic from state0 = [t, r, φ, p_r].

    Event detection:
    - plunge: r < 2.1 (near horizon)
    - escape: r > 1000
    """
    tau_span = (0.0, tau_max)
    tau_eval = np.linspace(0.0, tau_max, n_points)

    def plunge_event(tau: float, y: NDArray, E: float, L: float) -> float:
        return y[1] - 2.1
    plunge_event.terminal = True  # type: ignore[attr-defined]
    plunge_event.direction = -1.0  # type: ignore[attr-defined]

    def escape_event(tau: float, y: NDArray, E: float, L: float) -> float:
        return y[1] - 1000.0
    escape_event.terminal = True  # type: ignore[attr-defined]
    escape_event.direction = 1.0  # type: ignore[attr-defined]

    sol = solve_ivp(
        geodesic_rhs,
        tau_span,
        state0,
        args=(E, L),
        method=method,
        t_eval=tau_eval,
        rtol=rtol,
        atol=atol,
        events=[plunge_event, escape_event],
        dense_output=False,
    )

    return OrbitSolution(
        tau=sol.t,
        t=sol.y[0],
        r=sol.y[1],
        phi=sol.y[2],
        pr=sol.y[3],
        E=E,
        L=L,
        success=sol.success,
        message=sol.message,
    )
