"""Tests for circular orbit analysis."""

import numpy as np
import pytest
from emri_step1.physics.circular import CircularOrbitAnalyzer


def test_isco_at_r6():
    a = CircularOrbitAnalyzer()
    info = a.analyze(6.0)
    assert info.is_stable
    assert abs(info.E - np.sqrt(8.0 / 9.0)) < 1e-8
    assert abs(info.L - 2.0 * np.sqrt(3.0)) < 1e-8


def test_unstable_below_isco():
    a = CircularOrbitAnalyzer()
    # r=4 is between photon sphere and ISCO
    info = a.analyze(4.0)
    assert not info.is_stable


def test_circular_invalid_at_photon_sphere():
    a = CircularOrbitAnalyzer()
    with pytest.raises(ValueError):
        a.analyze(3.0)


def test_EL_formulas():
    """Check E(r) and L(r) against known values at r=10."""
    r = 10.0
    E = CircularOrbitAnalyzer.E_circular(r)
    L = CircularOrbitAnalyzer.L_circular(r)
    # Verify constraint: E² = V_eff(r; L) at pr=0
    from emri_step1.physics.potential import EffectivePotential
    veff = EffectivePotential(L)
    assert abs(E**2 - veff(r)) < 1e-12


def test_turning_points_roundtrip():
    """Convert (r_peri, r_apo) → (E, L) and check V_eff at turning points."""
    r_peri, r_apo = 7.0, 20.0
    E, L = CircularOrbitAnalyzer.turning_points_to_EL(r_peri, r_apo)
    from emri_step1.physics.potential import EffectivePotential
    veff = EffectivePotential(L)
    assert abs(E**2 - veff(r_peri)) < 1e-8
    assert abs(E**2 - veff(r_apo)) < 1e-8


def test_pe_to_turning_points():
    p, e = 10.0, 0.5
    r_p, r_a = CircularOrbitAnalyzer.pe_to_turning_points(p, e)
    assert abs(r_p - 10.0 / 1.5) < 1e-10
    assert abs(r_a - 10.0 / 0.5) < 1e-10
