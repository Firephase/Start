"""Tests for the domain layer."""

import pytest
from emri_lab.domain.enums import OrbitType, AppState, FluxModelId
from emri_lab.domain.models import OrbitParams, PhysicsConfig
from emri_lab.domain.states import UISessionState


class TestOrbitParams:
    def test_r_peri_apo(self):
        o = OrbitParams(p=10.0, e=0.5)
        assert abs(o.r_peri - 10.0 / 1.5) < 1e-10
        assert abs(o.r_apo - 10.0 / 0.5) < 1e-10

    def test_circular(self):
        o = OrbitParams(p=12.0, e=0.0)
        assert o.is_circular

    def test_not_circular(self):
        o = OrbitParams(p=12.0, e=0.3)
        assert not o.is_circular

    def test_invalid_p(self):
        with pytest.raises(ValueError):
            OrbitParams(p=-1.0, e=0.0)

    def test_invalid_e_negative(self):
        with pytest.raises(ValueError):
            OrbitParams(p=10.0, e=-0.1)

    def test_invalid_e_unity(self):
        with pytest.raises(ValueError):
            OrbitParams(p=10.0, e=1.0)


class TestPhysicsConfig:
    def test_defaults(self):
        cfg = PhysicsConfig()
        assert cfg.eta == 1e-5
        assert cfg.flux_model == FluxModelId.BASELINE_PN
        assert not cfg.use_horizon_flux

    def test_invalid_eta(self):
        with pytest.raises(ValueError):
            PhysicsConfig(eta=0.0)


class TestUISessionState:
    def test_initial_state(self):
        s = UISessionState()
        assert s.app_state == AppState.IDLE

    def test_transition(self):
        s = UISessionState()
        s.transition(AppState.CONFIGURING)
        s.transition(AppState.RUNNING_INSPIRAL)
        assert s.app_state == AppState.RUNNING_INSPIRAL

    def test_illegal_transition_raises(self):
        s = UISessionState()
        with pytest.raises(ValueError):
            s.transition(AppState.RUNNING_INSPIRAL)  # IDLE → RUNNING_INSPIRAL is illegal

    def test_reset(self):
        s = UISessionState()
        s.transition(AppState.CONFIGURING)
        s.transition(AppState.RUNNING_INSPIRAL)
        s.transition(AppState.VIEWING_RESULTS)
        s.reset()
        assert s.app_state == AppState.IDLE
        assert s.orbit is None
        assert s.inspiral_result is None
