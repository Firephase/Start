"""EOB Hamiltonian: H_eff and H_real plus Hamilton's equations of motion."""
from __future__ import annotations

import numpy as np

from .config import EOBConfig
from .potentials import EOBPotentialService, get_potential_service


class EOBHamiltonian:
    """EOB Hamiltonian evaluator.

    State vector: [r, p_r, phi, p_phi]

    The effective Hamiltonian is:
        H_eff = sqrt( A(u) * (1 + p_φ² u² + p_r²/D(u) + Q(u, p_r)) )

    The real Hamiltonian (in reduced units μ = M = 1) is:
        H_real = sqrt( 1 + 2ν (H_eff - 1) )

    For ν → 0: H_real = H_eff (geodesic limit).
    """

    def __init__(self, potential_service: EOBPotentialService | None = None) -> None:
        self._fixed_potentials = potential_service

    def _get_potentials(self, cfg: EOBConfig) -> EOBPotentialService:
        if self._fixed_potentials is not None:
            return self._fixed_potentials
        return get_potential_service(cfg.conservative_model)

    def heff(self, state: np.ndarray, cfg: EOBConfig) -> float:
        """Compute H_eff = sqrt(A·(1 + p_φ²u² + p_r²/D + Q)).

        Parameters
        ----------
        state : np.ndarray
            Phase-space vector [r, p_r, phi, p_phi].
        cfg : EOBConfig
            EOB configuration.

        Returns
        -------
        float
            Effective Hamiltonian value.
        """
        r, pr, phi, pphi = state
        u = 1.0 / max(r, 1e-10)
        pot = self._get_potentials(cfg)
        params = {"nu": cfg.nu, "eta": cfg.eta}

        A = pot.A(u, params)
        D = pot.D(u, params)
        Q = pot.Q(u, pr, params)

        under = A * (1.0 + pphi**2 * u**2 + pr**2 / max(D, 1e-10) + Q)
        return float(np.sqrt(max(under, 1e-30)))

    def hreal(self, state: np.ndarray, cfg: EOBConfig) -> float:
        """Compute H_real = sqrt(1 + 2ν·(H_eff - 1)) in reduced units.

        For ν → 0 this returns H_eff exactly (geodesic limit).

        Parameters
        ----------
        state : np.ndarray
            Phase-space vector [r, p_r, phi, p_phi].
        cfg : EOBConfig
            EOB configuration.

        Returns
        -------
        float
            Real EOB Hamiltonian value.
        """
        heff_val = self.heff(state, cfg)
        nu = cfg.nu
        if nu < 1e-12:
            return heff_val
        return float(np.sqrt(max(1.0 + 2.0 * nu * (heff_val - 1.0), 1e-30)))

    def rhs(
        self,
        t: float,
        state: np.ndarray,
        cfg: EOBConfig,
        F_phi: float = 0.0,
        F_r: float = 0.0,
    ) -> np.ndarray:
        """Hamilton's equations of motion + radiation reaction forces.

        Equations:
            dr/dt   =  ∂H_eff/∂p_r
            dp_r/dt = -∂H_eff/∂r + F_r
            dφ/dt   =  ∂H_eff/∂p_φ
            dp_φ/dt = F_φ   (radiation reaction only; no conservative torque)

        The partial derivatives of H_eff w.r.t. p_r and p_φ are analytic.
        The derivative w.r.t. r is computed via centred finite differences to
        handle the general (ν-dependent) potential case robustly.

        Parameters
        ----------
        t : float
            Current coordinate time (unused directly; required by solve_ivp API).
        state : np.ndarray
            Phase-space vector [r, p_r, phi, p_phi].
        cfg : EOBConfig
            EOB configuration.
        F_phi : float
            Azimuthal radiation-reaction force dp_φ/dt (negative = inspiral).
        F_r : float
            Radial radiation-reaction force (typically ≈ 0 quasi-circularly).

        Returns
        -------
        np.ndarray
            Time derivatives [dr/dt, dp_r/dt, dφ/dt, dp_φ/dt].
        """
        r, pr, phi, pphi = state
        u = 1.0 / max(r, 1e-10)
        pot = self._get_potentials(cfg)
        params = {"nu": cfg.nu, "eta": cfg.eta}

        A = pot.A(u, params)
        D = pot.D(u, params)
        H = self.heff(state, cfg)
        H_safe = max(H, 1e-30)

        # Analytic ∂H_eff/∂p_φ = A · p_φ · u² / H_eff
        dH_dpphi = A * pphi * u**2 / H_safe

        # Analytic ∂H_eff/∂p_r = A · p_r / (D · H_eff)
        dH_dpr = A * pr / max(D * H_safe, 1e-30)

        # Numerical ∂H_eff/∂r via centred differences (handles general potentials)
        h = max(1e-5 * r, 1e-8)
        u_p = 1.0 / (r + h)
        u_m = 1.0 / (r - h)
        A_p = pot.A(u_p, params)
        A_m = pot.A(u_m, params)
        D_p = pot.D(u_p, params)
        D_m = pot.D(u_m, params)
        Q_p = pot.Q(u_p, pr, params)
        Q_m = pot.Q(u_m, pr, params)

        inner_p = A_p * (1.0 + pphi**2 * u_p**2 + pr**2 / max(D_p, 1e-10) + Q_p)
        inner_m = A_m * (1.0 + pphi**2 * u_m**2 + pr**2 / max(D_m, 1e-10) + Q_m)

        Heff_p = float(np.sqrt(max(inner_p, 1e-30)))
        Heff_m = float(np.sqrt(max(inner_m, 1e-30)))
        dH_dr = (Heff_p - Heff_m) / (2.0 * h)

        # Equations of motion
        dr_dt = dH_dpr
        dpr_dt = -dH_dr + F_r
        dphi_dt = dH_dpphi
        dpphi_dt = F_phi  # driven entirely by radiation reaction

        return np.array([dr_dt, dpr_dt, dphi_dt, dpphi_dt])
