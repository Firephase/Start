"""Diagnostic plots for geodesic orbits."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from emri_project.dynamics.geodesic_solver import OrbitSolution, effective_potential


def plot_effective_potential(
    L: float,
    r_range: tuple[float, float] = (2.5, 30.0),
    E: float | None = None,
    n_points: int = 500,
) -> Figure:
    """Plot V_eff(r) = f(r)*(1 + L²/r²) and optional E² level."""
    r = np.linspace(r_range[0], r_range[1], n_points)
    Veff = effective_potential(r, E or 1.0, L)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(r, Veff, 'b-', lw=2, label=r'$V_{\rm eff}(r)$')
    if E is not None:
        ax.axhline(E**2, color='r', ls='--', label=f'$E^2 = {E**2:.4f}$')
    ax.axvline(6.0, color='k', ls=':', alpha=0.5, label='ISCO')
    ax.axvline(3.0, color='gray', ls=':', alpha=0.5, label='Photon sphere')
    ax.set_xlabel(r'$r/M$', fontsize=13)
    ax.set_ylabel(r'$V_{\rm eff}$', fontsize=13)
    ax.set_title(f'Effective potential, $L={L:.2f}$', fontsize=13)
    ax.legend()
    ax.set_ylim(0, min(2.0, 1.5 * np.max(Veff[r > 3])))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_orbit_trajectory(sol: OrbitSolution) -> Figure:
    """Four-panel plot: r(τ), φ(τ), r(φ), xy-trajectory."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    axes[0, 0].plot(sol.tau, sol.r, 'b-', lw=0.8)
    axes[0, 0].set_xlabel(r'$\tau/M$')
    axes[0, 0].set_ylabel(r'$r/M$')
    axes[0, 0].set_title(r'$r(\tau)$')
    axes[0, 0].grid(True, alpha=0.3)

    axes[0, 1].plot(sol.tau, sol.phi, 'g-', lw=0.8)
    axes[0, 1].set_xlabel(r'$\tau/M$')
    axes[0, 1].set_ylabel(r'$\phi$ [rad]')
    axes[0, 1].set_title(r'$\phi(\tau)$')
    axes[0, 1].grid(True, alpha=0.3)

    axes[1, 0].plot(sol.phi, sol.r, 'r-', lw=0.8, alpha=0.7)
    axes[1, 0].set_xlabel(r'$\phi$ [rad]')
    axes[1, 0].set_ylabel(r'$r/M$')
    axes[1, 0].set_title(r'$r(\phi)$')
    axes[1, 0].grid(True, alpha=0.3)

    axes[1, 1].plot(sol.x, sol.y, 'k-', lw=0.5, alpha=0.6)
    circle = plt.Circle((0, 0), 2.0, color='k', fill=True, zorder=5, label='Horizon')
    axes[1, 1].add_patch(circle)
    axes[1, 1].set_aspect('equal')
    axes[1, 1].set_xlabel(r'$x/M$')
    axes[1, 1].set_ylabel(r'$y/M$')
    axes[1, 1].set_title(r'$(x, y)$ trajectory')
    axes[1, 1].legend()
    axes[1, 1].grid(True, alpha=0.3)

    fig.suptitle(f'Geodesic orbit: $E={sol.E:.4f}$, $L={sol.L:.4f}$', fontsize=14)
    fig.tight_layout()
    return fig


def plot_hamiltonian_drift(sol: OrbitSolution) -> Figure:
    """Plot H(τ) + 1/2 (should stay near 0)."""
    drift = sol.hamiltonian_drift()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.semilogy(sol.tau, np.abs(drift), 'r-', lw=0.8)
    ax.set_xlabel(r'$\tau/M$')
    ax.set_ylabel(r'$|H + 1/2|$')
    ax.set_title('Hamiltonian constraint drift')
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig
