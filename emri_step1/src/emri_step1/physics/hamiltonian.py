"""
Symbolic derivation of the Schwarzschild geodesic Hamiltonian via SymPy.

All quantities in units G = c = M = 1.  Motion restricted to equatorial plane θ = π/2.

Superhamiltonian:  H = ½ g^{μν} p_μ p_ν
Schwarzschild:     f(r) = 1 - 2/r
                   H = ½ [ -pt²/f + f·pr² + pφ²/r² ]
Timelike constraint: H = -½
Conserved:         E = -pt,  L = pφ
"""

from __future__ import annotations

import sympy as sp
from functools import cached_property
from typing import Callable


class SchwarzschildHamiltonian:
    """
    Derives and compiles the Schwarzschild geodesic Hamiltonian symbolically.

    Use ``rhs`` to get a compiled callable suitable for scipy integrators.
    The state vector is  y = [t, r, φ, p_r]  with p_t = -E, p_φ = L fixed.
    """

    def __init__(self) -> None:
        self._build_symbols()
        self._build_hamiltonian()
        self._build_equations_of_motion()

    # ------------------------------------------------------------------
    # Symbol construction
    # ------------------------------------------------------------------
    def _build_symbols(self) -> None:
        self.tau = sp.Symbol("tau", real=True, positive=True)
        self.r, self.t, self.phi = sp.symbols("r t phi", real=True)
        self.p_t, self.p_r, self.p_phi = sp.symbols("p_t p_r p_phi", real=True)
        self.E_sym, self.L_sym = sp.symbols("E L", real=True, positive=True)

    # ------------------------------------------------------------------
    # Hamiltonian
    # ------------------------------------------------------------------
    def _build_hamiltonian(self) -> None:
        r, p_t, p_r, p_phi = self.r, self.p_t, self.p_r, self.p_phi

        self.f_expr = 1 - sp.Integer(2) / r
        f = self.f_expr

        # H = ½ [ -pt²/f + f·pr² + pφ²/r² ]
        self.H_expr = sp.Rational(1, 2) * (
            -p_t**2 / f + f * p_r**2 + p_phi**2 / r**2
        )

    # ------------------------------------------------------------------
    # Equations of motion via Hamilton's equations
    # ------------------------------------------------------------------
    def _build_equations_of_motion(self) -> None:
        r, t, phi = self.r, self.t, self.phi
        p_t, p_r, p_phi = self.p_t, self.p_r, self.p_phi
        E, L = self.E_sym, self.L_sym
        H = self.H_expr

        # Substitute conserved quantities  p_t = -E,  p_phi = L
        subs = {p_t: -E, p_phi: L}

        H_reduced = H.subs(subs)
        self.H_reduced_expr = H_reduced

        # Hamilton's equations
        # ṫ   = ∂H/∂p_t = -∂H/∂E  (after substitution we differentiate wrt p_t before sub)
        dt_dtau_raw = sp.diff(H, p_t).subs(subs)
        # ṙ   = ∂H/∂p_r
        dr_dtau_raw = sp.diff(H, p_r).subs(subs)
        # φ̇  = ∂H/∂p_phi = ∂H/∂L
        dphi_dtau_raw = sp.diff(H, p_phi).subs(subs)
        # ṗ_r = -∂H/∂r
        dpr_dtau_raw = -sp.diff(H_reduced, r)

        # Simplify
        self.dt_dtau_expr   = sp.simplify(dt_dtau_raw)
        self.dr_dtau_expr   = sp.simplify(dr_dtau_raw)
        self.dphi_dtau_expr = sp.simplify(dphi_dtau_raw)
        self.dpr_dtau_expr  = sp.simplify(dpr_dtau_raw)

    # ------------------------------------------------------------------
    # Compiled callables
    # ------------------------------------------------------------------
    @cached_property
    def _rhs_lambdified(self) -> Callable:
        """Lambdify the RHS into a fast numpy callable."""
        r, p_r = self.r, self.p_r
        E, L = self.E_sym, self.L_sym

        exprs = [
            self.dt_dtau_expr,
            self.dr_dtau_expr,
            self.dphi_dtau_expr,
            self.dpr_dtau_expr,
        ]
        return sp.lambdify([r, p_r, E, L], exprs, modules="numpy")

    def rhs(self, E: float, L: float) -> Callable[[float, list[float]], list[float]]:
        """
        Return a scipy-compatible RHS function  f(tau, y) -> dy/dtau.

        State vector:  y = [t, r, phi, p_r]
        """
        fn = self._rhs_lambdified

        def _rhs(tau: float, y: list[float]) -> list[float]:
            _t, r_val, _phi, pr_val = y
            dt, dr, dphi, dpr = fn(r_val, pr_val, E, L)
            return [float(dt), float(dr), float(dphi), float(dpr)]

        return _rhs

    def hamiltonian_value(self, r: float, pr: float, E: float, L: float) -> float:
        """Evaluate H at a point; should equal -½ for timelike geodesics."""
        f = 1.0 - 2.0 / r
        return 0.5 * (-(E**2) / f + f * pr**2 + L**2 / r**2)

    # ------------------------------------------------------------------
    # Pretty display helpers
    # ------------------------------------------------------------------
    def print_summary(self) -> None:
        """Print the symbolic Hamiltonian and equations of motion."""
        print("=" * 60)
        print("Schwarzschild Superhamiltonian (equatorial, G=c=M=1)")
        print("=" * 60)
        print(f"  f(r)  = {self.f_expr}")
        print(f"  H     = {self.H_expr}")
        print(f"  H_red = {self.H_reduced_expr}  (p_t=-E, p_phi=L)")
        print()
        print("Equations of motion (dot = d/dτ):")
        print(f"  ṫ     = {self.dt_dtau_expr}")
        print(f"  ṙ     = {self.dr_dtau_expr}")
        print(f"  φ̇    = {self.dphi_dtau_expr}")
        print(f"  ṗ_r   = {self.dpr_dtau_expr}")
        print("=" * 60)

    def latex_summary(self) -> dict[str, str]:
        """Return LaTeX strings for display in Streamlit."""
        return {
            "f(r)": sp.latex(self.f_expr),
            "H": sp.latex(self.H_expr),
            "H_reduced": sp.latex(self.H_reduced_expr),
            "dt_dtau": sp.latex(self.dt_dtau_expr),
            "dr_dtau": sp.latex(self.dr_dtau_expr),
            "dphi_dtau": sp.latex(self.dphi_dtau_expr),
            "dpr_dtau": sp.latex(self.dpr_dtau_expr),
        }
