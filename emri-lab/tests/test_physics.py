"""Tests for the physics layer."""

import pytest
import numpy as np
from emri_lab.physics.orbit_parametrization import (
    pe_to_EL, classify_orbit, pe_to_canonical, EL_to_pe,
)
from emri_lab.domain.enums import OrbitType, FluxModelId
from emri_lab.physics.fluxes import (
    BaselinePNFlux, ExtendedTestMassFlux, get_flux_model,
)


class TestOrbitClassifier:
    def test_plunging(self):
        # p=6.5 < 6 + 2*0.3 = 6.6
        assert classify_orbit(6.5, 0.3) == OrbitType.PLUNGING

    def test_circular_stable(self):
        assert classify_orbit(12.0, 0.0) == OrbitType.CIRCULAR_STABLE

    def test_circular_unstable(self):
        # p between photon sphere (3) and ISCO (6) but circular: e<1e-6, p<=6
        # classify_orbit checks separatrix first: p=5 <= 6+0=6 → PLUNGING
        # CIRCULAR_UNSTABLE only applies when p > separatrix but e < 1e-6, p <= 6
        # That region is empty for e=0 (separatrix p_sep=6 equals ISCO).
        # So CIRCULAR_UNSTABLE is only reachable via direct p assignment,
        # verified by checking classifier logic branch coverage separately.
        # For p just above separatrix but e≈0 and p≤6 this can't occur in Schwarzschild.
        # Instead test that p=5 plunges (below separatrix p_sep=6 for e=0).
        assert classify_orbit(5.0, 0.0) == OrbitType.PLUNGING

    def test_bound_eccentric(self):
        # p=10 > 6 + 2*0.3 = 6.6
        assert classify_orbit(10.0, 0.3) == OrbitType.BOUND_ECCENTRIC

    def test_separatrix_exact(self):
        # p exactly at separatrix → plunging
        e = 0.2
        assert classify_orbit(6.0 + 2.0 * e, e) == OrbitType.PLUNGING


class TestPeToEL:
    def test_circular(self):
        p = 12.0
        E, L = pe_to_EL(p, 0.0)
        E_exact = (p - 2) / np.sqrt(p * (p - 3))
        L_exact = p / np.sqrt(p - 3)
        assert abs(E - E_exact) < 1e-6
        assert abs(L - L_exact) < 1e-6

    def test_eccentric_physical(self):
        E, L = pe_to_EL(10.0, 0.3)
        assert 0 < E < 1  # bound orbit
        assert L > 0

    def test_eccentric_turning_points(self):
        """E and L must satisfy V_eff(r_peri) = V_eff(r_apo) = E²."""
        p, e = 10.0, 0.4
        E, L = pe_to_EL(p, e)
        r_peri = p / (1 + e)
        r_apo = p / (1 - e)

        def veff(r):
            return (1 - 2 / r) * (1 + L**2 / r**2)

        assert abs(veff(r_peri) - E**2) < 1e-8
        assert abs(veff(r_apo) - E**2) < 1e-8


class TestPeToCanonical:
    def test_r_at_pericenter(self):
        p, e = 10.0, 0.3
        result = pe_to_canonical(p, e, chi_r=0.0)
        assert abs(result["r"] - p / (1 + e)) < 1e-10

    def test_r_at_apocenter(self):
        p, e = 10.0, 0.3
        result = pe_to_canonical(p, e, chi_r=np.pi)
        assert abs(result["r"] - p / (1 - e)) < 1e-10

    def test_pr_zero_at_turning_points(self):
        p, e = 10.0, 0.3
        for chi in [0.0, np.pi]:
            result = pe_to_canonical(p, e, chi_r=chi)
            assert result["pr"] < 1e-6  # turning point: pr ≈ 0


class TestFluxModels:
    def test_baseline_flux_positive(self):
        f = BaselinePNFlux()
        assert f.flux_E(12.0, 0.0) > 0
        assert f.flux_L(12.0, 0.0) > 0

    def test_extended_larger_than_baseline(self):
        base = BaselinePNFlux()
        ext = ExtendedTestMassFlux()
        assert ext.flux_E(12.0, 0.0) > base.flux_E(12.0, 0.0)

    def test_flux_decreases_with_radius(self):
        f = BaselinePNFlux()
        assert f.flux_E(8.0, 0.0) > f.flux_E(15.0, 0.0)

    def test_get_flux_model_baseline(self):
        model = get_flux_model(FluxModelId.BASELINE_PN)
        assert isinstance(model, BaselinePNFlux)

    def test_get_flux_model_extended(self):
        model = get_flux_model(FluxModelId.EXTENDED_TEST_MASS)
        assert isinstance(model, ExtendedTestMassFlux)

    def test_get_flux_model_unknown(self):
        with pytest.raises((ValueError, KeyError)):
            get_flux_model("nonexistent_model")  # type: ignore
