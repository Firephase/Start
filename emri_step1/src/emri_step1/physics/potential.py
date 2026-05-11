"""
Effective potential for Schwarzschild geodesics.

  V_eff(r; L) = (1 - 2/r)(1 + L²/r²)

Radial equation:   (dr/dτ)² = E² - V_eff(r; L)
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from typing import Sequence
import sympy as sp


@dataclass
class TurningPointResult:
    """Roots of E² = V_eff(r; L) inside a search window."""

    r_peri: float | None          # inner turning point (periastron)
    r_apo: float | None           # outer turning point (apastron)
    is_bound: bool
    is_circular: bool
    allowed_region_exists: bool
    message: str


class EffectivePotential:
    """Compute and analyse the Schwarzschild effective potential."""

    def __init__(self, L: float) -> None:
        self.L = L
        self._build_symbolic()

    # ------------------------------------------------------------------
    # Symbolic tools
    # ------------------------------------------------------------------
    def _build_symbolic(self) -> None:
        r, L = sp.symbols("r L", positive=True, real=True)
        self._r_sym = r
        self._L_sym = L
        self._Veff_sym = (1 - 2 / r) * (1 + L**2 / r**2)
        self._dVeff_sym = sp.diff(self._Veff_sym, r)

    # ------------------------------------------------------------------
    # Numerical evaluation
    # ------------------------------------------------------------------
    def __call__(self, r: np.ndarray | float) -> np.ndarray | float:
        """V_eff(r; L)."""
        r = np.asarray(r, dtype=float)
        L = self.L
        return (1.0 - 2.0 / r) * (1.0 + L**2 / r**2)

    def dVeff_dr(self, r: np.ndarray | float) -> np.ndarray | float:
        """dV_eff/dr (analytical)."""
        r = np.asarray(r, dtype=float)
        L = self.L
        # d/dr [(1 - 2/r)(1 + L²/r²)]
        return (2.0 / r**2) * (1.0 + L**2 / r**2) + (1.0 - 2.0 / r) * (-2.0 * L**2 / r**3)

    # ------------------------------------------------------------------
    # Turning points  E² = V_eff(r)
    # ------------------------------------------------------------------
    def find_turning_points(
        self,
        E: float,
        r_min: float = 2.1,
        r_max: float = 1000.0,
        n_grid: int = 5000,
    ) -> TurningPointResult:
        """
        Find inner and outer turning points by sign-change root-finding on
        E² - V_eff(r) = 0 within [r_min, r_max].
        """
        from scipy.optimize import brentq

        E2 = E**2

        # Coarse grid scan
        r_grid = np.linspace(r_min, r_max, n_grid)
        g = E2 - self(r_grid)

        # Find sign changes
        roots: list[float] = []
        for i in range(len(g) - 1):
            if np.isnan(g[i]) or np.isnan(g[i + 1]):
                continue
            if g[i] * g[i + 1] < 0:
                try:
                    root = brentq(lambda rr: E2 - self(rr), r_grid[i], r_grid[i + 1], xtol=1e-12)
                    roots.append(root)
                except ValueError:
                    pass

        if len(roots) == 0:
            # Check if E² > V_eff everywhere above horizon → unbound plunge
            if np.all(g > 0):
                return TurningPointResult(
                    r_peri=None, r_apo=None,
                    is_bound=False, is_circular=False,
                    allowed_region_exists=True,
                    message="E² > V_eff for all r > 2: unbound/plunge trajectory.",
                )
            return TurningPointResult(
                r_peri=None, r_apo=None,
                is_bound=False, is_circular=False,
                allowed_region_exists=False,
                message="No allowed region found for given E, L.",
            )

        roots_sorted = sorted(roots)

        # The physical bound orbit occupies the OUTERMOST allowed region between two
        # consecutive roots where E² >= V_eff.  The innermost root (near the horizon)
        # is the inner boundary of the plunge zone, not the periastron of a bound orbit.
        # We find the outermost adjacent pair that brackets an E²>=V_eff region.
        outer_pair: tuple[float, float] | None = None
        for i in range(len(roots_sorted) - 1):
            ra, rb = roots_sorted[i], roots_sorted[i + 1]
            r_mid = 0.5 * (ra + rb)
            if E2 - self(r_mid) >= 0:
                outer_pair = (ra, rb)  # keep updating to get outermost

        if outer_pair is None:
            # All adjacent pairs are in forbidden regions → only plunge zone
            if len(roots_sorted) == 1:
                return TurningPointResult(
                    r_peri=None, r_apo=None,
                    is_bound=False, is_circular=False,
                    allowed_region_exists=True,
                    message="Only inner (plunge-zone) root found; no outer bound orbit.",
                )
            return TurningPointResult(
                r_peri=None, r_apo=None,
                is_bound=False, is_circular=False,
                allowed_region_exists=False,
                message="No outer bound orbit region detected.",
            )

        r_peri, r_apo = outer_pair
        is_circ = abs(r_peri - r_apo) < 0.01

        return TurningPointResult(
            r_peri=r_peri, r_apo=r_apo,
            is_bound=True, is_circular=is_circ,
            allowed_region_exists=True,
            message=f"Bound orbit: r_peri={r_peri:.6f}, r_apo={r_apo:.6f}.",
        )

    # ------------------------------------------------------------------
    # Circular orbit locus
    # ------------------------------------------------------------------
    def circular_orbit_radius_from_L(self) -> list[float]:
        """
        Find r values of circular orbits for this L by solving dV_eff/dr = 0.
        Returns up to two solutions (stable + unstable).
        """
        from scipy.optimize import brentq

        L = self.L
        # dV_eff/dr = 0  →  polynomial equation in r
        # Analytical: r² - L²·r + 3·L² = 0  (from standard derivation)
        # => r = [L² ± sqrt(L⁴ - 12·L²)] / 2
        disc = L**4 - 12.0 * L**2
        if disc < 0:
            return []  # no real circular orbits
        sqrt_disc = np.sqrt(disc)
        r1 = (L**2 - sqrt_disc) / 2.0
        r2 = (L**2 + sqrt_disc) / 2.0
        return sorted([r for r in [r1, r2] if r > 2.0])

    # ------------------------------------------------------------------
    # Plot data helper
    # ------------------------------------------------------------------
    def plot_data(
        self, r_range: tuple[float, float] = (2.1, 30.0), n: int = 800
    ) -> tuple[np.ndarray, np.ndarray]:
        r_arr = np.linspace(r_range[0], r_range[1], n)
        return r_arr, self(r_arr)
