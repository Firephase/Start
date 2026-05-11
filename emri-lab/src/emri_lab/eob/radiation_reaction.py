"""Radiation reaction forces for the EOB equations of motion."""
from __future__ import annotations

import numpy as np

from emri_lab.physics.fluxes import BaseFluxModel, get_flux_model
from emri_lab.domain.enums import FluxModelId
from .horizon_flux import HorizonFluxModel
from .config import EOBConfig


class EOBRadiationReaction:
    """Radiation reaction forces for EOB equations of motion.

    The azimuthal driving force is:
        dp_φ/dt = F_φ = -η · dL/dt

    where dL/dt is taken from the chosen GW flux model (and optionally
    supplemented by the horizon flux).  The radial force F_r is set to
    zero in the quasi-circular approximation.
    """

    def __init__(self, flux_model: BaseFluxModel | None = None) -> None:
        self._flux_model = flux_model
        self._horizon = HorizonFluxModel()

    def _get_flux(self, cfg: EOBConfig) -> BaseFluxModel:
        if self._flux_model is not None:
            return self._flux_model
        return get_flux_model(FluxModelId(cfg.flux_model))

    def azimuthal_force(
        self,
        eob_state: dict,
        flux_data: dict,
        cfg: EOBConfig,
    ) -> float:
        """Compute dp_φ/dt = -η · F_L.

        Parameters
        ----------
        eob_state : dict
            Current orbit state.  Expected keys: ``"r"``, ``"p"`` (fallback),
            ``"e"``, ``"eta"``.
        flux_data : dict
            Pre-computed flux values (ignored; evaluated internally).
        cfg : EOBConfig
            EOB run configuration.

        Returns
        -------
        float
            Azimuthal radiation-reaction force (negative → angular momentum
            decreases during inspiral).
        """
        r = float(eob_state.get("r", 10.0))
        p = float(eob_state.get("p", r))   # circular approximation p ≈ r
        e = float(eob_state.get("e", 0.0))
        eta = float(eob_state.get("eta", cfg.eta))

        flux = self._get_flux(cfg)
        F_L = flux.flux_L(p, e)

        if cfg.include_horizon_flux:
            h_flux = self._horizon.compute(eob_state)
            F_L += h_flux.get("dLdt", 0.0)

        return -eta * F_L

    def radial_force(
        self,
        eob_state: dict,
        flux_data: dict,
        cfg: EOBConfig,
    ) -> float:
        """Radial radiation-reaction force.

        In the quasi-circular approximation this is negligible; we return 0.

        Parameters
        ----------
        eob_state : dict
            Current orbit state.
        flux_data : dict
            Pre-computed flux values (unused).
        cfg : EOBConfig
            EOB run configuration.

        Returns
        -------
        float
            Radial force (zero in quasi-circular limit).
        """
        return 0.0
