"""Batch experiment manager for parameter sweeps."""
from __future__ import annotations
import time
import uuid
import itertools
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from emri_lab.domain.models import OrbitParams, PhysicsConfig
from emri_lab.domain.enums import FluxModelId
from emri_lab.physics.adiabatic import integrate_adiabatic_pe
from emri_lab.io.results_store import save_run
from emri_lab.domain.models import RunMetadata
from .registry import ExperimentRegistry

@dataclass
class SimulationConfig:
    """Complete configuration for a single simulation run."""
    orbit: OrbitParams
    physics: PhysicsConfig
    t_max: float = 1e7
    n_points: int = 2000
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    tags: dict = field(default_factory=dict)

class BatchExperimentManager:
    """Run batches of simulations and manage results."""

    def __init__(self, registry: ExperimentRegistry | None = None, output_dir=None):
        self._registry = registry or ExperimentRegistry()
        self._output_dir = output_dir

    def run_grid(self, configs: list[SimulationConfig]) -> list[str]:
        """Run a list of configs sequentially. Returns list of run_ids."""
        run_ids = []
        for cfg in configs:
            run_id = self._run_single(cfg)
            run_ids.append(run_id)
        return run_ids

    def run_parameter_sweep(self, base_cfg: SimulationConfig, sweep_spec: dict) -> list[str]:
        """Run a parameter sweep.

        sweep_spec example:
          {"p": [8.0, 10.0, 12.0], "eta": [1e-5, 1e-4]}
        Creates cartesian product of all parameter combinations.
        """
        keys = list(sweep_spec.keys())
        value_lists = [sweep_spec[k] for k in keys]

        configs = []
        for combo in itertools.product(*value_lists):
            params = dict(zip(keys, combo))
            cfg = self._apply_params(base_cfg, params)
            configs.append(cfg)

        return self.run_grid(configs)

    def _apply_params(self, base: SimulationConfig, params: dict) -> SimulationConfig:
        """Create a new SimulationConfig with overridden parameters."""
        orbit_p = base.orbit.p
        orbit_e = base.orbit.e
        eta = base.physics.eta
        flux_model = base.physics.flux_model
        t_max = base.t_max
        n_points = base.n_points

        if "p" in params:
            orbit_p = float(params["p"])
        if "e" in params:
            orbit_e = float(params["e"])
        if "eta" in params:
            eta = float(params["eta"])
        if "flux_model" in params:
            flux_model = FluxModelId(params["flux_model"])
        if "t_max" in params:
            t_max = float(params["t_max"])
        if "n_points" in params:
            n_points = int(params["n_points"])

        orbit = OrbitParams(p=orbit_p, e=orbit_e)
        physics = PhysicsConfig(eta=eta, flux_model=flux_model)

        return SimulationConfig(
            orbit=orbit,
            physics=physics,
            t_max=t_max,
            n_points=n_points,
            tags={"sweep_params": params},
        )

    def _run_single(self, cfg: SimulationConfig) -> str:
        """Run a single simulation and register it."""
        t0 = time.time()
        try:
            result = integrate_adiabatic_pe(
                cfg.orbit, cfg.physics, t_max=cfg.t_max, n_points=cfg.n_points
            )
            meta = RunMetadata(
                run_id=cfg.run_id,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                orbit=cfg.orbit,
                config=cfg.physics,
                duration_s=time.time() - t0,
            )
            if self._output_dir is not None:
                save_run(result, meta, output_dir=self._output_dir)
            else:
                save_run(result, meta)

            self._registry.register_run({
                "run_id": cfg.run_id,
                "p0": cfg.orbit.p,
                "e0": cfg.orbit.e,
                "eta": cfg.physics.eta,
                "flux_model": cfg.physics.flux_model.value,
                "t_max": cfg.t_max,
                "n_points": cfg.n_points,
                "plunged": result.plunged,
                "duration_s": meta.duration_s,
                "status": "success",
                **cfg.tags,
            })
        except Exception as exc:
            self._registry.register_run({
                "run_id": cfg.run_id,
                "status": "failed",
                "error": str(exc),
            })

        return cfg.run_id

    def collect_results(self, run_ids: list[str]) -> dict:
        """Load saved results for a list of run IDs from registry."""
        return self._registry.compare_runs(run_ids)
