"""Basic waveform generator from orbital trajectory.

Uses the quadrupole approximation for gravitational wave polarizations:
  h_+ = (μ/D) * (1 + cos²ι) * [ẍ_xx - ẍ_yy] / 2
  h_× = (μ/D) * 2 cosι * ẍ_xy

For equatorial (ι=0) circular-ish motion:
  h_+(t) = -A(t) * cos(2φ(t))
  h_×(t) = -A(t) * sin(2φ(t))

where A(t) = 4 μ M / (D r(t)) * (M/r(t)) = 4 η (M²/D) * r^(-1) * (M/r)
            ≈ 4 η / (D r(t)) in units M=1.

Reference: Maggiore "Gravitational Waves" Ch. 3.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def quadrupole_amplitude(r: NDArray, eta: float, distance: float) -> NDArray:
    """GW amplitude from quadrupole formula.

    A(t) = 4 η / (D * r(t)) in geometrized units.
    """
    return 4.0 * eta / (distance * r)


def generate_waveform_basic(
    t: NDArray,
    r: NDArray,
    phi: NDArray,
    eta: float,
    distance: float = 1.0,
    iota: float = 0.0,
) -> tuple[NDArray, NDArray]:
    """Generate h_+(t) and h_×(t) from trajectory.

    Parameters
    ----------
    t : coordinate time array
    r : radial coordinate array
    phi : azimuthal angle array
    eta : mass ratio μ/M
    distance : luminosity distance in units of M
    iota : inclination angle (0 = face-on)

    Returns
    -------
    h_plus, h_cross : gravitational wave polarizations
    """
    A = quadrupole_amplitude(r, eta, distance)
    cos_iota = np.cos(iota)

    h_plus  = -A * (1.0 + cos_iota**2) / 2.0 * np.cos(2.0 * phi)
    h_cross = -A * cos_iota * np.sin(2.0 * phi)

    return h_plus, h_cross


def accumulated_phase(phi: NDArray) -> NDArray:
    """Total accumulated GW phase Φ_GW = 2φ(t)."""
    return 2.0 * phi


def amplitude_envelope(h_plus: NDArray, h_cross: NDArray) -> NDArray:
    """Amplitude envelope A(t) = sqrt(h_+² + h_×²)."""
    return np.sqrt(h_plus**2 + h_cross**2)
