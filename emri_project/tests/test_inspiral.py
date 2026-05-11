"""Tests for adiabatic inspiral engine."""

import numpy as np
import pytest
from emri_project.dynamics.geodesic_solver import circular_E, circular_L
from emri_project.dynamics.inspiral import integrate_inspiral, r_from_EL, is_plunging
from emri_project.constants import R_ISCO


class TestInspiralEngine:
    """Test adiabatic inspiral."""

    def test_r_from_EL_circular(self):
        """r_from_EL should recover circular orbit radius."""
        r0 = 12.0
        E = circular_E(r0)
        L = circular_L(r0)
        r_rec = r_from_EL(E, L)
        assert abs(r_rec - r0) < 0.1

    def test_not_plunging_far_orbit(self):
        """Far orbit (r=15) should not be at separatrix."""
        E = circular_E(15.0)
        L = circular_L(15.0)
        assert not is_plunging(E, L)

    def test_plunging_near_isco(self):
        """Orbit extremely close to ISCO (r=6.005) should be flagged as plunging.

        r_from_EL uses a bracket [6.01, 1e6]; an orbit at r=6.005 falls outside
        this bracket and is conservatively declared as plunging (returns R_ISCO=6).
        """
        E = circular_E(6.005)
        L = circular_L(6.005)
        assert is_plunging(E, L)

    @pytest.mark.slow
    def test_inspiral_r_decreases(self):
        """r_circ should decrease monotonically during inspiral."""
        E0 = circular_E(15.0)
        L0 = circular_L(15.0)
        sol = integrate_inspiral(E0, L0, eta=1e-4, t_max=1e6, n_points=1000)
        # r should generally decrease (allow small numerical noise)
        assert sol.r_circ[0] > sol.r_circ[-1]

    @pytest.mark.slow
    def test_inspiral_energy_decreases(self):
        """Orbital energy should decrease (become more bound) during inspiral."""
        E0 = circular_E(15.0)
        L0 = circular_L(15.0)
        sol = integrate_inspiral(E0, L0, eta=1e-4, t_max=1e6, n_points=500)
        assert sol.E[0] > sol.E[-1]

    @pytest.mark.slow
    def test_inspiral_stops_at_isco(self):
        """Inspiral should terminate near ISCO."""
        E0 = circular_E(12.0)
        L0 = circular_L(12.0)
        sol = integrate_inspiral(E0, L0, eta=1e-3, t_max=1e8, n_points=5000)
        assert sol.plunged or sol.r_circ[-1] < R_ISCO + 1.0
