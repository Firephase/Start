from abc import ABC, abstractmethod
import numpy as np
from .mode_manager import HarmonicMode


class BaseAmplitudeModel(ABC):
    """Abstract amplitude model for harmonic modes."""

    @abstractmethod
    def amplitude(self, mode: HarmonicMode, orbit_state: dict) -> complex:
        """Compute complex amplitude for a given mode and orbit state.

        orbit_state dict keys: 'r', 'p', 'e', 'eta', 'distance', 'iota'
        """


class BaselineQuadrupoleAmplitude(BaseAmplitudeModel):
    """Quadrupole amplitude in the Peters-Mathews approximation.

    For dominant mode (n=0, m=2): standard quadrupole.
    For other modes: amplitude scaled by eccentricity content e^|n| / (|n|+1).
    """

    def amplitude(self, mode: HarmonicMode, orbit_state: dict) -> complex:
        r = orbit_state.get("r", orbit_state.get("p", 10.0))
        eta = orbit_state.get("eta", 1e-5)
        e = orbit_state.get("e", 0.0)
        iota = orbit_state.get("iota", 0.0)
        distance = orbit_state.get("distance", 1.0)

        # Base quadrupole amplitude A = 4η / (r * distance)
        A_base = 4.0 * eta / (r * distance)

        n, m = mode.n, mode.m

        if n == 0 and abs(m) == 2:
            # Dominant quadrupole mode
            amp = A_base
        elif abs(m) == 2:
            # Eccentric harmonics: scale by e^|n| / (|n|+1)
            amp = A_base * (e ** abs(n)) / (abs(n) + 1)
        else:
            denom = abs(n) + abs(m)
            if denom == 0:
                amp = 0.0
            else:
                amp = A_base * (e ** (abs(n) + abs(m) - 2)) / denom

        # Polarization factor for inclination iota
        # For m > 0: h ~ -(1+cos²ι)/2 exp(imΦ) + i cosι exp(imΦ)
        # For m < 0: complex conjugate contribution
        if m > 0:
            pol_factor = -(1.0 + np.cos(iota) ** 2) / 2.0 + 1j * (-np.cos(iota))
        else:
            pol_factor = -(1.0 + np.cos(iota) ** 2) / 2.0 - 1j * (-np.cos(iota))

        return complex(amp * pol_factor)


class AmplitudeModelRegistry:
    """Registry of available amplitude models."""

    _models: dict[str, type] = {
        "baseline_quadrupole": BaselineQuadrupoleAmplitude,
    }

    @classmethod
    def get(cls, name: str) -> BaseAmplitudeModel:
        if name not in cls._models:
            raise ValueError(
                f"Unknown amplitude model: {name}. Available: {list(cls._models)}"
            )
        return cls._models[name]()

    @classmethod
    def register(cls, name: str, model_cls: type) -> None:
        cls._models[name] = model_cls
