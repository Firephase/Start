"""
Lightweight EMRI physics core — pure Python + numpy only (no scipy).
Designed to run on Android without heavy dependencies.
All quantities in geometrized units: G = c = M = 1.
"""

import math
import numpy as np


# ---------------------------------------------------------------------------
# Orbital helpers
# ---------------------------------------------------------------------------

def separatrix(e: float) -> float:
    return 6.0 + 2.0 * e


def is_plunging(p: float, e: float) -> bool:
    return p <= separatrix(e)


def pe_to_EL(p: float, e: float):
    """Schwarzschild energy and angular momentum from (p, e)."""
    r_p = p / (1.0 + e)
    r_a = p / (1.0 - e)

    def veff_sq(r):
        return (1.0 - 2.0 / r) * (1.0 + 0.0 / r**2)  # placeholder, solved below

    # Exact analytic solution for Schwarzschild
    num_E = (p - 2.0 - 2.0 * e) * (p - 2.0 + 2.0 * e)
    den_E = p * (p - 3.0 - e**2)
    if den_E <= 0:
        return None, None
    E = math.sqrt(num_E / den_E)

    num_L = p**2
    den_L = p - 3.0 - e**2
    if den_L <= 0:
        return None, None
    L = math.sqrt(num_L / den_L)

    return E, L


def omega_phi(p: float, e: float = 0.0) -> float:
    """Approximate mean orbital frequency in the (p, e) parametrisation."""
    r_circ = p / (1.0 + e**2 / 2.0)  # rough mean radius
    r_circ = max(r_circ, 6.01)
    return r_circ ** (-1.5)


def omega_r_from_circ(r: float) -> float:
    r = max(r, 6.01)
    ophi = r ** (-1.5)
    ratio = max(1.0 - 6.0 / r, 0.0)
    return ophi * math.sqrt(ratio)


# ---------------------------------------------------------------------------
# Flux models (2.5 PN Peters–Mathews)
# ---------------------------------------------------------------------------

def _enhancement_f(e: float) -> float:
    """f(e) Peters eccentricity enhancement factor for dE/dt."""
    e2 = e * e
    return (1.0 + (73.0 / 24.0) * e2 + (37.0 / 96.0) * e2 * e2) / (1.0 - e2) ** 3.5


def _enhancement_g(e: float) -> float:
    """g(e) Peters enhancement factor for dL/dt."""
    e2 = e * e
    return (1.0 + (7.0 / 8.0) * e2) / (1.0 - e2) ** 2.0


def flux_E_baseline(p: float, e: float) -> float:
    """Energy flux dE/dt / eta  (Peters–Mathews 2.5PN)."""
    r_circ = p / max(1.0 - e**2, 1e-10)
    r_circ = max(r_circ, 6.01)
    base = (32.0 / 5.0) * r_circ ** (-5.0)
    return base * _enhancement_f(e)


def flux_L_baseline(p: float, e: float) -> float:
    """Angular-momentum flux dL/dt / eta  (Peters–Mathews 2.5PN)."""
    r_circ = p / max(1.0 - e**2, 1e-10)
    r_circ = max(r_circ, 6.01)
    E, L = pe_to_EL(p, e)
    if E is None or L < 1e-10:
        return 0.0
    base = (32.0 / 5.0) * r_circ ** (-3.5)
    return base * _enhancement_g(e)


def flux_E_extended(p: float, e: float) -> float:
    """Extended flux with approximate horizon correction."""
    fe = flux_E_baseline(p, e)
    r_circ = max(p / max(1.0 - e**2, 1e-10), 6.01)
    horizon_corr = 1.0 + 0.5 * (6.0 / r_circ) ** 3
    return fe * horizon_corr


def flux_L_extended(p: float, e: float) -> float:
    fl = flux_L_baseline(p, e)
    r_circ = max(p / max(1.0 - e**2, 1e-10), 6.01)
    horizon_corr = 1.0 + 0.5 * (6.0 / r_circ) ** 3
    return fl * horizon_corr


FLUX_MODELS = {
    "BASELINE_PN": (flux_E_baseline, flux_L_baseline),
    "EXTENDED_TEST_MASS": (flux_E_extended, flux_L_extended),
}


# ---------------------------------------------------------------------------
# Adiabatic inspiral RK4 in (p, e) space
# ---------------------------------------------------------------------------

def _dpde_dt(p: float, e: float, eta: float, flux_E, flux_L):
    """Time derivatives of (p, e) from energy/angular-momentum balance."""
    E, L = pe_to_EL(p, e)
    if E is None or L is None or L < 1e-12:
        return 0.0, 0.0

    dE_dt = -eta * flux_E(p, e)
    dL_dt = -eta * flux_L(p, e)

    # Jacobian: (E, L) → (p, e)
    # dE/dp, dE/de, dL/dp, dL/de  (numerical finite differences)
    dp = p * 1e-5
    de = max(e * 1e-5, 1e-8)

    E_pp, _ = pe_to_EL(p + dp, e)
    E_pm, _ = pe_to_EL(p - dp, e)
    E_ep, _ = pe_to_EL(p, min(e + de, 0.999))
    E_em, _ = pe_to_EL(p, max(e - de, 0.0))

    _, L_pp = pe_to_EL(p + dp, e)
    _, L_pm = pe_to_EL(p - dp, e)
    _, L_ep = pe_to_EL(p, min(e + de, 0.999))
    _, L_em = pe_to_EL(p, max(e - de, 0.0))

    if any(x is None for x in [E_pp, E_pm, E_ep, E_em, L_pp, L_pm, L_ep, L_em]):
        return 0.0, 0.0

    dE_dp = (E_pp - E_pm) / (2 * dp)
    dE_de = (E_ep - E_em) / (2 * de)
    dL_dp = (L_pp - L_pm) / (2 * dp)
    dL_de = (L_ep - L_em) / (2 * de)

    det = dE_dp * dL_de - dE_de * dL_dp
    if abs(det) < 1e-30:
        return 0.0, 0.0

    dp_dt = (dL_de * dE_dt - dE_de * dL_dt) / det
    de_dt = (-dL_dp * dE_dt + dE_dp * dL_dt) / det

    return dp_dt, de_dt


def integrate_inspiral(
    p0: float,
    e0: float,
    eta: float = 1e-5,
    t_max: float = 5e6,
    n_points: int = 1000,
    flux_model: str = "BASELINE_PN",
) -> dict:
    """
    RK4 adiabatic inspiral. Returns dict with arrays:
    t, p, e, r_circ, E, L, omega_phi, omega_r.
    """
    flux_E, flux_L = FLUX_MODELS.get(flux_model, FLUX_MODELS["BASELINE_PN"])

    dt = t_max / n_points
    t_arr = np.empty(n_points)
    p_arr = np.empty(n_points)
    e_arr = np.empty(n_points)

    p, e = p0, e0
    t = 0.0
    n_actual = 0

    for i in range(n_points):
        t_arr[i] = t
        p_arr[i] = p
        e_arr[i] = e
        n_actual = i + 1

        if is_plunging(p, e):
            break

        # RK4
        k1p, k1e = _dpde_dt(p, e, eta, flux_E, flux_L)
        k2p, k2e = _dpde_dt(p + 0.5 * dt * k1p, e + 0.5 * dt * k1e, eta, flux_E, flux_L)
        k3p, k3e = _dpde_dt(p + 0.5 * dt * k2p, e + 0.5 * dt * k2e, eta, flux_E, flux_L)
        k4p, k4e = _dpde_dt(p + dt * k3p, e + dt * k3e, eta, flux_E, flux_L)

        p += dt * (k1p + 2 * k2p + 2 * k3p + k4p) / 6.0
        e += dt * (k1e + 2 * k2e + 2 * k3e + k4e) / 6.0
        e = max(0.0, min(e, 0.999))
        t += dt

    t_arr = t_arr[:n_actual]
    p_arr = p_arr[:n_actual]
    e_arr = e_arr[:n_actual]

    r_circ = p_arr / np.maximum(1.0 - e_arr**2, 1e-10)
    r_circ = np.maximum(r_circ, 6.01)

    E_arr = np.array([pe_to_EL(pp, ee)[0] or 0.0 for pp, ee in zip(p_arr, e_arr)])
    L_arr = np.array([pe_to_EL(pp, ee)[1] or 0.0 for pp, ee in zip(p_arr, e_arr)])

    omf = r_circ ** (-1.5)
    ratio = np.maximum(1.0 - 6.0 / r_circ, 0.0)
    omr = omf * np.sqrt(ratio)

    return {
        "t": t_arr,
        "p": p_arr,
        "e": e_arr,
        "r_circ": r_circ,
        "E": E_arr,
        "L": L_arr,
        "omega_phi": omf,
        "omega_r": omr,
        "plunged": is_plunging(p_arr[-1], e_arr[-1]),
        "n_steps": n_actual,
    }


# ---------------------------------------------------------------------------
# Waveform
# ---------------------------------------------------------------------------

def _cumtrapz(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Cumulative trapezoidal integration."""
    out = np.empty_like(y)
    out[0] = 0.0
    out[1:] = np.cumsum(0.5 * (y[:-1] + y[1:]) * np.diff(x))
    return out


def build_waveform(
    inspiral: dict,
    eta: float = 1e-5,
    distance_mpc: float = 100.0,
    modes: list = None,
    iota: float = 0.0,
) -> dict:
    """
    Build h+(t) and hx(t) from inspiral trajectory.
    modes: list of (n, m) tuples; default [(0,2), (1,2), (-1,2)].
    """
    if modes is None:
        modes = [(0, 2), (1, 2), (-1, 2), (2, 2)]

    t = inspiral["t"]
    r = inspiral["r_circ"]
    omf = inspiral["omega_phi"]
    omr = inspiral["omega_r"]

    dist_M = distance_mpc * 3.086e22 / 1.477e3  # convert Mpc → M

    phi_r = _cumtrapz(omr, t)
    phi_phi = _cumtrapz(omf, t)

    h_plus = np.zeros(len(t))
    h_cross = np.zeros(len(t))

    ci = math.cos(iota)
    si = math.sin(iota)
    fp = 0.5 * (1 + ci**2)
    fc = ci

    e = inspiral["e"]

    for n, m in modes:
        phase = n * phi_r + m * phi_phi

        # Amplitude: leading quadrupole with eccentricity factor
        A_base = 4.0 * eta / np.maximum(r * dist_M, 1e-10)
        ecc_factor = e ** abs(n) / (abs(n) + 1) if n != 0 else 1.0
        A = A_base * ecc_factor

        h_plus += fp * A * np.cos(phase)
        h_cross += fc * A * np.sin(phase)

    return {
        "t": t,
        "h_plus": h_plus,
        "h_cross": h_cross,
        "phi_r": phi_r,
        "phi_phi": phi_phi,
        "f_gw": omf / math.pi,  # dominant GW frequency
    }
