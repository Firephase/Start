"""
Numerical geodesic integrator for Schwarzschild spacetime.

State vector:  y = [t, r, φ, p_r]
Integrators: DOP853 (default), Radau (stiff fallback)
"""

from __future__ import annotations

import time
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from scipy.integrate import solve_ivp
from typing import Callable

from emri_step1.physics.hamiltonian import SchwarzschildHamiltonian
from emri_step1.models.parameters import SolverConfig


@dataclass
class GeodesicResult:
    """Container for integration output and diagnostics."""

    tau: np.ndarray
    t: np.ndarray
    r: np.ndarray
    phi: np.ndarray
    p_r: np.ndarray
    E: float
    L: float

    # Diagnostics
    H_values: np.ndarray         # Hamiltonian along trajectory
    H_residual: np.ndarray       # H - (-0.5)
    solver_success: bool
    solver_message: str
    n_steps: int
    wall_time: float             # integration time in seconds

    # Derived
    x: np.ndarray = field(default_factory=lambda: np.array([]))
    y_cart: np.ndarray = field(default_factory=lambda: np.array([]))

    def __post_init__(self) -> None:
        self.x = self.r * np.cos(self.phi)
        self.y_cart = self.r * np.sin(self.phi)

    # ------------------------------------------------------------------
    # Diagnostics helpers
    # ------------------------------------------------------------------
    @property
    def H_max_drift(self) -> float:
        return float(np.max(np.abs(self.H_residual)))

    @property
    def r_min(self) -> float:
        return float(np.min(self.r))

    @property
    def r_max(self) -> float:
        return float(np.max(self.r))

    @property
    def is_plunge(self) -> bool:
        return self.r_min <= 2.1

    @property
    def estimated_radial_period(self) -> float | None:
        """Estimate τ-period from r(τ) via zero crossings of ṙ."""
        r = self.r
        r_mean = 0.5 * (r.max() + r.min())
        crossings = np.where(np.diff(np.sign(r - r_mean)))[0]
        if len(crossings) < 2:
            return None
        # Each pair of crossings = half-period
        periods = np.diff(self.tau[crossings])
        full = periods[::2]  # every other crossing = full period
        if len(full) == 0:
            return None
        return float(np.mean(full)) * 2

    def to_dataframe(self) -> pd.DataFrame:
        """Export trajectory as a pandas DataFrame."""
        return pd.DataFrame({
            "tau": self.tau,
            "t": self.t,
            "r": self.r,
            "phi": self.phi,
            "p_r": self.p_r,
            "x": self.x,
            "y": self.y_cart,
            "H": self.H_values,
            "H_residual": self.H_residual,
        })


class GeodesicSolver:
    """
    Integrate geodesic equations in Schwarzschild spacetime.

    The Hamiltonian RHS is derived symbolically and compiled to numpy
    via SchwarzschildHamiltonian.
    """

    def __init__(self, hamiltonian: SchwarzschildHamiltonian | None = None) -> None:
        self.ham = hamiltonian or SchwarzschildHamiltonian()

    # ------------------------------------------------------------------
    # Initial conditions
    # ------------------------------------------------------------------
    def initial_conditions(
        self,
        r0: float,
        phi0: float,
        E: float,
        L: float,
        pr0: float,
        t0: float = 0.0,
    ) -> list[float]:
        """Build state vector y0 = [t0, r0, phi0, pr0]."""
        return [t0, r0, phi0, pr0]

    def ic_from_circular(self, r0: float, phi0: float = 0.0) -> tuple[float, float, list[float]]:
        """
        Compute (E, L) for circular orbit at r0 and return (E, L, y0).
        Sets pr0 = 0 for circular orbit.
        """
        from emri_step1.physics.circular import CircularOrbitAnalyzer
        info = CircularOrbitAnalyzer().analyze(r0)
        y0 = self.initial_conditions(r0, phi0, info.E, info.L, pr0=0.0)
        return info.E, info.L, y0

    def ic_from_turning_points(
        self, r_peri: float, r_apo: float, phi0: float = 0.0
    ) -> tuple[float, float, list[float]]:
        """Compute (E, L, y0) from turning points; start at apastron (pr0=0)."""
        from emri_step1.physics.circular import CircularOrbitAnalyzer
        E, L = CircularOrbitAnalyzer.turning_points_to_EL(r_peri, r_apo)
        y0 = self.initial_conditions(r_apo, phi0, E, L, pr0=0.0)
        return E, L, y0

    # ------------------------------------------------------------------
    # Event functions
    # ------------------------------------------------------------------
    @staticmethod
    def _horizon_event(tau: float, y: list[float], *args: float) -> float:
        """Stop integration when r approaches horizon r=2."""
        return y[1] - 2.05

    _horizon_event.terminal = True   # type: ignore[attr-defined]
    _horizon_event.direction = -1    # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Integrate
    # ------------------------------------------------------------------
    def run(
        self,
        E: float,
        L: float,
        y0: list[float],
        cfg: SolverConfig | None = None,
    ) -> GeodesicResult:
        """
        Integrate the geodesic equations and return a GeodesicResult.
        """
        if cfg is None:
            from emri_step1.models.parameters import SolverConfig
            cfg = SolverConfig()

        rhs = self.ham.rhs(E, L)
        tau_span = (0.0, cfg.tau_max)
        t_eval = np.linspace(0.0, cfg.tau_max, cfg.n_output)

        events = [self._horizon_event] if cfg.stop_at_horizon else []

        t0 = time.perf_counter()
        sol = solve_ivp(
            rhs,
            tau_span,
            y0,
            method=cfg.integrator,
            t_eval=t_eval,
            rtol=cfg.rtol,
            atol=cfg.atol,
            max_step=cfg.max_step,
            events=events,
            dense_output=False,
        )
        wall = time.perf_counter() - t0

        # Fall back to Radau if primary integrator fails
        if not sol.success and cfg.integrator != "Radau":
            sol = solve_ivp(
                rhs,
                tau_span,
                y0,
                method="Radau",
                t_eval=t_eval,
                rtol=cfg.rtol,
                atol=cfg.atol,
                max_step=cfg.max_step,
                events=events,
            )

        tau_arr = sol.t
        t_arr   = sol.y[0]
        r_arr   = sol.y[1]
        phi_arr = sol.y[2]
        pr_arr  = sol.y[3]

        # Compute Hamiltonian constraint along trajectory
        H_arr = np.array([
            self.ham.hamiltonian_value(r_arr[i], pr_arr[i], E, L)
            for i in range(len(tau_arr))
        ])
        H_res = H_arr - (-0.5)

        return GeodesicResult(
            tau=tau_arr,
            t=t_arr,
            r=r_arr,
            phi=phi_arr,
            p_r=pr_arr,
            E=E,
            L=L,
            H_values=H_arr,
            H_residual=H_res,
            solver_success=sol.success,
            solver_message=sol.message,
            n_steps=len(tau_arr),
            wall_time=wall,
        )
