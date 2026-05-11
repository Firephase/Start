from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .enums import FluxModelId


@dataclass
class OrbitParams:
    """Orbital parameters in the (p, e) semi-latus rectum / eccentricity parametrization."""

    p: float
    e: float
    chi_r0: float = 0.0
    phi0: float = 0.0

    def __post_init__(self) -> None:
        if self.p <= 0:
            raise ValueError(f"Semi-latus rectum p must be positive, got {self.p}")
        if self.e < 0:
            raise ValueError(f"Eccentricity e must be non-negative, got {self.e}")
        if self.e >= 1:
            raise ValueError(f"Eccentricity e must be < 1 for bound orbits, got {self.e}")

    @property
    def is_circular(self) -> bool:
        """Return True when the orbit is effectively circular (e < 1e-6)."""
        return self.e < 1e-6

    @property
    def r_peri(self) -> float:
        """Periapsis coordinate radius."""
        return self.p / (1.0 + self.e)

    @property
    def r_apo(self) -> float:
        """Apoapsis coordinate radius."""
        return self.p / (1.0 - self.e)


@dataclass
class PhysicsConfig:
    """Configuration knobs for the physics layer."""

    eta: float = 1e-5
    """Mass ratio μ/M (small parameter)."""

    flux_model: FluxModelId = FluxModelId.BASELINE_PN
    """Which gravitational-wave flux model to use."""

    use_horizon_flux: bool = False
    """Whether to add the Poisson-Sasaki horizon flux on top of the baseline model."""

    rtol: float = 1e-10
    """Relative tolerance for ODE integration."""

    atol: float = 1e-10
    """Absolute tolerance for ODE integration."""

    def __post_init__(self) -> None:
        if not (0 < self.eta <= 1):
            raise ValueError(f"Mass ratio eta must be in (0, 1], got {self.eta}")
        if self.rtol <= 0 or self.atol <= 0:
            raise ValueError("rtol and atol must be positive")


@dataclass
class InspiralResult:
    """Output of an adiabatic inspiral integration."""

    t: np.ndarray
    """Coordinate time array."""

    p_arr: np.ndarray
    """Semi-latus rectum p(t)."""

    e_arr: np.ndarray
    """Eccentricity e(t)."""

    E_arr: np.ndarray
    """Specific energy E(t)."""

    L_arr: np.ndarray
    """Specific angular momentum L(t)."""

    r_circ: np.ndarray
    """Equivalent circular radius r_circ = p (valid when e≈0 or as representative scale)."""

    plunged: bool
    """True if the inspiral reached the separatrix / plunge condition."""

    message: str
    """Human-readable summary of the integration outcome."""

    @property
    def Omega_phi(self) -> np.ndarray:
        """Azimuthal orbital angular frequency Ω_φ = r^{-3/2} (Keplerian / Schwarzschild circular)."""
        return self.r_circ ** (-1.5)

    @property
    def frequency_gw(self) -> np.ndarray:
        """Leading gravitational-wave frequency f_GW = Ω_φ / π (dominant l=m=2 mode, geometrized)."""
        return self.Omega_phi / np.pi


@dataclass
class RunMetadata:
    """Bookkeeping metadata attached to each simulation run."""

    run_id: str
    """Unique identifier for this run (e.g. UUID)."""

    timestamp: str
    """ISO-8601 timestamp of when the run was started."""

    orbit: OrbitParams
    """Initial orbital parameters."""

    config: PhysicsConfig
    """Physics configuration used."""

    duration_s: float
    """Wall-clock time in seconds for the integration."""


@dataclass
class WaveformPreview:
    """Lightweight gravitational waveform preview (time-domain strain)."""

    t: np.ndarray
    """Time array (geometrized units)."""

    h_plus: np.ndarray
    """Plus polarization h₊(t)."""

    h_cross: np.ndarray
    """Cross polarization h×(t)."""
