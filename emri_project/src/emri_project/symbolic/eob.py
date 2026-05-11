"""Symbolic derivation of the EOB Hamiltonian for EMRI.

EOB maps the two-body problem onto an effective particle in a deformed
Schwarzschild geometry. For EMRI (η = μ/M → 0):
  H_EOB → H_geodesic (test-particle limit)

EOB potential A(r): encodes PN + self-force corrections.
  A(r) = 1 - 2/r + η * a_1SF(r) + O(η²)

For η=0: A(r) = f(r) = 1 - 2/r  (exact Schwarzschild)
D(r) = 1/A(r) in the simplest EOB gauge.

H_eff = sqrt(A(r) * (1 + p_φ²/r² + p_r²/D(r)))
H_EOB = (1/η) * sqrt(1 + 2η*(H_eff - 1)) - 1/η
"""

import sympy as sp


def eob_potential_A(r: sp.Expr, eta: sp.Expr, order: int = 0) -> sp.Expr:
    """EOB A-potential.

    order=0: pure Schwarzschild (EMRI limit η→0)
    order=1: includes 1GSF correction (placeholder)
    """
    A0 = 1 - 2 / r
    if order == 0:
        return A0
    # 1GSF correction placeholder: a_1SF(r) from Akcay et al.
    # Here we use a symbolic placeholder
    a1sf = sp.Symbol('a_1SF')
    return A0 + eta * a1sf


def eob_potential_D(r: sp.Expr, eta: sp.Expr, A: sp.Expr) -> sp.Expr:
    """EOB D-potential (Padé-resummed in general; here simplified)."""
    return 1 / A


def eob_effective_hamiltonian(
    r: sp.Expr,
    pr: sp.Expr,
    pphi: sp.Expr,
    eta: sp.Expr,
    order: int = 0
) -> sp.Expr:
    """H_eff = sqrt(A*(1 + p_φ²/r² + p_r²/D))."""
    A = eob_potential_A(r, eta, order)
    D = eob_potential_D(r, eta, A)
    return sp.sqrt(A * (1 + pphi**2 / r**2 + pr**2 / D))


def eob_real_hamiltonian(
    r: sp.Expr,
    pr: sp.Expr,
    pphi: sp.Expr,
    eta: sp.Expr,
    order: int = 0
) -> sp.Expr:
    """H_EOB = (1/η)*sqrt(1 + 2η*(H_eff - 1)) - 1/η.

    In the limit η→0: H_EOB → H_eff - 1 = H_geodesic - 1
    """
    H_eff = eob_effective_hamiltonian(r, pr, pphi, eta, order)
    return (1 / eta) * sp.sqrt(1 + 2 * eta * (H_eff - 1)) - 1 / eta


def eob_circular_EL(r: sp.Expr, eta: sp.Expr = sp.Integer(0)) -> tuple[sp.Expr, sp.Expr]:
    """Circular orbit E and L from EOB Hamiltonian (η=0 limit = geodesic)."""
    pr = sp.Integer(0)
    pphi = sp.Symbol('pphi', positive=True)

    if eta == 0:
        # Geodesic limit: use Schwarzschild expressions
        A = eob_potential_A(r, eta, 0)
        f = A
        L_sq = r**3 / (r - 3)
        E_sq = (r - 2)**2 / (r * (r - 3))
        return sp.sqrt(sp.simplify(E_sq)), sp.sqrt(sp.simplify(L_sq))

    # General case: solve ∂H_EOB/∂r = 0 for L(r)
    H = eob_real_hamiltonian(r, pr, pphi, eta)
    dHdr = sp.diff(H, r)
    L_sq_sol = sp.solve(dHdr, pphi**2)
    if L_sq_sol:
        L_c = sp.sqrt(sp.simplify(L_sq_sol[0]))
        E_c = sp.simplify(H.subs(pphi, L_c))
        return E_c, L_c
    return sp.nan, sp.nan
