"""Thin solver wrappers for geodesic and adiabatic integrations."""

from __future__ import annotations

from emri_lab.domain.models import InspiralResult, OrbitParams, PhysicsConfig
from emri_lab.physics.adiabatic import integrate_adiabatic_pe
from emri_lab.physics.orbit_parametrization import pe_to_EL


class GeodesicSolver:
    """Compute conserved quantities for a geodesic orbit."""

    def solve(self, orbit: OrbitParams, config: PhysicsConfig) -> dict:
        """Return E, L, r_peri, r_apo for the given orbit."""
        E, L = pe_to_EL(orbit.p, orbit.e)
        return {
            "E": E,
            "L": L,
            "r_peri": orbit.r_peri,
            "r_apo": orbit.r_apo,
        }


class InspiralSolver:
    """Integrate the adiabatic inspiral in (p, e) space."""

    def integrate(
        self,
        orbit: OrbitParams,
        config: PhysicsConfig,
        t_max: float = 1e7,
        n_points: int = 5000,
    ) -> InspiralResult:
        """Run adiabatic inspiral and return InspiralResult."""
        return integrate_adiabatic_pe(orbit, config, t_max=t_max, n_points=n_points)
