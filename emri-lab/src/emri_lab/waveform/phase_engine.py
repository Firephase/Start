import numpy as np
from scipy.integrate import cumulative_trapezoid
from .mode_manager import HarmonicMode


class PhaseEvolutionService:
    """Accumulates orbital and waveform phases from frequency arrays."""

    def accumulate_phase(self, time: np.ndarray, omega: np.ndarray) -> np.ndarray:
        """Integrate Φ(t) = ∫Ω(t')dt' using cumulative trapezoid."""
        phi = cumulative_trapezoid(omega, time, initial=0.0)
        return phi

    def accumulate_harmonic_phase(
        self,
        time: np.ndarray,
        omega_r: np.ndarray,
        omega_phi: np.ndarray,
        n: int,
        m: int,
    ) -> np.ndarray:
        """Compute Φ_{n,m}(t) = n·Φ_r(t) + m·Φ_φ(t)."""
        phi_r = self.accumulate_phase(time, omega_r)
        phi_phi = self.accumulate_phase(time, omega_phi)
        return n * phi_r + m * phi_phi

    def extract_frequencies(self, inspiral_result) -> tuple[np.ndarray, np.ndarray]:
        """Extract Ω_φ(t) and Ω_r(t) from InspiralResult.

        Ω_φ = r_circ^{-3/2} (circular Schwarzschild)
        Ω_r ≈ Ω_φ · √(1 - 6/r_circ) from Schwarzschild geodesic radial frequency formula.
        The factor max(..., 0) guards against r < 6M (near-ISCO / post-plunge data).
        """
        r = inspiral_result.r_circ
        omega_phi = r ** (-1.5)
        # Schwarzschild geodesic: Ω_r = Ω_φ √(1 - 6/r) for circular orbit
        ratio = np.maximum(1.0 - 6.0 / r, 0.0)
        omega_r = omega_phi * np.sqrt(ratio)
        return omega_r, omega_phi

    def build_phase_diagnostics(self, time, omega_r, omega_phi):
        """Compute full PhaseDiagnostics from frequency arrays."""
        from .result import PhaseDiagnostics

        phi_phi = self.accumulate_phase(time, omega_phi)
        phi_r = self.accumulate_phase(time, omega_r)
        phi_gw = 2.0 * phi_phi  # dominant GW phase
        return PhaseDiagnostics(
            time=time,
            phi_orbital=phi_phi,
            phi_radial=phi_r,
            phi_gw=phi_gw,
            omega_phi=omega_phi,
            omega_r=omega_r,
        )
