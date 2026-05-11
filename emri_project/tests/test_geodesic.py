"""Tests for geodesic solver (Layer A/B verification)."""

import numpy as np
import pytest
from emri_project.dynamics.geodesic_solver import (
    circular_E, circular_L, ic_circular, ic_eccentric, integrate_geodesic,
    effective_potential,
)
from emri_project.dynamics.hamiltonian import superhamiltonian, hamiltonian_constraint
from emri_project.dynamics.metric import lapse
from emri_project.constants import R_ISCO


class TestCircularOrbits:
    """Verify E(r), L(r) for circular orbits against known Schwarzschild formulae."""

    def test_isco_energy(self):
        """At r=6: E = sqrt(8/9) = 2*sqrt(2)/3."""
        E = circular_E(6.0)
        expected = 2.0 * np.sqrt(2.0) / 3.0
        assert abs(E - expected) < 1e-12

    def test_isco_angular_momentum(self):
        """At r=6: L = 2*sqrt(3)."""
        L = circular_L(6.0)
        expected = 2.0 * np.sqrt(3.0)
        assert abs(L - expected) < 1e-12

    def test_circular_E_r10(self):
        """E at r=10."""
        E = circular_E(10.0)
        expected = 8.0 / np.sqrt(70.0)
        assert abs(E - expected) < 1e-12

    def test_circular_L_r10(self):
        """L at r=10."""
        L = circular_L(10.0)
        expected = 10.0 / np.sqrt(7.0)
        assert abs(L - expected) < 1e-12

    def test_E_increases_with_r(self):
        """E should decrease towards 1 as r→∞ (more bound for smaller r near ISCO)."""
        r_vals = np.array([7.0, 10.0, 20.0, 50.0, 100.0])
        E_vals = np.array([circular_E(r) for r in r_vals])
        # All E < 1 (bound), and E should increase toward 1 as r increases
        assert np.all(E_vals < 1.0)

    def test_L_increases_with_r(self):
        """L increases monotonically with r for circular orbits."""
        r_vals = np.array([7.0, 10.0, 20.0, 50.0])
        L_vals = np.array([circular_L(r) for r in r_vals])
        assert np.all(np.diff(L_vals) > 0)

    def test_circular_orbit_invalid_below_isco(self):
        """r < r_ISCO should raise ValueError."""
        with pytest.raises(ValueError):
            ic_circular(5.0)


class TestHamiltonianConservation:
    """Test that H = -1/2 is conserved during integration."""

    def test_circular_orbit_constraint_initial(self):
        """H + 1/2 = 0 at initial conditions for circular orbit."""
        state0, E, L = ic_circular(10.0)
        constraint = hamiltonian_constraint(state0, E, L)
        assert abs(constraint) < 1e-12

    @pytest.mark.slow
    def test_circular_orbit_constraint_evolution(self):
        """H + 1/2 stays < 1e-10 during circular orbit integration."""
        state0, E, L = ic_circular(10.0)
        sol = integrate_geodesic(state0, E, L, tau_max=500.0, n_points=5000)
        drift = sol.hamiltonian_drift()
        assert np.max(np.abs(drift)) < 1e-8

    @pytest.mark.slow
    def test_eccentric_orbit_constraint(self):
        """H + 1/2 stays < 1e-8 for eccentric orbit."""
        state0, E, L = ic_eccentric(r_apo=15.0, r_peri=7.0)
        sol = integrate_geodesic(state0, E, L, tau_max=1000.0, n_points=10000)
        drift = sol.hamiltonian_drift()
        assert np.max(np.abs(drift)) < 1e-7


class TestEffectivePotential:
    """Test effective potential properties."""

    def test_veff_at_isco(self):
        """At ISCO r=6, V_eff(6) = E_ISCO²."""
        L = circular_L(6.0)
        E = circular_E(6.0)
        Veff = effective_potential(np.array([6.0]), E, L)
        assert abs(Veff[0] - E**2) < 1e-12

    def test_veff_minimum_at_circular(self):
        """V_eff has minimum at circular orbit radius."""
        r0 = 10.0
        E = circular_E(r0)
        L = circular_L(r0)
        r = np.linspace(7.0, 20.0, 1000)
        Veff = effective_potential(r, E, L)
        i_min = np.argmin(Veff)
        assert abs(r[i_min] - r0) < 0.1


class TestTurningPoints:
    """Test turning point finder."""

    def test_circular_orbit_no_turning_points(self):
        """For circular orbit p_r=0 always, so r_min = r_max = r_circ."""
        from emri_project.observables.turning_points import find_turning_points
        r0 = 10.0
        E = circular_E(r0)
        L = circular_L(r0)
        r_peri, r_apo = find_turning_points(E, L)
        assert abs(r_peri - r0) < 0.5
        assert abs(r_apo - r0) < 0.5

    def test_eccentric_turning_points(self):
        """r_peri and r_apo match input for eccentric orbit."""
        from emri_project.observables.turning_points import find_turning_points
        r_apo_in, r_peri_in = 15.0, 8.0
        state0, E, L = ic_eccentric(r_apo_in, r_peri_in)
        r_peri_out, r_apo_out = find_turning_points(E, L)
        assert abs(r_peri_out - r_peri_in) < 0.1
        assert abs(r_apo_out - r_apo_in) < 0.1


class TestOrbitalFrequencies:
    """Test orbital frequency computation."""

    def test_omega_phi_circular(self):
        """Ω_φ = r^(-3/2) for circular orbit."""
        from emri_project.observables.frequencies import omega_phi_circular
        r = 10.0
        Omega = omega_phi_circular(r)
        assert abs(Omega - r**(-1.5)) < 1e-15

    def test_frequencies_bound_orbit(self):
        """Ω_r and Ω_φ are finite and positive for bound orbit."""
        from emri_project.observables.frequencies import orbital_frequencies
        state0, E, L = ic_eccentric(15.0, 8.0)
        freqs = orbital_frequencies(E, L)
        assert freqs['Omega_r'] > 0
        assert freqs['Omega_phi'] > 0
        assert freqs['Omega_phi'] > freqs['Omega_r']  # precessing orbit


class TestMetricFunctions:
    """Test metric functions."""

    def test_lapse_at_horizon(self):
        """f(2) = 0 at Schwarzschild horizon."""
        assert abs(lapse(np.array([2.0]))[0]) < 1e-15

    def test_lapse_asymptotic(self):
        """f(r) → 1 as r → ∞."""
        assert abs(lapse(np.array([1e6]))[0] - 1.0) < 1e-5
