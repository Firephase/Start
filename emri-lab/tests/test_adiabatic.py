"""Tests for the adiabatic inspiral integration."""

import pytest
import numpy as np
from emri_lab.domain.models import OrbitParams, PhysicsConfig
from emri_lab.physics.adiabatic import integrate_adiabatic_pe, dpde_rates
from emri_lab.physics.orbit_parametrization import pe_to_EL


class TestDpdtRates:
    def test_dpdt_negative(self):
        """During inspiral p should decrease (dpdt < 0)."""
        p, e = 12.0, 0.0
        E, L = pe_to_EL(p, e)
        from emri_lab.physics.fluxes import BaselinePNFlux
        flux = BaselinePNFlux()
        dEdt = 1e-5 * flux.flux_E(p, e)
        dLdt = 1e-5 * flux.flux_L(p, e)
        dpdt, dedt = dpde_rates(p, e, dEdt, dLdt)
        assert dpdt < 0


@pytest.mark.slow
class TestInspiralIntegration:
    def test_p_decreases(self):
        orbit = OrbitParams(p=12.0, e=0.0)
        config = PhysicsConfig(eta=1e-4)
        result = integrate_adiabatic_pe(orbit, config, t_max=1e6, n_points=500)
        assert result.p_arr[0] > result.p_arr[-1]

    def test_energy_decreases(self):
        orbit = OrbitParams(p=12.0, e=0.0)
        config = PhysicsConfig(eta=1e-4)
        result = integrate_adiabatic_pe(orbit, config, t_max=1e6, n_points=500)
        assert result.E_arr[0] > result.E_arr[-1]

    def test_stops_near_separatrix(self):
        orbit = OrbitParams(p=8.0, e=0.0)
        config = PhysicsConfig(eta=1e-3)
        result = integrate_adiabatic_pe(orbit, config, t_max=1e8, n_points=2000)
        assert result.plunged or result.p_arr[-1] < 7.0

    def test_eccentric_inspiral(self):
        orbit = OrbitParams(p=10.0, e=0.3)
        config = PhysicsConfig(eta=1e-4)
        result = integrate_adiabatic_pe(orbit, config, t_max=1e6, n_points=500)
        assert result.p_arr[0] > result.p_arr[-1]
        assert np.all(result.e_arr >= 0)
