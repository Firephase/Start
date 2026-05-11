"""Model comparison service for trajectory and waveform analysis."""
from __future__ import annotations

import numpy as np
from scipy.interpolate import interp1d


class ModelComparisonService:
    """Compare two trajectories or waveforms quantitatively.

    All methods accept trajectory dicts with at minimum the keys:
        ``t``, ``r_circ``, ``Omega_phi``

    Waveform comparison methods accept :class:`~emri_lab.waveform.result.WaveformResult`
    objects (which carry ``.time``, ``.h_plus``, ``.phase`` attributes).
    """

    # ------------------------------------------------------------------
    # Trajectory comparison
    # ------------------------------------------------------------------

    def compare_trajectories(self, a: dict, b: dict) -> dict:
        """Compare two trajectory dicts on a common time grid.

        The two trajectories are linearly interpolated onto the overlapping
        portion of their time axes.  Phase accumulation is estimated by
        integrating the angular frequency Ω_φ.

        Parameters
        ----------
        a, b : dict
            Trajectory dicts as produced by :class:`~emri_lab.eob.adapter.TrajectoryAdapter`.
            Required keys: ``"t"``, ``"r_circ"``, ``"Omega_phi"``.

        Returns
        -------
        dict
            Keys:
            - ``t_common``        – shared time grid
            - ``r_diff``          – r_a(t) − r_b(t)
            - ``r_rms_diff``      – RMS of r_diff
            - ``dephasing``       – Δφ(t) = φ_a(t) − φ_b(t)
            - ``max_dephasing``   – max |Δφ|
            - ``final_dephasing`` – Δφ at the end of the common window
        """
        t_a = np.asarray(a["t"])
        t_b = np.asarray(b["t"])

        t_start = max(t_a[0], t_b[0])
        t_end = min(t_a[-1], t_b[-1])

        if t_end <= t_start:
            return {"error": "No overlapping time range"}

        n_common = min(len(t_a), len(t_b))
        t_common = np.linspace(t_start, t_end, max(n_common, 2))

        def _interp(t_src, y_src, t_tgt):
            f = interp1d(
                t_src, y_src,
                kind="linear",
                bounds_error=False,
                fill_value="extrapolate",
            )
            return f(t_tgt)

        # Radial separation
        r_a = _interp(t_a, np.asarray(a["r_circ"]), t_common)
        r_b = _interp(t_b, np.asarray(b["r_circ"]), t_common)

        # Phase via cumulative trapezoidal integration of Ω_φ
        def _phase(t_src, omega_src, t_tgt):
            omega_interp = _interp(t_src, np.asarray(omega_src), t_tgt)
            dt = np.concatenate([[0.0], np.diff(t_tgt)])
            return np.cumsum(omega_interp * dt)

        phi_a = _phase(t_a, a["Omega_phi"], t_common)
        phi_b = _phase(t_b, b["Omega_phi"], t_common)
        dephasing = phi_a - phi_b

        return {
            "t_common": t_common,
            "r_diff": r_a - r_b,
            "r_rms_diff": float(np.sqrt(np.mean((r_a - r_b) ** 2))),
            "dephasing": dephasing,
            "max_dephasing": float(np.max(np.abs(dephasing))),
            "final_dephasing": float(dephasing[-1]),
        }

    # ------------------------------------------------------------------
    # Waveform phase comparison
    # ------------------------------------------------------------------

    def compare_phases(self, wf_a, wf_b) -> dict:
        """Compare GW phases of two WaveformResult objects.

        Parameters
        ----------
        wf_a, wf_b : WaveformResult
            Must carry ``.time`` and ``.phase`` arrays.

        Returns
        -------
        dict
            Keys: ``t``, ``phase_residual``, ``max_phase_diff``, ``rms_phase_diff``.
        """
        t_min = max(wf_a.time[0], wf_b.time[0])
        t_max = min(wf_a.time[-1], wf_b.time[-1])
        n = min(len(wf_a.time), len(wf_b.time))
        t_common = np.linspace(t_min, t_max, max(n, 2))

        f_a = interp1d(
            wf_a.time, wf_a.phase,
            kind="linear", bounds_error=False, fill_value="extrapolate",
        )
        f_b = interp1d(
            wf_b.time, wf_b.phase,
            kind="linear", bounds_error=False, fill_value="extrapolate",
        )

        phase_a = f_a(t_common)
        phase_b = f_b(t_common)
        residual = phase_a - phase_b

        return {
            "t": t_common,
            "phase_residual": residual,
            "max_phase_diff": float(np.max(np.abs(residual))),
            "rms_phase_diff": float(np.sqrt(np.mean(residual ** 2))),
        }

    # ------------------------------------------------------------------
    # Flux comparison
    # ------------------------------------------------------------------

    def compare_fluxes(self, flux_a: dict, flux_b: dict) -> dict:
        """Compare two flux model outputs.

        Parameters
        ----------
        flux_a, flux_b : dict
            Each should contain at least ``"dEdt"`` and ``"dLdt"`` keys.

        Returns
        -------
        dict
            Absolute and relative differences for energy and angular
            momentum flux.
        """
        E_a = float(flux_a.get("dEdt", 0.0))
        E_b = float(flux_b.get("dEdt", 0.0))
        L_a = float(flux_a.get("dLdt", 0.0))
        L_b = float(flux_b.get("dLdt", 0.0))

        dE_rel = abs(E_a - E_b) / max(abs(E_a), 1e-30)
        dL_rel = abs(L_a - L_b) / max(abs(L_a), 1e-30)

        return {
            "dEdt_a": E_a,
            "dEdt_b": E_b,
            "dEdt_rel_diff": float(dE_rel),
            "dLdt_a": L_a,
            "dLdt_b": L_b,
            "dLdt_rel_diff": float(dL_rel),
        }

    # ------------------------------------------------------------------
    # Mismatch
    # ------------------------------------------------------------------

    def waveform_mismatch(self, wf_a, wf_b) -> float:
        """Compute the waveform mismatch 1 − ⟨h_a | h_b⟩ / (|h_a| |h_b|).

        The inner product is the flat (un-whitened) time-domain overlap:
            ⟨h_a | h_b⟩ = ∫ h_a(t) h_b(t) dt

        interpolated onto the common time window.

        Parameters
        ----------
        wf_a, wf_b : WaveformResult
            Must carry ``.time`` and ``.h_plus`` arrays.

        Returns
        -------
        float
            Mismatch in [0, 2].  A value of 0 indicates perfect overlap.
        """
        t_min = max(wf_a.time[0], wf_b.time[0])
        t_max = min(wf_a.time[-1], wf_b.time[-1])
        n = min(len(wf_a.time), len(wf_b.time))
        t_common = np.linspace(t_min, t_max, max(n, 2))

        f_a = interp1d(
            wf_a.time, wf_a.h_plus,
            kind="linear", bounds_error=False, fill_value=0.0,
        )
        f_b = interp1d(
            wf_b.time, wf_b.h_plus,
            kind="linear", bounds_error=False, fill_value=0.0,
        )

        h_a = f_a(t_common)
        h_b = f_b(t_common)

        inner = float(np.trapz(h_a * h_b, t_common))
        norm_a = float(np.sqrt(max(np.trapz(h_a ** 2, t_common), 1e-60)))
        norm_b = float(np.sqrt(max(np.trapz(h_b ** 2, t_common), 1e-60)))

        overlap = inner / (norm_a * norm_b)
        return float(1.0 - np.clip(overlap, -1.0, 1.0))
