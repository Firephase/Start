"""Typed configuration objects for EMRI simulation runs."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SystemParams:
    """Physical parameters of the EMRI system."""
    M: float = 1.0          # central black hole mass (geometrized units)
    mu: float = 1e-5        # small body mass (mass ratio eta = mu/M)
    distance: float = 1.0   # luminosity distance (in units of M)
    inclination: float = 0.0  # orbital inclination [radians]

    @property
    def eta(self) -> float:
        return self.mu / self.M


@dataclass
class OrbitParams:
    """Initial orbital parameters."""
    r0: float = 10.0        # initial radial coordinate
    pr0: float = 0.0        # initial radial momentum (0 for circular)
    mode: Literal["circular", "perturbed", "eccentric"] = "circular"
    eccentricity: float = 0.0   # orbital eccentricity (for eccentric mode)
    p_semi: float | None = None  # semi-latus rectum (alternative parametrization)


@dataclass
class IntegratorParams:
    """ODE integrator settings."""
    method: str = "DOP853"
    rtol: float = 1e-12
    atol: float = 1e-12
    tau_max: float = 5000.0    # max proper time
    n_points: int = 50000      # output points
    dense_output: bool = False


@dataclass
class RunConfig:
    """Complete configuration for a simulation run."""
    system: SystemParams = field(default_factory=SystemParams)
    orbit: OrbitParams = field(default_factory=OrbitParams)
    integrator: IntegratorParams = field(default_factory=IntegratorParams)
    output_dir: str = "output"
    run_id: str = "run_001"
