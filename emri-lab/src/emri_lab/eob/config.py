from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class EOBConfig:
    conservative_model: str = "schwarzschild"  # "schwarzschild" | "3pn"
    flux_model: str = "baseline_pn"
    include_horizon_flux: bool = False
    include_eccentricity: bool = True
    include_primary_spin: bool = False    # Kerr extension (future)
    include_secondary_spin: bool = False  # secondary spin (future)
    nu: float = 0.0  # symmetric mass ratio (test-mass limit = 0)
    eta: float = 1e-5  # mass ratio μ/M


@dataclass
class EOBState:
    t: np.ndarray
    r: np.ndarray
    pr: np.ndarray
    phi: np.ndarray
    pphi: np.ndarray
    heff: np.ndarray
    hreal: np.ndarray

    @property
    def r_circ(self) -> np.ndarray:
        return self.r

    @property
    def Omega_phi(self) -> np.ndarray:
        """Approximate azimuthal frequency Ω_φ ≈ p_φ / r²."""
        return self.pphi / np.maximum(self.r**2, 1e-10)
