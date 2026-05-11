"""Tests for the effective potential."""

import numpy as np
import pytest
from emri_step1.physics.potential import EffectivePotential


def test_veff_at_large_r():
    """V_eff → 1 as r → ∞."""
    veff = EffectivePotential(L=3.46)
    assert abs(veff(1000.0) - 1.0) < 0.01


def test_veff_at_horizon():
    """V_eff(r=2) = 0 regardless of L."""
    for L in [2.0, 4.0, 10.0]:
        veff = EffectivePotential(L)
        assert abs(veff(2.0)) < 1e-10


def test_turning_points_near_circular():
    """
    A slightly eccentric orbit near r=10 should find turning points close to r0.
    Note: exact circular orbits have a double root (tangency) at r0, so the
    sign-change scan cannot detect r0 directly.  Use E = 1.001 * E_circ instead.
    """
    from emri_step1.physics.circular import CircularOrbitAnalyzer
    r0 = 10.0
    info = CircularOrbitAnalyzer().analyze(r0)
    veff = EffectivePotential(info.L)
    E_perturbed = info.E * 1.001   # tiny eccentricity
    tp = veff.find_turning_points(E_perturbed)
    assert tp.allowed_region_exists
    assert tp.is_bound
    # Both turning points should be near r0
    # A 0.1% energy increase shifts r_peri and r_apo by ~1.5 M; verify both bracket r0
    assert tp.r_peri < r0 < tp.r_apo


def test_turning_points_eccentric():
    """Turning points for eccentric orbit should match input."""
    from emri_step1.physics.circular import CircularOrbitAnalyzer
    r_p, r_a = 7.0, 20.0
    E, L = CircularOrbitAnalyzer.turning_points_to_EL(r_p, r_a)
    veff = EffectivePotential(L)
    tp = veff.find_turning_points(E)
    assert tp.is_bound
    assert abs(tp.r_peri - r_p) < 0.05
    assert abs(tp.r_apo - r_a) < 0.1
