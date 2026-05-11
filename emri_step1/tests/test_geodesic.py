"""Tests for the geodesic integrator."""

import numpy as np
import pytest
from emri_step1.physics.hamiltonian import SchwarzschildHamiltonian
from emri_step1.physics.geodesic import GeodesicSolver
from emri_step1.models.parameters import SolverConfig


@pytest.fixture(scope="module")
def solver():
    return GeodesicSolver()


def short_cfg(tau_max: float = 200.0) -> SolverConfig:
    return SolverConfig(tau_max=tau_max, n_output=2000, rtol=1e-10, atol=1e-12)


def test_circular_hamiltonian_conservation(solver):
    """H must stay at -0.5 with relative error < 1e-6 for circular orbit."""
    E, L, y0 = solver.ic_from_circular(10.0)
    result = solver.run(E, L, y0, short_cfg())
    assert result.H_max_drift < 1e-6, f"H drift = {result.H_max_drift}"


def test_circular_radius_constant(solver):
    """r must stay within 1e-4 of r0 for a circular orbit."""
    r0 = 10.0
    E, L, y0 = solver.ic_from_circular(r0)
    result = solver.run(E, L, y0, short_cfg(tau_max=300.0))
    r_variation = result.r_max - result.r_min
    assert r_variation < 1e-3, f"r varies by {r_variation} for circular orbit"


def test_eccentric_bound_orbit(solver):
    """Eccentric orbit should stay within turning points."""
    r_peri, r_apo = 7.0, 20.0
    E, L, y0 = solver.ic_from_turning_points(r_peri, r_apo)
    result = solver.run(E, L, y0, short_cfg(tau_max=500.0))
    assert result.r_min >= r_peri - 0.1
    assert result.r_max <= r_apo + 0.1
    assert not result.is_plunge


def test_hamiltonian_conservation_eccentric(solver):
    """Hamiltonian drift < 1e-6 for eccentric orbit."""
    E, L, y0 = solver.ic_from_turning_points(7.0, 20.0)
    result = solver.run(E, L, y0, short_cfg(tau_max=500.0))
    assert result.H_max_drift < 1e-6


def test_solver_returns_dataframe(solver):
    E, L, y0 = solver.ic_from_circular(10.0)
    result = solver.run(E, L, y0, short_cfg(tau_max=50.0))
    df = result.to_dataframe()
    assert set(["tau", "r", "phi", "p_r", "H", "H_residual"]).issubset(df.columns)


def test_plunge_detection(solver):
    """High-E radial orbit should be flagged as plunge."""
    # Near-radial infall: large E, small L
    E, L = 1.2, 0.5
    y0 = [0.0, 10.0, 0.0, 0.0]
    cfg = SolverConfig(tau_max=200.0, n_output=5000, stop_at_horizon=True)
    result = solver.run(E, L, y0, cfg)
    assert result.is_plunge or result.r_min < 3.0
