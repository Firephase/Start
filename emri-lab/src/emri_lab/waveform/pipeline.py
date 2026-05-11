"""Top-level waveform generation pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from emri_lab.domain.models import InspiralResult
from .mode_manager import HarmonicMode, ModeSelectionPolicy
from .amplitude import BaseAmplitudeModel, BaselineQuadrupoleAmplitude, AmplitudeModelRegistry
from .phase_engine import PhaseEvolutionService
from .summation import WaveformSummationService
from .frequency_preview import FrequencyDomainPreview
from .result import WaveformResult, ModeAmplitudeTable, PhaseDiagnostics, SpectrumDiagnostics


@dataclass
class WaveformConfig:
    """Configuration for the waveform generation pipeline."""

    mode_policy: str = "dominant_only"
    """Mode selection policy name. One of: dominant_only, low_order_eccentric, fixed_grid, user_custom."""

    amplitude_model: str = "baseline_quadrupole"
    """Amplitude model registry key."""

    eta: float = 1e-5
    """Mass ratio μ/M."""

    distance: float = 1.0
    """Observer distance in geometrized units."""

    iota: float = 0.0
    """Orbital inclination angle (radians)."""

    domain: str = "time"
    """Output domain: 'time', 'frequency', or 'both'."""

    n_max: int = 3
    """Maximum radial harmonic index for fixed_grid policy."""

    custom_modes: list[tuple[int, int]] | None = None
    """User-specified (n, m) mode pairs for user_custom policy."""


class WaveformPipeline:
    """Orchestrates the full waveform generation pipeline.

    Steps
    -----
    1. Extract Ω_φ(t), Ω_r(t) from InspiralResult.
    2. Select harmonic modes via ModeSelectionPolicy.
    3. Accumulate orbital phases → PhaseDiagnostics.
    4. Compute Φ_{n,m}(t) per mode.
    5. Evaluate complex mode amplitudes via amplitude model.
    6. Sum modes → h+(t), h×(t).
    7. Build WaveformResult and ModeAmplitudeTable.
    8. Optionally compute FFT spectrum → SpectrumDiagnostics.
    """

    def __init__(self) -> None:
        self._phase_svc = PhaseEvolutionService()
        self._mode_policy = ModeSelectionPolicy()
        self._summation = WaveformSummationService()
        self._freq_preview = FrequencyDomainPreview()

    def run(
        self,
        inspiral: InspiralResult,
        cfg: WaveformConfig,
    ) -> tuple[WaveformResult, ModeAmplitudeTable, PhaseDiagnostics, SpectrumDiagnostics | None]:
        """Run complete waveform generation pipeline.

        Parameters
        ----------
        inspiral : InspiralResult
            Output from the adiabatic inspiral integrator.
        cfg : WaveformConfig
            Pipeline configuration.

        Returns
        -------
        WaveformResult
            Time-domain h+(t), h×(t), phase Φ_φ(t), amplitude envelope.
        ModeAmplitudeTable
            Per-mode amplitudes and phases used in the summation.
        PhaseDiagnostics
            Full phase evolution arrays for diagnostics.
        SpectrumDiagnostics or None
            FFT spectrum (only when cfg.domain in ('frequency', 'both')).
        """
        time = inspiral.t

        # 1. Extract frequencies from inspiral trajectory
        omega_r, omega_phi = self._phase_svc.extract_frequencies(inspiral)

        # 2. Select harmonic modes
        kwargs: dict = {"n_max": cfg.n_max}
        if cfg.custom_modes is not None:
            kwargs["modes"] = cfg.custom_modes
        modes = self._mode_policy.select_modes(inspiral, cfg.mode_policy, **kwargs)

        # 3. Build phase diagnostics (Φ_φ, Φ_r, Φ_gw arrays)
        phase_diag = self._phase_svc.build_phase_diagnostics(time, omega_r, omega_phi)

        # 4. Compute Φ_{n,m}(t) for each selected mode
        phases: dict[HarmonicMode, np.ndarray] = {}
        for mode in modes:
            phases[mode] = self._phase_svc.accumulate_harmonic_phase(
                time, omega_r, omega_phi, mode.n, mode.m
            )

        # 5. Evaluate complex amplitudes at midpoint orbit state
        amp_model: BaseAmplitudeModel = AmplitudeModelRegistry.get(cfg.amplitude_model)
        amplitudes_dict = self._summation.build_mode_amplitudes(
            inspiral, modes, amp_model, cfg.eta, cfg.distance, cfg.iota
        )

        # 6. Sum modes → time-domain strain
        td = self._summation.build_time_domain(time, modes, phases, amplitudes_dict)
        h_plus = td["h_plus"]
        h_cross = td["h_cross"]

        # 7. Assemble output objects
        phi_phi = phase_diag.phi_orbital
        amplitude_envelope = np.abs(td["strain_complex"])

        wf_result = WaveformResult(
            time=time,
            h_plus=h_plus,
            h_cross=h_cross,
            phase=phi_phi,
            amplitude_envelope=amplitude_envelope,
            selected_modes=modes,
        )

        mode_table = ModeAmplitudeTable(
            modes=modes,
            amplitudes=[abs(amplitudes_dict[m]) for m in modes],
            phases=[float(np.angle(amplitudes_dict[m])) for m in modes],
        )

        # 8. Optional frequency-domain spectrum
        spec_diag: SpectrumDiagnostics | None = None
        if cfg.domain in ("frequency", "both"):
            omega_phi_mean = float(np.mean(omega_phi))
            omega_r_mean = float(np.mean(omega_r))
            spec_diag = self._freq_preview.compute_spectrum(
                time, h_plus, h_cross, modes, omega_phi_mean, omega_r_mean
            )

        return wf_result, mode_table, phase_diag, spec_diag
