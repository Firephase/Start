import numpy as np
from .mode_manager import HarmonicMode
from .amplitude import BaseAmplitudeModel


class WaveformSummationService:
    """Sums harmonic modes to produce time-domain h+/hx."""

    def build_time_domain(
        self,
        time: np.ndarray,
        modes: list[HarmonicMode],
        phases: dict,       # {HarmonicMode: np.ndarray}
        amplitudes: dict,   # {HarmonicMode: complex (or np.ndarray if time-varying)}
    ) -> dict:
        """Sum modes to get h_plus, h_cross, strain_complex.

        For each mode (n,m):
          contribution = A_{n,m} * exp(i * Φ_{n,m}(t))
        h = Σ contributions
        h_+ = Re(h), h_× = Im(h)
        """
        n = len(time)
        h_complex = np.zeros(n, dtype=complex)

        for mode in modes:
            phi = phases.get(mode, np.zeros(n))
            amp = amplitudes.get(mode, 0.0)

            if np.isscalar(amp):
                contribution = amp * np.exp(1j * phi)
            else:
                # Time-varying amplitude array
                contribution = amp * np.exp(1j * phi)

            h_complex += contribution

        h_plus = np.real(h_complex)
        h_cross = np.imag(h_complex)

        return {
            "h_plus": h_plus,
            "h_cross": h_cross,
            "strain_complex": h_complex,
        }

    def build_mode_amplitudes(
        self,
        inspiral_result,
        modes: list[HarmonicMode],
        amplitude_model: BaseAmplitudeModel,
        eta: float,
        distance: float = 1.0,
        iota: float = 0.0,
    ) -> dict:
        """Compute (constant) complex amplitude for each mode using midpoint orbit state."""
        r = inspiral_result.r_circ
        e = inspiral_result.e_arr
        p = inspiral_result.p_arr

        # Use midpoint orbit state for amplitude evaluation
        mid = len(r) // 2
        orbit_state = {
            "r": float(r[mid]),
            "p": float(p[mid]),
            "e": float(e[mid]),
            "eta": eta,
            "distance": distance,
            "iota": iota,
        }

        result = {}
        for mode in modes:
            result[mode] = amplitude_model.amplitude(mode, orbit_state)
        return result
