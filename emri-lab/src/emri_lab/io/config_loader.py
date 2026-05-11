"""YAML configuration loader with Pydantic validation.

Loads run configurations from YAML files, validates them with Pydantic schemas,
and converts them to domain model instances.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from emri_lab.domain.enums import FluxModelId
from emri_lab.domain.models import OrbitParams, PhysicsConfig


class OrbitParamsSchema(BaseModel):
    """Pydantic schema for orbit parameters validation."""

    p: float = Field(gt=6.0, description="Semi-latus rectum (must be > 6 M)")
    e: float = Field(ge=0.0, lt=1.0, description="Eccentricity (0 ≤ e < 1)")
    chi_r0: float = 0.0
    phi0: float = 0.0


class PhysicsConfigSchema(BaseModel):
    """Pydantic schema for physics configuration validation."""

    eta: float = Field(default=1e-5, gt=0.0, lt=1.0, description="Mass ratio μ/M")
    flux_model: FluxModelId = FluxModelId.BASELINE_PN
    use_horizon_flux: bool = False
    rtol: float = 1e-10
    atol: float = 1e-10


class RunConfigSchema(BaseModel):
    """Top-level run configuration schema."""

    orbit: OrbitParamsSchema
    physics: PhysicsConfigSchema = Field(default_factory=PhysicsConfigSchema)
    t_max: float = 1e7
    n_points: int = 5000


def load_config(path: str | Path) -> RunConfigSchema:
    """Load and validate a YAML run configuration file.

    Parameters
    ----------
    path : str or Path
        Path to the YAML configuration file.

    Returns
    -------
    RunConfigSchema
        Validated configuration object.

    Raises
    ------
    FileNotFoundError
        If the config file does not exist.
    pydantic.ValidationError
        If the config values fail validation.
    """
    with open(path) as f:
        data = yaml.safe_load(f)
    return RunConfigSchema(**data)


def orbit_from_config(cfg: RunConfigSchema) -> OrbitParams:
    """Convert an orbit config schema to an OrbitParams domain object.

    Parameters
    ----------
    cfg : RunConfigSchema
        Validated run configuration.

    Returns
    -------
    OrbitParams
        Domain orbit parameters.
    """
    o = cfg.orbit
    return OrbitParams(p=o.p, e=o.e, chi_r0=o.chi_r0, phi0=o.phi0)


def physics_from_config(cfg: RunConfigSchema) -> PhysicsConfig:
    """Convert a physics config schema to a PhysicsConfig domain object.

    Parameters
    ----------
    cfg : RunConfigSchema
        Validated run configuration.

    Returns
    -------
    PhysicsConfig
        Domain physics configuration.
    """
    p = cfg.physics
    return PhysicsConfig(
        eta=p.eta,
        flux_model=p.flux_model,
        use_horizon_flux=p.use_horizon_flux,
        rtol=p.rtol,
        atol=p.atol,
    )
