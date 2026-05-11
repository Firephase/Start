from dataclasses import dataclass, field
import numpy as np
from .mode_manager import HarmonicMode


@dataclass
class WaveformResult:
    time: np.ndarray
    h_plus: np.ndarray
    h_cross: np.ndarray
    phase: np.ndarray           # orbital phase Φ_φ(t)
    amplitude_envelope: np.ndarray  # |h(t)| envelope
    selected_modes: list[HarmonicMode]

    @property
    def strain_complex(self) -> np.ndarray:
        return self.h_plus + 1j * self.h_cross

    @property
    def instantaneous_frequency(self) -> np.ndarray:
        """d(phase)/dt via finite differences."""
        dt = np.diff(self.time)
        dphi = np.diff(self.phase)
        freq = np.concatenate([[dphi[0] / dt[0]], dphi / dt])
        return freq / (2 * np.pi)


@dataclass
class ModeAmplitudeTable:
    modes: list[HarmonicMode]
    amplitudes: list[float]  # peak amplitude for each mode
    phases: list[float]      # initial phase for each mode


@dataclass
class PhaseDiagnostics:
    time: np.ndarray
    phi_orbital: np.ndarray   # Φ_φ(t)
    phi_radial: np.ndarray    # Φ_r(t)
    phi_gw: np.ndarray        # 2·Φ_φ (dominant GW phase)
    omega_phi: np.ndarray
    omega_r: np.ndarray


@dataclass
class SpectrumDiagnostics:
    frequencies: np.ndarray
    power_plus: np.ndarray
    power_cross: np.ndarray
    peak_frequencies: np.ndarray
    peak_mode_labels: list[str]
