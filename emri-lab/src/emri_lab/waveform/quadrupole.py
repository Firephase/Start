"""Quadrupole waveform generation for EMRI systems.

Computes the leading-order quadrupole gravitational waveform polarizations
h_+ and h_x from a trajectory (r(t), φ(t)).

All quantities in geometrized units G = c = M = 1.
"""

import numpy as np


def h_plus(t, r_arr, phi_arr, eta, distance=1.0, iota=0.0):
    """Compute h_+ polarization from trajectory.

    Parameters
    ----------
    t : array-like
        Time array (geometrized units).
    r_arr : array-like
        Instantaneous orbital radius r(t).
    phi_arr : array-like
        Instantaneous azimuthal angle φ(t).
    eta : float
        Mass ratio μ/M.
    distance : float
        Observer luminosity distance (geometrized units), default 1.
    iota : float
        Inclination angle of orbit to line of sight (radians), default 0.

    Returns
    -------
    numpy.ndarray
        h_+(t) strain.
    """
    A = 4.0 * eta / distance
    r = r_arr  # instantaneous radius
    return -A * (1.0 + np.cos(iota) ** 2) / 2.0 * np.cos(2.0 * phi_arr) / r


def h_cross(t, r_arr, phi_arr, eta, distance=1.0, iota=0.0):
    """Compute h_x polarization from trajectory.

    Parameters
    ----------
    t : array-like
        Time array (geometrized units).
    r_arr : array-like
        Instantaneous orbital radius r(t).
    phi_arr : array-like
        Instantaneous azimuthal angle φ(t).
    eta : float
        Mass ratio μ/M.
    distance : float
        Observer luminosity distance (geometrized units), default 1.
    iota : float
        Inclination angle of orbit to line of sight (radians), default 0.

    Returns
    -------
    numpy.ndarray
        h_x(t) strain.
    """
    A = 4.0 * eta / distance
    r = r_arr
    return -A * np.cos(iota) * np.sin(2.0 * phi_arr) / r


def generate_waveform(t, r_arr, phi_arr, eta, distance=1.0, iota=0.0):
    """Generate (h_plus, h_cross) waveform polarizations.

    Parameters
    ----------
    t : array-like
        Time array (geometrized units).
    r_arr : array-like
        Instantaneous orbital radius r(t).
    phi_arr : array-like
        Instantaneous azimuthal angle φ(t).
    eta : float
        Mass ratio μ/M.
    distance : float
        Observer luminosity distance (geometrized units), default 1.
    iota : float
        Inclination angle of orbit to line of sight (radians), default 0.

    Returns
    -------
    tuple[numpy.ndarray, numpy.ndarray]
        (h_plus, h_cross) waveform polarizations.
    """
    hp = h_plus(t, r_arr, phi_arr, eta, distance, iota)
    hc = h_cross(t, r_arr, phi_arr, eta, distance, iota)
    return hp, hc
