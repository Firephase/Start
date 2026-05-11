"""Adapter for FastEMRIWaveforms (FEW) for reference waveform comparisons.

Reference: Katz et al. (2021), arXiv:2104.04582
"""

from __future__ import annotations
import numpy as np


def check_few_available() -> bool:
    try:
        import few  # noqa: F401
        return True
    except ImportError:
        return False


def few_waveform_comparison_stub(
    M: float, mu: float, a: float, p0: float, e0: float, T: float, dt: float,
) -> dict:
    """Placeholder for FEW waveform comparison."""
    if not check_few_available():
        return {'status': 'FEW not installed', 'install_hint': 'pip install fastemriwaveforms'}
    try:
        from few.waveform import GeneralCircularEccentricEquatorialFlux
        wave_gen = GeneralCircularEccentricEquatorialFlux()
        h = wave_gen(M, mu, a, p0, e0, 0.0, T=T, dt=dt)
        return {'status': 'ok', 'h_plus': np.real(h), 'h_cross': np.imag(h)}
    except Exception as exc:
        return {'status': f'error: {exc}'}
