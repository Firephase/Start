"""Application use cases: high-level orchestration of geodesic and inspiral simulations."""

import time
import uuid
from dataclasses import dataclass

import numpy as np

from emri_lab.domain.models import OrbitParams, PhysicsConfig, InspiralResult, RunMetadata, WaveformPreview
from emri_lab.domain.enums import FluxModelId
from emri_lab.physics.orbit_parametrization import pe_to_EL, classify_orbit
from emri_lab.physics.adiabatic import integrate_adiabatic_pe
from emri_lab.physics.fluxes import get_flux_model


@dataclass
class GeodesicSimResult:
    """Result of a geodesic orbit classification and constants-of-motion computation."""

    run_id: str
    """Short unique identifier for this run."""

    orbit_type: str
    """Orbit classification value (from OrbitType enum)."""

    E: float
    """Specific energy of the orbit."""

    L: float
    """Specific angular momentum of the orbit."""

    r_peri: float
    """Periapsis coordinate radius."""

    r_apo: float
    """Apoapsis coordinate radius."""

    duration_s: float
    """Wall-clock time in seconds for the computation."""


def run_geodesic_simulation(orbit: OrbitParams, config: PhysicsConfig) -> GeodesicSimResult:
    """Compute orbit classification and constants of motion.

    This is a fast, pure-Schwarzschild geodesic analysis: no ODE integration,
    just energy/angular-momentum computation and orbit-type classification.

    Parameters
    ----------
    orbit : OrbitParams
        Initial orbital parameters (p, e).
    config : PhysicsConfig
        Physics configuration (used for context, e.g. flux model selection).

    Returns
    -------
    GeodesicSimResult
        Classification and conserved quantities.
    """
    t0 = time.time()
    run_id = str(uuid.uuid4())[:8]

    E, L = pe_to_EL(orbit.p, orbit.e)
    orbit_type = classify_orbit(orbit.p, orbit.e)

    return GeodesicSimResult(
        run_id=run_id,
        orbit_type=orbit_type.value,
        E=E,
        L=L,
        r_peri=orbit.r_peri,
        r_apo=orbit.r_apo,
        duration_s=time.time() - t0,
    )


def run_adiabatic_simulation(
    orbit: OrbitParams,
    config: PhysicsConfig,
    t_max: float = 1e7,
    n_points: int = 5000,
) -> tuple[InspiralResult, RunMetadata]:
    """Run full adiabatic inspiral and return result + metadata.

    Delegates the actual ODE integration to ``integrate_adiabatic_pe`` in the
    physics layer and wraps the output with bookkeeping metadata.

    Parameters
    ----------
    orbit : OrbitParams
        Initial orbital parameters (p, e).
    config : PhysicsConfig
        Physics configuration (mass ratio, flux model, tolerances).
    t_max : float
        Maximum integration time in geometrized units (default 1e7 M).
    n_points : int
        Number of output time points (default 5000).

    Returns
    -------
    tuple[InspiralResult, RunMetadata]
        The inspiral trajectory result and associated run metadata.
    """
    t0 = time.time()
    run_id = str(uuid.uuid4())[:8]

    result = integrate_adiabatic_pe(orbit, config, t_max=t_max, n_points=n_points)

    meta = RunMetadata(
        run_id=run_id,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        orbit=orbit,
        config=config,
        duration_s=time.time() - t0,
    )

    return result, meta
