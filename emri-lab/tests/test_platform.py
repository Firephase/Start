"""Tests for the research platform layer (Step 6)."""
import pytest
import tempfile
import json
from pathlib import Path
import numpy as np

from emri_lab.platform.registry import ExperimentRegistry
from emri_lab.platform.batch import BatchExperimentManager, SimulationConfig
from emri_lab.platform.dataset import DatasetBuilder
from emri_lab.platform.detector import DetectorProjectionAdapter
from emri_lab.platform.bundle import save_run_bundle, load_run_bundle, zip_bundle, RunBundle
from emri_lab.domain.models import OrbitParams, PhysicsConfig


class TestExperimentRegistry:
    def test_register_and_list(self, tmp_path):
        reg = ExperimentRegistry(registry_path=tmp_path / "registry.json")
        run_id = reg.register_run({"p0": 12.0, "e0": 0.0, "eta": 1e-5})
        runs = reg.list_runs()
        assert len(runs) == 1
        assert runs[0]["p0"] == 12.0

    def test_filter(self, tmp_path):
        reg = ExperimentRegistry(registry_path=tmp_path / "registry.json")
        reg.register_run({"p0": 12.0, "model": "A"})
        reg.register_run({"p0": 10.0, "model": "B"})
        filtered = reg.list_runs({"model": "A"})
        assert len(filtered) == 1
        assert filtered[0]["p0"] == 12.0

    def test_compare_runs(self, tmp_path):
        reg = ExperimentRegistry(registry_path=tmp_path / "registry.json")
        rid1 = reg.register_run({"foo": 1})
        rid2 = reg.register_run({"foo": 2})
        comp = reg.compare_runs([rid1, rid2, "nonexistent"])
        assert len(comp["found"]) == 2
        assert len(comp["missing"]) == 1

    def test_delete_run(self, tmp_path):
        reg = ExperimentRegistry(registry_path=tmp_path / "registry.json")
        rid = reg.register_run({"foo": 42})
        assert reg.delete_run(rid)
        assert len(reg.list_runs()) == 0


class TestBatchManager:
    def test_parameter_sweep_count(self, tmp_path):
        """Sweep over 2 p values x 2 eta values = 4 configs."""
        base = SimulationConfig(
            orbit=OrbitParams(p=12.0, e=0.0),
            physics=PhysicsConfig(eta=1e-5),
            t_max=100.0,
            n_points=10,
        )
        sweep = {"p": [10.0, 12.0], "eta": [1e-5, 1e-4]}
        reg = ExperimentRegistry(registry_path=tmp_path / "registry.json")
        mgr = BatchExperimentManager(registry=reg, output_dir=tmp_path / "runs")
        run_ids = mgr.run_parameter_sweep(base, sweep)
        assert len(run_ids) == 4

    @pytest.mark.slow
    def test_run_grid(self, tmp_path):
        """Run 3 simulations in a grid."""
        configs = [
            SimulationConfig(
                orbit=OrbitParams(p=p, e=0.0),
                physics=PhysicsConfig(eta=1e-3),
                t_max=1000.0,
                n_points=50,
            )
            for p in [10.0, 12.0, 14.0]
        ]
        reg = ExperimentRegistry(registry_path=tmp_path / "registry.json")
        mgr = BatchExperimentManager(registry=reg, output_dir=tmp_path / "runs")
        run_ids = mgr.run_grid(configs)
        assert len(run_ids) == 3
        assert len(reg.list_runs()) == 3


class TestRunBundle:
    def test_save_load_bundle(self, tmp_path):
        metadata = {"run_id": "test01", "p0": 12.0}
        config = {"orbit": {"p": 12.0, "e": 0.0}, "physics": {"eta": 1e-5}}
        trajectory = {"t": [0.0, 1.0, 2.0], "p": [12.0, 11.9, 11.8]}

        bundle = save_run_bundle(
            run_id="test01",
            metadata=metadata,
            config=config,
            trajectory=trajectory,
            base_dir=tmp_path,
        )
        assert bundle.metadata_path.exists()
        assert bundle.config_path.exists()
        assert bundle.trajectory_path.exists()

        loaded = load_run_bundle(tmp_path / "test01")
        assert loaded["metadata"]["p0"] == 12.0
        assert "t" in loaded["trajectory"]

    def test_zip_bundle(self, tmp_path):
        save_run_bundle("run99", {"x": 1}, {"y": 2}, {"t": [0]}, tmp_path)
        zip_path = zip_bundle(tmp_path / "run99")
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"


class TestDetectorAdapter:
    def test_project_returns_strain(self):
        from emri_lab.waveform.result import WaveformResult
        from emri_lab.waveform.mode_manager import HarmonicMode
        t = np.linspace(0, 100, 200)
        h_plus = np.sin(t)
        h_cross = np.cos(t)
        wf = WaveformResult(
            time=t, h_plus=h_plus, h_cross=h_cross,
            phase=t, amplitude_envelope=np.ones_like(t),
            selected_modes=[HarmonicMode(0, 2)],
        )
        adapter = DetectorProjectionAdapter()
        result = adapter.project(wf, {"detector": "LISA", "F_plus": 1.0, "F_cross": 0.5})
        assert "h_observed" in result
        assert len(result["h_observed"]) == len(t)
        assert result["SNR_proxy"] > 0
