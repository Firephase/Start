"""Tests for radiation flux models."""

import numpy as np
import pytest
from emri_project.fluxes.infinity_flux import (
    flux_E_quadrupole, flux_E_PN_circular, flux_L_PN_circular
)
from emri_project.fluxes.horizon_flux import (
    flux_E_horizon_circular, horizon_flux_ratio
)


class TestInfinityFlux:
    """Test energy flux to infinity."""

    def test_quadrupole_positive(self):
        """Flux must be positive."""
        for r in [7, 10, 20, 50]:
            assert flux_E_quadrupole(float(r)) > 0

    def test_quadrupole_decreases_with_r(self):
        """Flux increases toward smaller r (stronger gravity)."""
        r_vals = [10.0, 20.0, 50.0]
        F_vals = [flux_E_quadrupole(r) for r in r_vals]
        assert F_vals[0] > F_vals[1] > F_vals[2]

    def test_quadrupole_scaling(self):
        """F_quad ∝ r^(-5)."""
        r1, r2 = 10.0, 20.0
        F1 = flux_E_quadrupole(r1)
        F2 = flux_E_quadrupole(r2)
        ratio = F1 / F2
        expected = (r2 / r1)**5
        assert abs(ratio - expected) < 1e-10

    def test_PN_positive(self):
        for r in [8.0, 12.0, 30.0]:
            assert flux_E_PN_circular(r) > 0

    def test_PN_matches_quadrupole_at_large_r(self):
        """PN correction small at large r: F_PN ≈ F_quad."""
        r = 1000.0
        F_PN = flux_E_PN_circular(r, order=0)
        F_quad = flux_E_quadrupole(r)
        assert abs(F_PN - F_quad) / F_quad < 1e-10

    def test_EL_flux_ratio(self):
        """dL/dt / (dE/dt) = 1/Ω_phi for circular orbit."""
        r = 10.0
        F_E = flux_E_PN_circular(r)
        F_L = flux_L_PN_circular(r)
        Omega = r**(-1.5)
        ratio = F_L / F_E
        assert abs(ratio - 1.0 / Omega) < 1e-10


class TestHorizonFlux:
    """Test horizon flux properties."""

    def test_horizon_flux_positive(self):
        for r in [7.0, 10.0, 30.0]:
            assert flux_E_horizon_circular(r) > 0

    def test_horizon_suppressed_vs_infinity(self):
        """Horizon flux < infinity flux by large factor."""
        for r in [10.0, 20.0]:
            ratio = horizon_flux_ratio(r)
            assert ratio < 0.1

    def test_horizon_flux_scaling(self):
        """Horizon flux ∝ r^(-9)."""
        r1, r2 = 10.0, 20.0
        F1 = flux_E_horizon_circular(r1)
        F2 = flux_E_horizon_circular(r2)
        ratio = F1 / F2
        expected = (r2 / r1)**9
        assert abs(ratio - expected) < 1e-9

    def test_horizon_ratio_increases_near_isco(self):
        """Horizon flux fraction grows as orbit approaches ISCO."""
        ratio_far = horizon_flux_ratio(30.0)
        ratio_near = horizon_flux_ratio(7.0)
        assert ratio_near > ratio_far
