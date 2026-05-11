"""
Circular orbit analysis for Schwarzschild geodesics.

Conditions:   ṙ = 0,   dV_eff/dr = 0
Formulas (r > 3):
    E(r) = (1 - 2/r) / sqrt(1 - 3/r)
    L(r) = r / sqrt(r - 3)

ISCO at r = 6  (innermost stable circular orbit).
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class CircularOrbitInfo:
    r0: float
    E: float
    L: float
    is_stable: bool
    is_isco: bool
    omega: float          # angular velocity dφ/dt
    T_phi: float          # azimuthal period in coordinate time
    T_tau: float          # azimuthal period in proper time
    v_circ: float         # local circular velocity (for reference)


class CircularOrbitAnalyzer:
    """Compute circular orbit parameters in Schwarzschild geometry."""

    ISCO_RADIUS: float = 6.0
    PHOTON_SPHERE: float = 3.0
    HORIZON: float = 2.0

    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Core formulas
    # ------------------------------------------------------------------
    @staticmethod
    def E_circular(r: float) -> float:
        """E(r) = (1 - 2/r) / sqrt(1 - 3/r),  valid for r > 3."""
        if r <= 3.0:
            raise ValueError(f"Circular orbit requires r > 3; got r={r}")
        return (1.0 - 2.0 / r) / np.sqrt(1.0 - 3.0 / r)

    @staticmethod
    def L_circular(r: float) -> float:
        """L(r) = r / sqrt(r - 3),  valid for r > 3."""
        if r <= 3.0:
            raise ValueError(f"Circular orbit requires r > 3; got r={r}")
        return r / np.sqrt(r - 3.0)

    @staticmethod
    def is_stable(r: float) -> bool:
        """Stable iff r >= ISCO = 6."""
        return r >= CircularOrbitAnalyzer.ISCO_RADIUS

    @staticmethod
    def omega_circular(r: float) -> float:
        """Angular velocity dφ/dt = 1 / r^{3/2}  (Kepler in GR)."""
        return 1.0 / r**1.5

    @staticmethod
    def T_phi_coordinate(r: float) -> float:
        """Coordinate-time period T = 2π r^{3/2}."""
        return 2.0 * np.pi * r**1.5

    @staticmethod
    def T_phi_proper(r: float) -> float:
        """Proper-time period τ = T_coord * sqrt(1 - 3/r)."""
        if r <= 3.0:
            raise ValueError(f"r must be > 3; got r={r}")
        return 2.0 * np.pi * r**1.5 * np.sqrt(1.0 - 3.0 / r)

    def analyze(self, r0: float) -> CircularOrbitInfo:
        """Full analysis of a circular orbit at radius r0."""
        if r0 <= self.PHOTON_SPHERE:
            raise ValueError(
                f"r0={r0} <= photon sphere r=3. No timelike circular orbit exists."
            )
        E = self.E_circular(r0)
        L = self.L_circular(r0)
        omega = self.omega_circular(r0)
        T_phi = self.T_phi_coordinate(r0)
        T_tau = self.T_phi_proper(r0)
        stable = self.is_stable(r0)
        isco = abs(r0 - self.ISCO_RADIUS) < 1e-6
        f = 1.0 - 2.0 / r0
        # Local circular velocity: v² = (r dΩ)² / (grr/gtt) — for reference
        v_circ = np.sqrt(1.0 / (r0 - 3.0)) if r0 > 3.0 else float("nan")

        return CircularOrbitInfo(
            r0=r0, E=E, L=L,
            is_stable=stable, is_isco=isco,
            omega=omega, T_phi=T_phi, T_tau=T_tau,
            v_circ=v_circ,
        )

    # ------------------------------------------------------------------
    # Scan circular orbit family
    # ------------------------------------------------------------------
    def isco_scan(
        self, r_range: tuple[float, float] = (3.01, 50.0), n: int = 500
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (r, E(r), L(r)) arrays for the circular orbit locus."""
        r_arr = np.linspace(r_range[0], r_range[1], n)
        E_arr = np.array([self.E_circular(r) for r in r_arr])
        L_arr = np.array([self.L_circular(r) for r in r_arr])
        return r_arr, E_arr, L_arr

    # ------------------------------------------------------------------
    # Convert between (p, e) and (r_peri, r_apo)
    # ------------------------------------------------------------------
    @staticmethod
    def pe_to_turning_points(p: float, e: float) -> tuple[float, float]:
        """
        Semi-latus rectum p, eccentricity e  →  (r_peri, r_apo).
        r_peri = p/(1+e),  r_apo = p/(1-e).
        """
        if e < 0 or e >= 1:
            raise ValueError(f"Eccentricity must be in [0,1); got e={e}")
        r_peri = p / (1.0 + e)
        r_apo  = p / (1.0 - e)
        return r_peri, r_apo

    @staticmethod
    def turning_points_to_EL(r_peri: float, r_apo: float) -> tuple[float, float]:
        """
        From turning points solve E, L analytically.

        At turning points:  E² = V_eff(r_i) = (1-2/r_i)(1+L²/r_i²)
        Subtracting the two equations and solving for L then E.
        """
        r1, r2 = r_peri, r_apo
        if r1 >= r2:
            raise ValueError("r_peri must be < r_apo")
        if r1 <= 2.0:
            raise ValueError(f"r_peri={r1} is inside or at the horizon r=2")

        # V_eff(r) = (1-2/r)(1+L²/r²) = A + B·L²  where A = 1-2/r, B = (1-2/r)/r²
        A1 = 1.0 - 2.0 / r1
        B1 = A1 / r1**2
        A2 = 1.0 - 2.0 / r2
        B2 = A2 / r2**2

        # E² = A1 + B1·L²  and  E² = A2 + B2·L²
        # → (B1 - B2)·L² = A2 - A1
        denom = B1 - B2
        if abs(denom) < 1e-14:
            raise ValueError("Degenerate system: turning points too close or circular orbit.")
        L2 = (A2 - A1) / denom
        if L2 < 0:
            raise ValueError(f"L² < 0 for r_peri={r1}, r_apo={r2}: no bound orbit.")
        L = np.sqrt(L2)
        E2 = A1 + B1 * L2
        if E2 < 0:
            raise ValueError(f"E² < 0 for r_peri={r1}, r_apo={r2}.")
        E = np.sqrt(E2)
        return E, L
