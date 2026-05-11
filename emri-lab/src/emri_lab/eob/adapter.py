"""Compatibility adapter between trajectory sources and the waveform engine."""
from __future__ import annotations

import numpy as np

from emri_lab.domain.models import InspiralResult
from .config import EOBState


class TrajectoryAdapter:
    """Convert different trajectory types to a common dict for the waveform engine.

    The waveform engine expects a trajectory dict with the keys:
        ``t``, ``r_circ``, ``p``, ``e``, ``E``, ``L``, ``Omega_phi``

    This adapter converts both :class:`InspiralResult` (adiabatic) and
    :class:`EOBState` (EOB integrator) to that common format, and can also
    wrap such a dict back into an :class:`InspiralResult` for downstream code
    that expects the domain model.
    """

    def from_adiabatic(self, evolution: InspiralResult) -> dict:
        """Convert an :class:`InspiralResult` to a waveform-compatible dict.

        Parameters
        ----------
        evolution : InspiralResult
            Output of the adiabatic inspiral integrator.

        Returns
        -------
        dict
            Trajectory dict with keys ``t``, ``r_circ``, ``p``, ``e``,
            ``E``, ``L``, ``Omega_phi``, ``source``.
        """
        return {
            "t": evolution.t,
            "r_circ": evolution.r_circ,
            "p": evolution.p_arr,
            "e": evolution.e_arr,
            "E": evolution.E_arr,
            "L": evolution.L_arr,
            "Omega_phi": evolution.Omega_phi,
            "source": "adiabatic",
        }

    def from_eob(self, eob_state: EOBState) -> dict:
        """Convert an :class:`EOBState` to a waveform-compatible dict.

        The EOB trajectory is quasi-circular, so eccentricity is set to zero
        and the semi-latus rectum p is approximated by r.

        Parameters
        ----------
        eob_state : EOBState
            Output of the EOB integrator.

        Returns
        -------
        dict
            Trajectory dict with keys ``t``, ``r_circ``, ``p``, ``e``,
            ``E``, ``L``, ``Omega_phi``, ``source``.
        """
        r = eob_state.r
        pphi = eob_state.pphi
        Omega_phi = pphi / np.maximum(r**2, 1e-10)
        return {
            "t": eob_state.t,
            "r_circ": r,
            "p": r,                        # circular approximation: p ≈ r
            "e": np.zeros_like(r),
            "E": eob_state.hreal,
            "L": pphi,
            "Omega_phi": Omega_phi,
            "source": "eob",
        }

    def to_inspiral_result(self, traj_dict: dict) -> InspiralResult:
        """Wrap a trajectory dict into an :class:`InspiralResult`.

        Useful for passing EOB trajectories to code that already expects the
        domain model type.

        Parameters
        ----------
        traj_dict : dict
            A trajectory dict as returned by :meth:`from_adiabatic` or
            :meth:`from_eob`.

        Returns
        -------
        InspiralResult
        """
        return InspiralResult(
            t=traj_dict["t"],
            p_arr=traj_dict["p"],
            e_arr=traj_dict["e"],
            E_arr=traj_dict["E"],
            L_arr=traj_dict["L"],
            r_circ=traj_dict["r_circ"],
            plunged=False,
            message=f"From {traj_dict.get('source', 'unknown')} trajectory",
        )
