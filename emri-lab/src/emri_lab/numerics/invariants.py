"""Diagnostics for numerical invariants and frequency cross-checks."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class InvariantExtractor:
    """Extract conserved-quantity diagnostics from orbit solutions."""

    @staticmethod
    def hamiltonian_drift(H_arr: NDArray) -> float:
        """Max |H + 0.5| over a trajectory (should be ~0 for geodesic)."""
        return float(np.max(np.abs(H_arr + 0.5)))

    @staticmethod
    def energy_drift(E_arr: NDArray) -> float:
        """Relative energy drift |E(tf) - E(t0)| / |E(t0)|."""
        if abs(E_arr[0]) < 1e-30:
            return 0.0
        return float(abs(E_arr[-1] - E_arr[0]) / abs(E_arr[0]))

    @staticmethod
    def fft_frequency(t: NDArray, r: NDArray) -> float:
        """Dominant frequency from FFT of r(t).

        Returns the frequency (in units of 1/M) corresponding to the
        peak of the power spectrum. Useful as a cross-check against
        Omega_r computed from turning-point quadrature.
        """
        if len(t) < 4:
            return float("nan")

        dt = np.mean(np.diff(t))
        if dt <= 0:
            return float("nan")

        # Detrend to remove slow secular drift before FFT
        r_detrended = r - np.polyval(np.polyfit(t, r, 1), t)

        n = len(r_detrended)
        freqs = np.fft.rfftfreq(n, d=dt)
        power = np.abs(np.fft.rfft(r_detrended)) ** 2

        # Exclude DC component
        if len(freqs) > 1:
            peak_idx = np.argmax(power[1:]) + 1
            return float(freqs[peak_idx])
        return float("nan")
