"""Comprehensive tests for the EOB integration layer (Step 5).

Covers:
- EOBConfig / EOBState dataclasses
- SchwarzschildPotentials and ResummedPotentials
- EOBHamiltonian (heff, hreal, rhs)
- EOBRadiationReaction (azimuthal force sign)
- HorizonFluxModel (positive output, magnitude check)
- TrajectoryAdapter (key presence, round-trip)
- ModelComparisonService (trajectory comparison)
- integrate_eob (end-to-end smoke test)
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from emri_lab.eob import (
    EOBConfig,
    EOBState,
    SchwarzschildPotentials,
    ResummedPotentials,
    EOBHamiltonian,
    EOBRadiationReaction,
    HorizonFluxModel,
    TrajectoryAdapter,
    ModelComparisonService,
    integrate_eob,
)
from emri_lab.domain.models import InspiralResult


# ---------------------------------------------------------------------------
# Helper: build a minimal InspiralResult for adapter tests
# ---------------------------------------------------------------------------

def _make_inspiral_result(n: int = 10) -> InspiralResult:
    t = np.linspace(0.0, 1000.0, n)
    r = np.linspace(12.0, 8.0, n)
    return InspiralResult(
        t=t,
        p_arr=r,
        e_arr=np.zeros(n),
        E_arr=np.ones(n) * 0.95,
        L_arr=np.ones(n) * 3.5,
        r_circ=r,
        plunged=False,
        message="test",
    )


# ===========================================================================
# EOBConfig
# ===========================================================================

class TestEOBConfig:
    def test_frozen_immutable(self):
        """EOBConfig must be frozen (FrozenInstanceError on mutation)."""
        cfg = EOBConfig()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
            cfg.nu = 0.25  # type: ignore[misc]

    def test_defaults(self):
        cfg = EOBConfig()
        assert cfg.conservative_model == "schwarzschild"
        assert cfg.flux_model == "baseline_pn"
        assert cfg.nu == 0.0
        assert cfg.eta == pytest.approx(1e-5)

    def test_custom_values(self):
        cfg = EOBConfig(conservative_model="3pn", nu=0.1, eta=1e-4)
        assert cfg.conservative_model == "3pn"
        assert cfg.nu == pytest.approx(0.1)


# ===========================================================================
# EOBState
# ===========================================================================

class TestEOBState:
    def _make_state(self, n: int = 5) -> EOBState:
        t = np.linspace(0.0, 100.0, n)
        r = np.linspace(10.0, 8.0, n)
        return EOBState(
            t=t, r=r,
            pr=np.zeros(n), phi=np.linspace(0.0, 1.0, n),
            pphi=np.ones(n) * 3.5,
            heff=np.ones(n) * 0.96,
            hreal=np.ones(n) * 0.96,
        )

    def test_r_circ_property(self):
        s = self._make_state()
        np.testing.assert_array_equal(s.r_circ, s.r)

    def test_Omega_phi_property(self):
        s = self._make_state()
        expected = s.pphi / np.maximum(s.r ** 2, 1e-10)
        np.testing.assert_allclose(s.Omega_phi, expected)

    def test_Omega_phi_positive(self):
        s = self._make_state()
        assert np.all(s.Omega_phi > 0.0)


# ===========================================================================
# SchwarzschildPotentials
# ===========================================================================

class TestSchwarzschildPotentials:
    def setup_method(self):
        self.pot = SchwarzschildPotentials()
        self.params = {"nu": 0.0, "eta": 1e-5}

    def test_A_at_r10(self):
        """A(u=1/10) = 1 - 2/10 = 0.8."""
        u = 1.0 / 10.0
        assert self.pot.A(u, self.params) == pytest.approx(0.8, rel=1e-12)

    def test_A_at_r6(self):
        """A(u=1/6) = 1 - 1/3 ≈ 2/3."""
        u = 1.0 / 6.0
        assert self.pot.A(u, self.params) == pytest.approx(1.0 - 2.0 / 6.0, rel=1e-12)

    def test_A_near_horizon(self):
        """A approaches zero near r=2 but is clamped to ≥ 1e-10."""
        u = 1.0 / 2.01
        val = self.pot.A(u, self.params)
        assert val > 0.0
        assert val < 0.02

    def test_A_horizon_clamped(self):
        """A at exactly r=2 (u=0.5) should be clamped to 1e-10, not negative."""
        u = 0.5
        assert self.pot.A(u, self.params) >= 1e-10

    def test_dA_du_constant(self):
        """dA/du = -2 everywhere (Schwarzschild)."""
        for u in [0.05, 0.1, 0.15]:
            assert self.pot.dA_du(u, self.params) == pytest.approx(-2.0)

    def test_B_is_reciprocal_of_A(self):
        u = 1.0 / 10.0
        A = self.pot.A(u, self.params)
        B = self.pot.B(u, self.params)
        assert A * B == pytest.approx(1.0, rel=1e-10)

    def test_D_equals_one(self):
        """D = A*B = 1 in Schwarzschild (test-mass limit)."""
        for u in [0.05, 0.08, 0.12]:
            assert self.pot.D(u, self.params) == pytest.approx(1.0, rel=1e-9)

    def test_Q_zero(self):
        """Q is identically 0 in the Schwarzschild limit."""
        assert self.pot.Q(0.1, 0.5, self.params) == 0.0

    def test_metadata_name(self):
        meta = self.pot.metadata()
        assert meta["name"] == "schwarzschild"


# ===========================================================================
# ResummedPotentials
# ===========================================================================

class TestResummedPotentials:
    def setup_method(self):
        self.pot = ResummedPotentials()

    def test_nu_zero_reduces_to_schwarzschild_A(self):
        """For ν=0 the 3PN A should equal the Schwarzschild A."""
        params = {"nu": 0.0}
        u = 0.1
        assert self.pot.A(u, params) == pytest.approx(1.0 - 2.0 * u, rel=1e-12)

    def test_A_correction_with_nu(self):
        """A(u, ν>0) differs from Schwarzschild A."""
        params_nu = {"nu": 0.1}
        params_0 = {"nu": 0.0}
        u = 0.1
        A_nu = self.pot.A(u, params_nu)
        A_0 = self.pot.A(u, params_0)
        assert A_nu != pytest.approx(A_0)

    def test_Q_zero_for_nu_zero(self):
        params = {"nu": 0.0}
        assert self.pot.Q(0.1, 0.5, params) == pytest.approx(0.0, abs=1e-14)

    def test_Q_positive_for_nonzero_nu(self):
        params = {"nu": 0.1}
        assert self.pot.Q(0.1, 0.5, params) > 0.0

    def test_metadata(self):
        meta = self.pot.metadata()
        assert meta["name"] == "resummed_3pn"


# ===========================================================================
# EOBHamiltonian
# ===========================================================================

class TestEOBHamiltonian:
    def setup_method(self):
        self.ham = EOBHamiltonian()
        self.cfg = EOBConfig()

    def test_heff_positive(self):
        """H_eff > 0 for any valid state."""
        state = np.array([10.0, 0.0, 0.0, 3.5])
        assert self.ham.heff(state, self.cfg) > 0.0

    def test_heff_circular_r10(self):
        """H_eff for circular orbit at r=10 should match Schwarzschild E_circ.

        E_circ(r) = (r-2)/sqrt(r*(r-3))  — for the 'free particle', with p_φ = L_circ.
        """
        r = 10.0
        # Circular orbit initial conditions
        pphi = r / np.sqrt(r - 3.0)
        state = np.array([r, 0.0, 0.0, pphi])
        heff = self.ham.heff(state, self.cfg)
        E_circ = (r - 2.0) / np.sqrt(r * (r - 3.0))
        # H_eff for circular orbit equals E_circ in Schwarzschild
        assert heff == pytest.approx(E_circ, rel=1e-8)

    def test_heff_larger_for_radial_motion(self):
        """Adding p_r > 0 increases H_eff (kinetic energy)."""
        r = 10.0
        pphi = r / np.sqrt(r - 3.0)
        state_circ = np.array([r, 0.0, 0.0, pphi])
        state_rad = np.array([r, 0.5, 0.0, pphi])
        assert self.ham.heff(state_rad, self.cfg) > self.ham.heff(state_circ, self.cfg)

    def test_hreal_equals_heff_for_nu_zero(self):
        """For ν=0 the real Hamiltonian must equal H_eff (geodesic limit)."""
        state = np.array([10.0, 0.0, 0.0, 3.5])
        cfg = EOBConfig(nu=0.0)
        assert self.ham.hreal(state, cfg) == pytest.approx(
            self.ham.heff(state, cfg), rel=1e-12
        )

    def test_hreal_positive(self):
        state = np.array([10.0, 0.0, 0.0, 3.5])
        assert self.ham.hreal(state, self.cfg) > 0.0

    def test_rhs_shape(self):
        """rhs should return a 4-element array."""
        state = np.array([10.0, 0.0, 0.0, 3.5])
        deriv = self.ham.rhs(0.0, state, self.cfg)
        assert deriv.shape == (4,)

    def test_rhs_dphi_positive(self):
        """dφ/dt should be positive for prograde orbit (p_φ > 0)."""
        state = np.array([10.0, 0.0, 0.0, 3.5])
        deriv = self.ham.rhs(0.0, state, self.cfg)
        assert deriv[2] > 0.0  # dφ/dt > 0

    def test_rhs_dphi_matches_Omega(self):
        """dφ/dt = A·p_φ·u²/H_eff.

        For a circular orbit at r=12 in Schwarzschild:
            A(u) = 1 - 2/12 = 5/6
            u = 1/12
            p_φ = L_circ(12) = 12/√9 = 4
            H_eff = E_circ(12) = 10/√(12·9) = 10/√108
        We verify against the analytic expression rather than the crude p_φ/r²
        approximation (which differs by the factor A/H_eff ≈ 0.87).
        """
        r = 12.0
        pphi = r / np.sqrt(r - 3.0)  # = 4.0
        u = 1.0 / r
        state = np.array([r, 0.0, 0.0, pphi])
        deriv = self.ham.rhs(0.0, state, self.cfg)
        dphi_dt = deriv[2]

        pot = SchwarzschildPotentials()
        params = {"nu": 0.0, "eta": 1e-5}
        A = pot.A(u, params)
        H = self.ham.heff(state, self.cfg)
        expected = A * pphi * u**2 / H

        assert dphi_dt == pytest.approx(expected, rel=1e-8)


# ===========================================================================
# EOBRadiationReaction
# ===========================================================================

class TestEOBRadiationReaction:
    def setup_method(self):
        self.rr = EOBRadiationReaction()
        self.cfg = EOBConfig()

    def test_azimuthal_force_negative(self):
        """dp_φ/dt < 0 during inspiral (angular momentum is lost)."""
        orbit_state = {"r": 10.0, "p": 10.0, "e": 0.0, "eta": 1e-5}
        F_phi = self.rr.azimuthal_force(orbit_state, {}, self.cfg)
        assert F_phi < 0.0

    def test_azimuthal_force_stronger_at_smaller_r(self):
        """The radiation reaction is stronger (more negative) at smaller r."""
        s_large = {"r": 15.0, "p": 15.0, "e": 0.0}
        s_small = {"r": 8.0,  "p": 8.0,  "e": 0.0}
        F_large = self.rr.azimuthal_force(s_large, {}, self.cfg)
        F_small = self.rr.azimuthal_force(s_small, {}, self.cfg)
        assert F_small < F_large  # more negative = stronger reaction

    def test_radial_force_zero(self):
        """Radial force is zero in the quasi-circular approximation."""
        orbit_state = {"r": 10.0, "p": 10.0, "e": 0.0}
        F_r = self.rr.radial_force(orbit_state, {}, self.cfg)
        assert F_r == pytest.approx(0.0, abs=1e-15)

    def test_horizon_flux_adds_when_enabled(self):
        """Including horizon flux makes dp_φ/dt more negative."""
        cfg_no_hor = EOBConfig(include_horizon_flux=False)
        cfg_with_hor = EOBConfig(
            flux_model="extended_test_mass",
            include_horizon_flux=True,
        )
        orbit_state = {"r": 8.0, "p": 8.0, "e": 0.0}
        F_no = self.rr.azimuthal_force(orbit_state, {}, cfg_no_hor)
        F_hor = self.rr.azimuthal_force(orbit_state, {}, cfg_with_hor)
        # Both negative; horizon contribution should make it more negative
        assert F_hor <= F_no


# ===========================================================================
# HorizonFluxModel
# ===========================================================================

class TestHorizonFluxModel:
    def setup_method(self):
        self.model = HorizonFluxModel()

    def test_compute_returns_positive(self):
        """dEdt and dLdt from the horizon must be positive (energy absorbed)."""
        result = self.model.compute({"r": 10.0})
        assert result["dEdt"] > 0.0
        assert result["dLdt"] > 0.0

    def test_compute_dEdt_formula(self):
        """dEdt = (8/5) r^{-9} for r=10."""
        r = 10.0
        expected = (8.0 / 5.0) * r ** (-9)
        result = self.model.compute({"r": r})
        assert result["dEdt"] == pytest.approx(expected, rel=1e-12)

    def test_compute_dLdt_formula(self):
        """dLdt = dEdt / Ω_φ = (8/5) r^{-15/2} for r=10."""
        r = 10.0
        Omega = r ** (-1.5)
        dEdt = (8.0 / 5.0) * r ** (-9)
        expected_dLdt = dEdt / Omega
        result = self.model.compute({"r": r})
        assert result["dLdt"] == pytest.approx(expected_dLdt, rel=1e-12)

    def test_compute_increases_near_horizon(self):
        """Flux is larger (stronger) at smaller radii."""
        r_large = self.model.compute({"r": 15.0})
        r_small = self.model.compute({"r": 8.0})
        assert r_small["dEdt"] > r_large["dEdt"]

    def test_is_negligible_at_large_r(self):
        """Horizon flux is negligible far from the ISCO."""
        assert self.model.is_negligible(20.0)

    def test_not_negligible_near_isco(self):
        """Horizon flux is NOT negligible very close to the ISCO."""
        assert not self.model.is_negligible(2.5)

    def test_fallback_to_p_key(self):
        """Orbit state using 'p' key instead of 'r' should still work."""
        result = self.model.compute({"p": 10.0})
        expected = (8.0 / 5.0) * 10.0 ** (-9)
        assert result["dEdt"] == pytest.approx(expected, rel=1e-12)


# ===========================================================================
# TrajectoryAdapter
# ===========================================================================

EXPECTED_TRAJ_KEYS = {"t", "r_circ", "p", "e", "E", "L", "Omega_phi", "source"}


class TestTrajectoryAdapter:
    def setup_method(self):
        self.adapter = TrajectoryAdapter()

    def test_from_adiabatic_keys(self):
        """from_adiabatic must return all required trajectory keys."""
        result = self.adapter.from_adiabatic(_make_inspiral_result())
        assert EXPECTED_TRAJ_KEYS.issubset(result.keys())

    def test_from_adiabatic_source_label(self):
        result = self.adapter.from_adiabatic(_make_inspiral_result())
        assert result["source"] == "adiabatic"

    def test_from_adiabatic_array_lengths(self):
        n = 15
        ir = _make_inspiral_result(n)
        result = self.adapter.from_adiabatic(ir)
        for key in ["t", "r_circ", "p", "e", "E", "L", "Omega_phi"]:
            assert len(result[key]) == n

    def test_from_eob_keys(self):
        """from_eob must return all required trajectory keys."""
        n = 8
        state = EOBState(
            t=np.linspace(0, 100, n),
            r=np.linspace(10, 8, n),
            pr=np.zeros(n),
            phi=np.linspace(0, 5, n),
            pphi=np.ones(n) * 3.4,
            heff=np.ones(n) * 0.96,
            hreal=np.ones(n) * 0.96,
        )
        result = self.adapter.from_eob(state)
        assert EXPECTED_TRAJ_KEYS.issubset(result.keys())

    def test_from_eob_source_label(self):
        n = 5
        state = EOBState(
            t=np.linspace(0, 50, n), r=np.ones(n) * 10.0,
            pr=np.zeros(n), phi=np.zeros(n),
            pphi=np.ones(n) * 3.5,
            heff=np.ones(n), hreal=np.ones(n),
        )
        result = self.adapter.from_eob(state)
        assert result["source"] == "eob"

    def test_from_eob_eccentricity_zero(self):
        """EOB quasi-circular: e must be all zeros."""
        n = 5
        state = EOBState(
            t=np.linspace(0, 50, n), r=np.ones(n) * 10.0,
            pr=np.zeros(n), phi=np.zeros(n),
            pphi=np.ones(n) * 3.5,
            heff=np.ones(n), hreal=np.ones(n),
        )
        result = self.adapter.from_eob(state)
        np.testing.assert_array_equal(result["e"], 0.0)

    def test_to_inspiral_result_roundtrip(self):
        """Round-trip: from_adiabatic → to_inspiral_result preserves arrays."""
        ir = _make_inspiral_result(10)
        traj = self.adapter.from_adiabatic(ir)
        ir2 = self.adapter.to_inspiral_result(traj)
        np.testing.assert_array_equal(ir2.t, ir.t)
        np.testing.assert_array_equal(ir2.p_arr, ir.p_arr)

    def test_to_inspiral_result_not_plunged(self):
        ir = _make_inspiral_result()
        traj = self.adapter.from_adiabatic(ir)
        ir2 = self.adapter.to_inspiral_result(traj)
        assert ir2.plunged is False


# ===========================================================================
# ModelComparisonService
# ===========================================================================

def _make_traj_dict(r_start: float, r_end: float, n: int = 50) -> dict:
    t = np.linspace(0.0, 1000.0, n)
    r = np.linspace(r_start, r_end, n)
    Omega = r ** (-1.5)
    return {"t": t, "r_circ": r, "Omega_phi": Omega}


class TestModelComparisonService:
    def setup_method(self):
        self.svc = ModelComparisonService()

    def test_compare_trajectories_keys(self):
        """compare_trajectories must return the expected result keys."""
        a = _make_traj_dict(12.0, 8.0)
        b = _make_traj_dict(12.0, 8.0)
        result = self.svc.compare_trajectories(a, b)
        for key in ("t_common", "r_diff", "r_rms_diff", "dephasing",
                    "max_dephasing", "final_dephasing"):
            assert key in result, f"Missing key: {key}"

    def test_identical_trajectories_zero_diff(self):
        """Two identical trajectories should give zero r_rms_diff."""
        traj = _make_traj_dict(12.0, 7.5)
        result = self.svc.compare_trajectories(traj, traj)
        assert result["r_rms_diff"] == pytest.approx(0.0, abs=1e-12)

    def test_different_trajectories_nonzero_diff(self):
        """Trajectories starting at different r0 should differ."""
        a = _make_traj_dict(12.0, 8.0)
        b = _make_traj_dict(12.5, 8.0)
        result = self.svc.compare_trajectories(a, b)
        assert result["r_rms_diff"] > 0.0

    def test_max_dephasing_non_negative(self):
        a = _make_traj_dict(12.0, 8.0)
        b = _make_traj_dict(11.0, 7.0)
        result = self.svc.compare_trajectories(a, b)
        assert result["max_dephasing"] >= 0.0

    def test_no_overlap_returns_error(self):
        """Non-overlapping time ranges should return an error key."""
        a = {"t": np.array([0.0, 1.0]), "r_circ": np.array([10.0, 9.0]),
             "Omega_phi": np.array([0.03, 0.04])}
        b = {"t": np.array([5.0, 10.0]), "r_circ": np.array([8.0, 7.0]),
             "Omega_phi": np.array([0.05, 0.06])}
        result = self.svc.compare_trajectories(a, b)
        assert "error" in result

    def test_compare_fluxes_keys(self):
        flux_a = {"dEdt": 1e-5, "dLdt": 3e-4}
        flux_b = {"dEdt": 2e-5, "dLdt": 4e-4}
        result = self.svc.compare_fluxes(flux_a, flux_b)
        for key in ("dEdt_a", "dEdt_b", "dEdt_rel_diff",
                    "dLdt_a", "dLdt_b", "dLdt_rel_diff"):
            assert key in result

    def test_compare_fluxes_identical_zero_diff(self):
        flux = {"dEdt": 1e-5, "dLdt": 3e-4}
        result = self.svc.compare_fluxes(flux, flux)
        assert result["dEdt_rel_diff"] == pytest.approx(0.0, abs=1e-14)
        assert result["dLdt_rel_diff"] == pytest.approx(0.0, abs=1e-14)


# ===========================================================================
# integrate_eob (end-to-end smoke test)
# ===========================================================================

class TestIntegrateEOB:
    def test_runs_without_error(self):
        """integrate_eob should complete without raising an exception."""
        result = integrate_eob(r0=12.0, t_max=1e5, n_points=100)
        assert isinstance(result, EOBState)

    def test_output_arrays_nonempty(self):
        result = integrate_eob(r0=12.0, t_max=1e5, n_points=100)
        assert len(result.t) > 0
        assert len(result.r) == len(result.t)
        assert len(result.pphi) == len(result.t)

    def test_initial_radius(self):
        """The first point of r should be close to r0."""
        r0 = 12.0
        result = integrate_eob(r0=r0, t_max=1e5, n_points=100)
        assert result.r[0] == pytest.approx(r0, rel=1e-6)

    def test_heff_positive_everywhere(self):
        """H_eff must be positive at all time steps."""
        result = integrate_eob(r0=12.0, t_max=1e5, n_points=100)
        assert np.all(result.heff > 0.0)

    def test_hreal_positive_everywhere(self):
        result = integrate_eob(r0=12.0, t_max=1e5, n_points=100)
        assert np.all(result.hreal > 0.0)

    def test_r_decreases_overall(self):
        """The orbital radius should shrink overall during the inspiral."""
        result = integrate_eob(r0=12.0, t_max=1e5, n_points=100)
        assert result.r[-1] < result.r[0]

    def test_phi_increases(self):
        """The azimuthal angle should increase monotonically."""
        result = integrate_eob(r0=12.0, t_max=1e5, n_points=100)
        assert result.phi[-1] > result.phi[0]

    def test_custom_pphi0(self):
        """Custom pphi0 is accepted without error."""
        result = integrate_eob(r0=12.0, pphi0=4.0, t_max=1e5, n_points=50)
        assert isinstance(result, EOBState)

    def test_schwarzschild_and_3pn_both_run(self):
        """Both conservative model choices must run to completion."""
        for model in ("schwarzschild", "3pn"):
            cfg = EOBConfig(conservative_model=model, nu=0.01 if model == "3pn" else 0.0)
            result = integrate_eob(r0=12.0, cfg=cfg, t_max=5e4, n_points=50)
            assert len(result.t) > 0

    def test_adapter_roundtrip_after_integration(self):
        """TrajectoryAdapter.from_eob works on the result of integrate_eob."""
        result = integrate_eob(r0=12.0, t_max=1e5, n_points=100)
        adapter = TrajectoryAdapter()
        traj = adapter.from_eob(result)
        assert EXPECTED_TRAJ_KEYS.issubset(traj.keys())
        np.testing.assert_array_equal(traj["e"], 0.0)
