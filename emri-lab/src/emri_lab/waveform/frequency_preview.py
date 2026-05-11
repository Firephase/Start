import numpy as np
from .result import SpectrumDiagnostics
from .mode_manager import HarmonicMode


class FrequencyDomainPreview:
    """FFT-based spectral analysis of time-domain waveform."""

    def compute_spectrum(
        self,
        time: np.ndarray,
        h_plus: np.ndarray,
        h_cross: np.ndarray,
        modes: list[HarmonicMode],
        omega_phi_mean: float,
        omega_r_mean: float,
    ) -> SpectrumDiagnostics:
        """Compute FFT power spectrum and label peaks with mode indices."""
        dt = float(np.mean(np.diff(time)))
        n = len(time)

        freqs = np.fft.rfftfreq(n, d=dt)

        # Hanning window to reduce spectral leakage
        window = np.hanning(n)
        fft_plus = np.fft.rfft(h_plus * window)
        fft_cross = np.fft.rfft(h_cross * window)

        power_plus = np.abs(fft_plus) ** 2
        power_cross = np.abs(fft_cross) ** 2

        # Find peaks in combined power
        power_total = power_plus + power_cross
        n_peaks = min(10, max(1, len(freqs) // 4))
        peak_indices = self._find_peaks(power_total, n_peaks=n_peaks)
        peak_frequencies = freqs[peak_indices]

        # Label each peak with the best-matching mode (n,m)
        # f_{n,m} = (n·Ω_r + m·Ω_φ) / (2π)
        labels = []
        for f_peak in peak_frequencies:
            best_label = self._match_mode_to_frequency(
                f_peak, modes, omega_r_mean, omega_phi_mean
            )
            labels.append(best_label)

        return SpectrumDiagnostics(
            frequencies=freqs,
            power_plus=power_plus,
            power_cross=power_cross,
            peak_frequencies=peak_frequencies,
            peak_mode_labels=labels,
        )

    def _find_peaks(self, power: np.ndarray, n_peaks: int) -> np.ndarray:
        """Find top-N peaks by amplitude, excluding DC component (index 0)."""
        if len(power) <= 1:
            return np.array([], dtype=int)
        # Exclude DC (index 0) by searching indices 1..end
        search_power = power[1:]
        if len(search_power) == 0:
            return np.array([], dtype=int)
        sorted_indices = np.argsort(search_power)[::-1][:n_peaks] + 1
        # Keep only indices with nonzero power
        mask = power[sorted_indices] > 0
        return sorted_indices[mask]

    def _match_mode_to_frequency(
        self,
        f_peak: float,
        modes: list[HarmonicMode],
        omega_r: float,
        omega_phi: float,
    ) -> str:
        """Find mode (n,m) whose predicted frequency is closest to f_peak."""
        best_label = "?"
        best_diff = float("inf")
        for mode in modes:
            f_mode = (mode.n * omega_r + mode.m * omega_phi) / (2 * np.pi)
            diff = abs(f_mode - f_peak)
            if diff < best_diff:
                best_diff = diff
                best_label = f"({mode.n},{mode.m})"
        return best_label
