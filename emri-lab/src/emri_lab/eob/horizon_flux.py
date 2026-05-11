"""Horizon absorption flux model (Poisson-Sasaki leading order)."""
from __future__ import annotations

import numpy as np


class HorizonFluxModel:
    """Horizon absorption flux model (Poisson-Sasaki leading order).

    Energy absorbed by the horizon at leading post-Newtonian order:
        F_H_E = (8/5) r^{-9}

    Angular momentum absorbed (using Ω_φ = r^{-3/2} for circular orbits):
        F_H_L = F_H_E / Ω_φ = (8/5) r^{-9} × r^{3/2} = (8/5) r^{-15/2}

    Reference: Poisson & Sasaki (1995).
    """

    def compute(self, orbit_state: dict) -> dict:
        """Return horizon contributions to dE/dt and dL/dt.

        Parameters
        ----------
        orbit_state : dict
            Must contain at least one of ``"r"`` or ``"p"`` (uses ``"r"`` first).

        Returns
        -------
        dict
            Keys ``"dEdt"`` and ``"dLdt"`` (both positive → energy/momentum
            carried away from the orbit into the horizon).
        """
        r = orbit_state.get("r", orbit_state.get("p", 10.0))
        r = max(float(r), 2.01)  # stay away from the horizon singularity

        dEdt = (8.0 / 5.0) * r**(-9)
        Omega_phi = r**(-1.5)
        dLdt = dEdt / Omega_phi  # = (8/5) r^{-15/2}

        return {
            "dEdt": float(dEdt),
            "dLdt": float(dLdt),
        }

    def is_negligible(self, r: float, threshold: float = 1e-3) -> bool:
        """Return True if horizon flux is negligible relative to the r^{-5} infinity flux.

        The ratio  F_H / F_inf ~ r^{-9} / r^{-5} = r^{-4}.
        For r ≥ 10 this is already ≤ 10^{-4}, which is below the default threshold.

        Parameters
        ----------
        r : float
            Orbital radius.
        threshold : float
            Fractional threshold below which the horizon term is considered negligible.

        Returns
        -------
        bool
        """
        r = max(r, 2.01)
        ratio = r**(-9) / (r**(-5) + 1e-30)
        return float(ratio) < threshold
