"""High-level waveform pipeline: trajectory → waveform."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from emri_project.waveform.basic import generate_waveform_basic, accumulated_phase, amplitude_envelope
from emri_project.waveform.modes import mode_h22


@dataclass
class WaveformResult:
    """Complete waveform output."""
    t: NDArray
    h_plus: NDArray
    h_cross: NDArray
    phase: NDArray
    amplitude: NDArray
    h22: NDArray | None = None

    def snr_proxy(self) -> float:
        """Proxy for SNR: integral of h²."""
        dt = np.mean(np.diff(self.t))
        return float(np.sqrt(np.trapz(self.h_plus**2 + self.h_cross**2, self.t)))


def waveform_from_geodesic(
    t: NDArray,
    r: NDArray,
    phi: NDArray,
    eta: float,
    distance: float = 1.0,
    iota: float = 0.0,
    compute_modes: bool = True,
) -> WaveformResult:
    """Generate waveform from geodesic trajectory arrays."""
    h_plus, h_cross = generate_waveform_basic(t, r, phi, eta, distance, iota)
    phase = accumulated_phase(phi)
    amp = amplitude_envelope(h_plus, h_cross)
    h22 = mode_h22(t, r, phi, eta, distance) if compute_modes else None

    return WaveformResult(
        t=t,
        h_plus=h_plus,
        h_cross=h_cross,
        phase=phase,
        amplitude=amp,
        h22=h22,
    )


def waveform_from_inspiral(
    inspiral_t: NDArray,
    inspiral_r: NDArray,
    eta: float,
    distance: float = 1.0,
    iota: float = 0.0,
) -> WaveformResult:
    """Generate waveform from adiabatic inspiral (r(t) track).

    Phase is accumulated by integrating Ω_φ(t) = r(t)^(-3/2).
    """
    Omega = inspiral_r**(-1.5)
    phi = np.zeros_like(inspiral_t)
    for i in range(1, len(inspiral_t)):
        dt = inspiral_t[i] - inspiral_t[i - 1]
        phi[i] = phi[i - 1] + 0.5 * (Omega[i] + Omega[i - 1]) * dt

    return waveform_from_geodesic(inspiral_t, inspiral_r, phi, eta, distance, iota)
