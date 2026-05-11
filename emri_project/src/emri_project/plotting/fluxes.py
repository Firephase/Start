"""Plots for radiation fluxes and adiabatic inspiral."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from emri_project.dynamics.inspiral import InspiralSolution
from emri_project.fluxes.infinity_flux import flux_E_PN_circular
from emri_project.fluxes.horizon_flux import flux_E_horizon_circular, horizon_flux_ratio


def plot_flux_vs_radius(r_range: tuple[float, float] = (6.5, 50.0)) -> Figure:
    """Plot dE/dt_inf and dE/dt_hor vs orbital radius."""
    r = np.linspace(r_range[0], r_range[1], 300)
    F_inf = np.array([flux_E_PN_circular(ri) for ri in r])
    F_hor = np.array([flux_E_horizon_circular(ri) for ri in r])
    ratio = np.array([horizon_flux_ratio(ri) for ri in r])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    ax1.semilogy(r, F_inf, 'b-', label=r'$\dot{E}_\infty$')
    ax1.semilogy(r, F_hor, 'r--', label=r'$\dot{E}_{\rm hor}$')
    ax1.set_xlabel(r'$r/M$')
    ax1.set_ylabel(r'Flux (units $\eta^2$)')
    ax1.set_title('Energy flux vs radius')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.semilogy(r, ratio, 'g-')
    ax2.set_xlabel(r'$r/M$')
    ax2.set_ylabel(r'$\dot{E}_{\rm hor}/\dot{E}_\infty$')
    ax2.set_title('Horizon flux fraction')
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def plot_inspiral_track(sol: InspiralSolution) -> Figure:
    """Plot inspiral trajectory: r(t), E(t), L(t), Ω_GW(t)."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    axes[0, 0].plot(sol.t, sol.r_circ, 'b-', lw=1.5)
    axes[0, 0].axhline(6.0, color='r', ls='--', label='ISCO')
    axes[0, 0].set_xlabel(r'$t/M$')
    axes[0, 0].set_ylabel(r'$r/M$')
    axes[0, 0].set_title('Inspiral radius')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)

    axes[0, 1].plot(sol.t, sol.E, 'g-', lw=1.5)
    axes[0, 1].set_xlabel(r'$t/M$')
    axes[0, 1].set_ylabel(r'$E$')
    axes[0, 1].set_title('Orbital energy evolution')
    axes[0, 1].grid(True, alpha=0.3)

    axes[1, 0].plot(sol.t, sol.L, 'm-', lw=1.5)
    axes[1, 0].set_xlabel(r'$t/M$')
    axes[1, 0].set_ylabel(r'$L$')
    axes[1, 0].set_title('Angular momentum evolution')
    axes[1, 0].grid(True, alpha=0.3)

    axes[1, 1].plot(sol.t, sol.frequency_gw, 'r-', lw=1.5)
    axes[1, 1].set_xlabel(r'$t/M$')
    axes[1, 1].set_ylabel(r'$f_{\rm GW} \cdot M$')
    axes[1, 1].set_title('GW frequency chirp')
    axes[1, 1].grid(True, alpha=0.3)

    fig.suptitle(f'Adiabatic inspiral ($\\eta={sol.E[0]:.4f}$)', fontsize=13)
    fig.tight_layout()
    return fig
