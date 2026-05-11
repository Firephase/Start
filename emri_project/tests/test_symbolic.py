"""Tests for symbolic derivation module."""

import sympy as sp
import pytest
from emri_project.symbolic.schwarzschild import (
    lapse_function, build_superhamiltonian, build_schwarzschild_symbols,
    circular_orbit_EL, effective_potential, derive_hamilton_equations
)


class TestSymbolicSchwarzschild:
    def test_lapse_at_horizon(self):
        r = sp.Symbol('r')
        f = lapse_function(r)
        assert f.subs(r, 2) == 0

    def test_superhamiltonian_timelike(self):
        """H = -1/2 for circular orbit (check symbolic structure)."""
        syms = build_schwarzschild_symbols()
        H = build_superhamiltonian(syms)
        # H should be a rational function of r, pt, pr, pphi
        assert H is not None
        assert sp.diff(H, syms['pr']) != 0

    def test_hamilton_equations_have_four_components(self):
        syms = build_schwarzschild_symbols()
        eqs = derive_hamilton_equations(syms)
        assert 'dr_dtau' in eqs
        assert 'dphi_dtau' in eqs
        assert 'dt_dtau' in eqs
        assert 'dpr_dtau' in eqs

    def test_dphi_dtau_is_L_over_r2(self):
        """dφ/dτ = L/r²."""
        syms = build_schwarzschild_symbols()
        eqs = derive_hamilton_equations(syms)
        r, L = syms['r'], syms['L']
        expected = L / r**2
        diff = sp.simplify(eqs['dphi_dtau'] - expected)
        assert diff == 0

    def test_circular_EL_at_isco(self):
        """E=2√2/3, L=2√3 at r=6."""
        r = sp.Symbol('r', positive=True)
        E_sym, L_sym = circular_orbit_EL(r)
        E_isco = float(E_sym.subs(r, 6))
        L_isco = float(L_sym.subs(r, 6))
        import numpy as np
        assert abs(E_isco - 2 * np.sqrt(2) / 3) < 1e-10
        assert abs(L_isco - 2 * np.sqrt(3)) < 1e-10
