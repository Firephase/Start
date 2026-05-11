"""Tests for the symbolic Hamiltonian module."""

import numpy as np
import pytest
from emri_step1.physics.hamiltonian import SchwarzschildHamiltonian


@pytest.fixture(scope="module")
def ham():
    return SchwarzschildHamiltonian()


def test_hamiltonian_timelike_circular(ham):
    """For a circular orbit the Hamiltonian must equal -0.5."""
    from emri_step1.physics.circular import CircularOrbitAnalyzer
    r0 = 10.0
    info = CircularOrbitAnalyzer().analyze(r0)
    H = ham.hamiltonian_value(r0, 0.0, info.E, info.L)
    assert abs(H - (-0.5)) < 1e-10, f"H = {H}, expected -0.5"


def test_hamiltonian_at_apastron(ham):
    """At apastron (pr=0) H must equal -½ (i.e. E² = V_eff)."""
    from emri_step1.physics.circular import CircularOrbitAnalyzer
    from emri_step1.physics.potential import EffectivePotential
    # Use a clearly bound orbit with L > L_ISCO
    r_peri, r_apo = 8.0, 20.0
    E, L = CircularOrbitAnalyzer.turning_points_to_EL(r_peri, r_apo)
    veff = EffectivePotential(L)
    tp = veff.find_turning_points(E)
    assert tp.r_apo is not None, f"find_turning_points returned: {tp}"
    H = ham.hamiltonian_value(tp.r_apo, 0.0, E, L)
    assert abs(H - (-0.5)) < 1e-4, f"H = {H} at apastron, expected -0.5"


def test_rhs_returns_four_components(ham):
    rhs = ham.rhs(E=0.968, L=3.46)
    dy = rhs(0.0, [0.0, 10.0, 0.0, 0.0])
    assert len(dy) == 4


def test_rhs_circular_pr_zero(ham):
    """For a circular orbit with pr=0 the radial velocity ṙ must be ~0."""
    from emri_step1.physics.circular import CircularOrbitAnalyzer
    r0 = 10.0
    info = CircularOrbitAnalyzer().analyze(r0)
    rhs = ham.rhs(E=info.E, L=info.L)
    dy = rhs(0.0, [0.0, r0, 0.0, 0.0])
    dr = dy[1]
    assert abs(dr) < 1e-10, f"dr/dτ = {dr}, should be 0 for circular orbit"


def test_latex_summary_keys(ham):
    keys = ham.latex_summary()
    for k in ["f(r)", "H", "dt_dtau", "dr_dtau", "dphi_dtau", "dpr_dtau"]:
        assert k in keys
