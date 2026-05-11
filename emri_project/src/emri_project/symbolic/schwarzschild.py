"""Symbolic derivation of Schwarzschild geodesic equations using SymPy.

Metric: ds² = -f dt² + f⁻¹ dr² + r² dφ²,  f(r) = 1 - 2/r
Super-Hamiltonian: H = (1/2) g^{μν} p_μ p_ν
Timelike constraint: H = -1/2
Conserved: E = -p_t,  L = p_φ
"""

import sympy as sp


def build_schwarzschild_symbols() -> dict:
    """Return symbolic variables used in derivations."""
    r, tau = sp.symbols('r tau', positive=True)
    t, phi = sp.symbols('t phi', real=True)
    pt, pr, pphi = sp.symbols('p_t p_r p_phi', real=True)
    E, L = sp.symbols('E L', real=True, positive=True)
    M = sp.Integer(1)  # G=c=M=1
    return dict(r=r, tau=tau, t=t, phi=phi,
                pt=pt, pr=pr, pphi=pphi, E=E, L=L, M=M)


def lapse_function(r: sp.Expr) -> sp.Expr:
    """f(r) = 1 - 2/r in geometrized units (M=1)."""
    return 1 - sp.Rational(2, 1) / r


def build_superhamiltonian(syms: dict) -> sp.Expr:
    """H = (1/2)(- p_t²/f + f p_r² + p_φ²/r²)."""
    r, pt, pr, pphi = syms['r'], syms['pt'], syms['pr'], syms['pphi']
    f = lapse_function(r)
    H = sp.Rational(1, 2) * (-pt**2 / f + f * pr**2 + pphi**2 / r**2)
    return sp.simplify(H)


def derive_hamilton_equations(syms: dict) -> dict:
    """Derive Hamilton equations from H.

    Returns dict with symbolic expressions for:
    - dr_dtau, dphi_dtau, dt_dtau (from ∂H/∂p)
    - dpr_dtau (from -∂H/∂r)
    With substitutions E=-p_t, L=p_φ applied.
    """
    r, pt, pr, pphi = syms['r'], syms['pt'], syms['pr'], syms['pphi']
    E, L = syms['E'], syms['L']
    H = build_superhamiltonian(syms)

    # dq/dτ = ∂H/∂p
    dr_dtau = sp.diff(H, pr)
    dphi_dtau = sp.diff(H, pphi)
    dt_dtau = sp.diff(H, pt)
    # dp/dτ = -∂H/∂q
    dpr_dtau = -sp.diff(H, r)

    # Substitute conserved quantities: p_t = -E, p_φ = L
    subs = {pt: -E, pphi: L}

    return {
        'dr_dtau': sp.simplify(dr_dtau.subs(subs)),
        'dphi_dtau': sp.simplify(dphi_dtau.subs(subs)),
        'dt_dtau': sp.simplify(dt_dtau.subs(subs)),
        'dpr_dtau': sp.simplify(dpr_dtau.subs(subs)),
    }


def effective_potential(r: sp.Expr, L: sp.Expr) -> sp.Expr:
    """V_eff(r, L) from the radial equation.

    From H = -1/2 and ṙ = f*p_r:
    (ṙ)²/2 = E²/(2f) - V_eff_total
    More usefully: E² = f(r)*(1 + L²/r²) at turning points (ṙ=0)
    V_eff(r) ≡ f(r)*(1 + L²/r²)
    """
    f = lapse_function(r)
    return f * (1 + L**2 / r**2)


def circular_orbit_EL(r: sp.Expr) -> tuple[sp.Expr, sp.Expr]:
    """E(r) and L(r) for circular geodesics in Schwarzschild.

    Conditions: V_eff = E² and dV_eff/dr = 0
    Result: E = (r-2)/sqrt(r*(r-3)), L = r/sqrt(r-3)
    """
    L = sp.Symbol('L', positive=True)
    f = lapse_function(r)
    Veff = effective_potential(r, L)

    dVdr = sp.diff(Veff, r)
    L_circ_sq = sp.solve(dVdr, L**2)[0]
    L_circ = sp.sqrt(sp.simplify(L_circ_sq))
    E_circ = sp.sqrt(sp.simplify(Veff.subs(L**2, L_circ_sq)))

    return sp.simplify(E_circ), sp.simplify(L_circ)


def isco_radius() -> sp.Expr:
    """Find ISCO by d²V_eff/dr² = 0 combined with circular orbit condition."""
    r = sp.Symbol('r', positive=True)
    E_c, L_c = circular_orbit_EL(r)
    # At ISCO: dL_circ/dr = 0 (equivalently d²Veff/dr² = 0)
    dLdr = sp.diff(L_c**2, r)
    isco = sp.solve(dLdr, r)
    return isco


def print_summary() -> None:
    """Print analytical summary of Schwarzschild geodesics."""
    syms = build_schwarzschild_symbols()
    r, L = syms['r'], syms['L']

    print("=" * 60)
    print("SCHWARZSCHILD GEODESICS - ANALYTICAL SUMMARY")
    print("Units: G = c = M = 1")
    print("=" * 60)

    H = build_superhamiltonian(syms)
    print(f"\nSuper-Hamiltonian:\nH = {H}")

    eqs = derive_hamilton_equations(syms)
    print("\nHamilton equations:")
    for name, expr in eqs.items():
        print(f"  {name} = {expr}")

    Veff = effective_potential(r, L)
    print(f"\nEffective potential:\nV_eff = {Veff}")

    E_c, L_c = circular_orbit_EL(r)
    print(f"\nCircular orbits:")
    print(f"  E(r) = {E_c}")
    print(f"  L(r) = {L_c}")

    isco = isco_radius()
    print(f"\nISCO radius: r_ISCO = {isco}")


if __name__ == "__main__":
    print_summary()
