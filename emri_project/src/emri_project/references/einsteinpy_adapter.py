"""Adapter for EinsteinPy Geodesics for reference comparisons."""

from __future__ import annotations
import numpy as np


def check_einsteinpy_available() -> bool:
    try:
        import einsteinpy  # noqa: F401
        return True
    except ImportError:
        return False


def compare_circular_orbit(r0: float) -> dict:
    """Compare our circular orbit E, L with analytical reference."""
    from emri_project.dynamics.geodesic_solver import circular_E, circular_L
    our_E = circular_E(r0)
    our_L = circular_L(r0)

    analytical_E = (r0 - 2.0) / np.sqrt(r0 * (r0 - 3.0))
    analytical_L = r0 / np.sqrt(r0 - 3.0)

    return {
        'r0': r0,
        'our_E': our_E,
        'our_L': our_L,
        'analytical_E': analytical_E,
        'analytical_L': analytical_L,
        'E_residual': abs(our_E - analytical_E),
        'L_residual': abs(our_L - analytical_L),
        'einsteinpy_available': check_einsteinpy_available(),
    }
