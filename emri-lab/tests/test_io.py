"""Tests for the I/O layer."""

import pytest
import tempfile
from pathlib import Path
from emri_lab.io.config_loader import load_config, orbit_from_config, physics_from_config
from emri_lab.domain.enums import FluxModelId


class TestConfigLoader:
    def test_load_default_step2(self):
        path = Path(__file__).parent.parent / "configs" / "default_step2.yaml"
        cfg = load_config(path)
        orbit = orbit_from_config(cfg)
        physics = physics_from_config(cfg)
        assert orbit.p == 12.0
        assert orbit.e == 0.0
        assert physics.flux_model == FluxModelId.BASELINE_PN
        assert not physics.use_horizon_flux

    def test_load_default_step3(self):
        path = Path(__file__).parent.parent / "configs" / "default_step3.yaml"
        cfg = load_config(path)
        orbit = orbit_from_config(cfg)
        physics = physics_from_config(cfg)
        assert orbit.e == 0.3
        assert physics.flux_model == FluxModelId.EXTENDED_TEST_MASS
        assert physics.use_horizon_flux

    def test_load_demo_eccentric(self):
        path = Path(__file__).parent.parent / "configs" / "demo_eccentric.yaml"
        cfg = load_config(path)
        orbit = orbit_from_config(cfg)
        assert orbit.p == 10.0
        assert orbit.e == 0.5

    def test_t_max_loaded(self):
        path = Path(__file__).parent.parent / "configs" / "default_step2.yaml"
        cfg = load_config(path)
        assert cfg.t_max == 1e7
        assert cfg.n_points == 5000
