"""Spherical harmonic mode decomposition for EMRI waveforms.

h = sum_{ℓm} h_ℓm * Y_ℓm^(-2)(ι, φ_obs)

For equatorial circular/eccentric orbits the dominant modes are:
  ℓ=m=2: h_22(t) ~ A_22(r) * exp(2i φ(t))
  ℓ=2,m=1: subdominant
  ℓ=3,m=3: next-to-leading

Here we implement the test-particle amplitudes for the (ℓ,m) modes
using the asymptotic flux amplitudes from Black Hole Perturbation Toolkit.

For simplicity, we parametrize:
  |h_ℓm| ~ C_ℓm * (μ/D) * (M/r)^{(ℓ+1)}
with C_22 = 8*sqrt(π/5), C_21 = (i/3)*sqrt(16π/5), etc.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


# Mode amplitude coefficients (leading PN, normalized so h22 matches quadrupole)
_MODE_COEFFS: dict[tuple[int, int], complex] = {
    (2, 2): 8.0 * np.sqrt(np.pi / 5.0),
    (2, 1): 1j / 3.0 * np.sqrt(16.0 * np.pi / 5.0),
    (3, 3): -3.0 / 4.0 * np.sqrt(6.0 * np.pi / 7.0),
    (4, 4): 64.0 / 9.0 * np.sqrt(np.pi / 7.0),
}


def mode_amplitude(ell: int, m: int, r: NDArray, eta: float, distance: float) -> NDArray:
    """Leading-order amplitude for mode (ℓ, m).

    |h_ℓm| ∝ (M/r)^{ℓ+1} * η / D
    """
    coeff = abs(_MODE_COEFFS.get((ell, m), 1.0))
    return coeff * eta / distance * r**(-(ell + 1))


def mode_h22(
    t: NDArray,
    r: NDArray,
    phi: NDArray,
    eta: float,
    distance: float = 1.0,
) -> NDArray:
    """Dominant (2,2) mode: h_22(t) = A_22(r) * exp(2i φ(t))."""
    A = mode_amplitude(2, 2, r, eta, distance)
    return A * np.exp(2j * phi)


def reconstruct_hplus_hcross(
    modes: dict[tuple[int, int], NDArray],
    iota: float = 0.0,
    phi_obs: float = 0.0,
) -> tuple[NDArray, NDArray]:
    """Reconstruct h_+, h_× from mode dictionary using spin-weighted harmonics.

    h = sum h_ℓm * _{-2}Y_ℓm(ι, φ_obs)
    For dominant (2,2) + (2,-2) in face-on limit:
      h_+ - ih_× = 2 * h_22 * Y_22(ι, φ_obs)
    """
    from scipy.special import sph_harm

    h_complex = np.zeros(len(next(iter(modes.values()))), dtype=complex)
    for (ell, m), hlm in modes.items():
        Y = sph_harm(m, ell, phi_obs, iota)
        h_complex += hlm * Y

        if m > 0 and (-ell, -m) not in modes:
            Y_neg = sph_harm(-m, ell, phi_obs, iota)
            h_complex += np.conj(hlm) * (-1)**m * Y_neg

    h_plus  = np.real(h_complex)
    h_cross = -np.imag(h_complex)
    return h_plus, h_cross
