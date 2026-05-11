"""
Pydantic v2 parameter models for orbit and solver configuration.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class OrbitMode(str, Enum):
    circular   = "circular"
    el_direct  = "el_direct"
    turning_points = "turning_points"
    pe_params  = "pe_params"


class SolverConfig(BaseModel):
    """Numerical integration settings."""
    integrator: Literal["DOP853", "Radau", "RK45", "LSODA"] = "DOP853"
    tau_max: float = Field(default=2000.0, gt=0.0)
    rtol: float = Field(default=1e-10, gt=0.0)
    atol: float = Field(default=1e-12, gt=0.0)
    max_step: float = Field(default=1.0, gt=0.0)
    n_output: int = Field(default=10000, gt=10)
    stop_at_horizon: bool = True


class OrbitConfig(BaseModel):
    """Orbit specification — one mode must be consistently filled."""
    mode: OrbitMode = OrbitMode.circular

    # Circular mode
    r0: float | None = Field(default=None, gt=2.0)

    # Direct E, L mode
    E: float | None = Field(default=None, gt=0.0)
    L: float | None = Field(default=None, gt=0.0)
    r_start: float | None = Field(default=None, gt=2.0)
    pr0: float = 0.0

    # Turning-points mode
    r_peri: float | None = Field(default=None, gt=2.0)
    r_apo: float | None = Field(default=None, gt=2.0)

    # (p, e) parametrisation
    p_param: float | None = Field(default=None, gt=0.0)
    e_param: float | None = Field(default=None, ge=0.0)

    phi0: float = 0.0

    @model_validator(mode="after")
    def _validate_mode(self) -> "OrbitConfig":
        mode = self.mode
        if mode == OrbitMode.circular:
            if self.r0 is None:
                raise ValueError("circular mode requires r0")
            if self.r0 <= 3.0:
                raise ValueError(f"Circular orbit requires r0 > 3 (photon sphere); got r0={self.r0}")
        elif mode == OrbitMode.el_direct:
            if self.E is None or self.L is None:
                raise ValueError("el_direct mode requires E and L")
            if self.r_start is None:
                raise ValueError("el_direct mode requires r_start")
        elif mode == OrbitMode.turning_points:
            if self.r_peri is None or self.r_apo is None:
                raise ValueError("turning_points mode requires r_peri and r_apo")
            if self.r_peri >= self.r_apo:
                raise ValueError("r_peri must be < r_apo")
        elif mode == OrbitMode.pe_params:
            if self.p_param is None or self.e_param is None:
                raise ValueError("pe_params mode requires p_param and e_param")
        return self


class SimulationConfig(BaseModel):
    """Top-level simulation configuration."""
    name: str = "emri_simulation"
    description: str = ""
    orbit: OrbitConfig = Field(default_factory=lambda: OrbitConfig(mode=OrbitMode.circular, r0=10.0))
    solver: SolverConfig = Field(default_factory=SolverConfig)

    def to_yaml_dict(self) -> dict:
        return self.model_dump(mode="json")
