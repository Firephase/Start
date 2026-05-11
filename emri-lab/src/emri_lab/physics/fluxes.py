"""Gravitational-wave flux models for EMRI inspirals.

All quantities are in geometrized units G = c = M = 1.

Available models
----------------
BaselinePNFlux
    Peters-Mathews quadrupole with 2.5PN corrections (circular orbit limit).
    Energy flux: dE/dt = (32/5) r⁻⁵ × PN_factor(v)
    Angular momentum flux: dL/dt = (dE/dt) / Ω_φ

ExtendedTestMassFlux
    Adds the leading-order Poisson-Sasaki horizon absorption flux on top of
    the baseline model.
    Horizon flux: F_H ≈ (8/5) r⁻⁹
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from ..domain.enums import FluxModelId


class BaseFluxModel(ABC):
    """Abstract base class for GW flux models."""

    model_id: FluxModelId

    @abstractmethod
    def flux_E(self, p: float, e: float) -> float:
        """Energy flux dE/dt (positive = energy lost to GWs).

        Parameters
        ----------
        p : float
            Semi-latus rectum (Schwarzschild coordinate radius for circular orbits).
        e : float
            Eccentricity.

        Returns
        -------
        float
            |dE/dt| ≥ 0.
        """

    @abstractmethod
    def flux_L(self, p: float, e: float) -> float:
        """Angular momentum flux dL/dt (positive = L lost to GWs).

        Parameters
        ----------
        p : float
            Semi-latus rectum.
        e : float
            Eccentricity.

        Returns
        -------
        float
            |dL/dt| ≥ 0.
        """


class BaselinePNFlux(BaseFluxModel):
    """Peters-Mathews quadrupole with 2.5PN circular-orbit corrections.

    The energy flux is evaluated at the circular-orbit approximation r = p.
    PN expansion through 2.5PN order follows Blanchet et al. conventions:

        F_E = (32/5) r⁻⁵ [1 + f₂ v² + f₃ v³ + f₄ v⁴ + f₅ v⁵]

    where v² = 1/r = M/r (in geometrized units).
    """

    model_id = FluxModelId.BASELINE_PN

    def flux_E(self, p: float, e: float) -> float:  # noqa: D102
        # Use the circular-orbit approximation r = p (valid to leading order in e).
        r = p
        v2 = 1.0 / r          # v² = M/r in geometrized units (M=1)
        v3 = v2 ** 1.5
        v4 = v2 ** 2
        v5 = v2 ** 2.5

        # PN correction coefficients
        f2 = -1247.0 / 336.0 * v2
        f3 = 4.0 * np.pi * v3
        f4 = -44711.0 / 9072.0 * v4
        f5 = -8191.0 * np.pi / 672.0 * v5

        pn_factor = 1.0 + f2 + f3 + f4 + f5

        return (32.0 / 5.0) * r ** (-5) * pn_factor

    def flux_L(self, p: float, e: float) -> float:  # noqa: D102
        # dL/dt = (dE/dt) / Ω_φ,  Ω_φ = r^{-3/2} for Keplerian / Schwarzschild circular
        r = p
        Omega_phi = r ** (-1.5)
        return self.flux_E(p, e) / Omega_phi


class ExtendedTestMassFlux(BaseFluxModel):
    """Baseline PN flux plus leading-order Poisson-Sasaki horizon absorption.

    The horizon flux (energy absorbed by the black hole horizon) at leading
    post-Newtonian order is (Poisson & Sasaki 1995):

        F_H ≈ (8/5) r⁻⁹

    This is added to the infinity flux from ``BaselinePNFlux``.
    """

    model_id = FluxModelId.EXTENDED_TEST_MASS

    _baseline: BaselinePNFlux

    def __init__(self) -> None:
        self._baseline = BaselinePNFlux()

    def flux_E(self, p: float, e: float) -> float:  # noqa: D102
        r = p
        F_inf = self._baseline.flux_E(p, e)
        F_hor = (8.0 / 5.0) * r ** (-9)
        return F_inf + F_hor

    def flux_L(self, p: float, e: float) -> float:  # noqa: D102
        r = p
        Omega_phi = r ** (-1.5)
        return self.flux_E(p, e) / Omega_phi


def get_flux_model(model_id: FluxModelId) -> BaseFluxModel:
    """Factory: return the flux model instance for *model_id*.

    Parameters
    ----------
    model_id : FluxModelId
        Identifier for the desired flux model.

    Returns
    -------
    BaseFluxModel
        Concrete flux model instance.

    Raises
    ------
    ValueError
        If *model_id* does not correspond to a known model.
    """
    if model_id == FluxModelId.BASELINE_PN:
        return BaselinePNFlux()
    if model_id == FluxModelId.EXTENDED_TEST_MASS:
        return ExtendedTestMassFlux()
    raise ValueError(f"Unknown flux model: {model_id!r}")
