"""Schwarzschild metric functions.

Equatorial plane (θ=π/2), geometrized units G=c=M=1.
Metric: ds² = -f dt² + f⁻¹ dr² + r² dφ²
f(r) = 1 - 2/r
"""

import numpy as np
from numpy.typing import NDArray


def lapse(r: NDArray) -> NDArray:
    """f(r) = 1 - 2/r."""
    return 1.0 - 2.0 / r


def dlapse_dr(r: NDArray) -> NDArray:
    """df/dr = 2/r²."""
    return 2.0 / r**2


def d2lapse_dr2(r: NDArray) -> NDArray:
    """d²f/dr² = -4/r³."""
    return -4.0 / r**3


def g_tt(r: NDArray) -> NDArray:
    return -lapse(r)


def g_rr(r: NDArray) -> NDArray:
    return 1.0 / lapse(r)


def g_phiphi(r: NDArray) -> NDArray:
    return r**2


def g_tt_up(r: NDArray) -> NDArray:
    """g^tt = -1/f."""
    return -1.0 / lapse(r)


def g_rr_up(r: NDArray) -> NDArray:
    """g^rr = f."""
    return lapse(r)


def g_phiphi_up(r: NDArray) -> NDArray:
    """g^φφ = 1/r²."""
    return 1.0 / r**2
