"""Plots for EMRI waveforms."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from emri_project.waveform.interfaces import WaveformResult


def plot_waveform(wf: WaveformResult, t_max: float | None = None) -> Figure:
    """Four-panel waveform plot: h+, h×, amplitude, GW phase."""
    t = wf.t
    mask = t <= t_max if t_max else slice(None)
    t_plot = t[mask]

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))

    axes[0, 0].plot(t_plot, wf.h_plus[mask], 'b-', lw=0.6)
    axes[0, 0].set_xlabel(r'$t/M$')
    axes[0, 0].set_ylabel(r'$h_+$')
    axes[0, 0].set_title(r'Plus polarization $h_+$')
    axes[0, 0].grid(True, alpha=0.3)

    axes[0, 1].plot(t_plot, wf.h_cross[mask], 'r-', lw=0.6)
    axes[0, 1].set_xlabel(r'$t/M$')
    axes[0, 1].set_ylabel(r'$h_\times$')
    axes[0, 1].set_title(r'Cross polarization $h_\times$')
    axes[0, 1].grid(True, alpha=0.3)

    axes[1, 0].plot(t_plot, wf.amplitude[mask], 'g-', lw=1.0)
    axes[1, 0].set_xlabel(r'$t/M$')
    axes[1, 0].set_ylabel(r'$A(t)$')
    axes[1, 0].set_title('Amplitude envelope')
    axes[1, 0].grid(True, alpha=0.3)

    axes[1, 1].plot(t_plot, wf.phase[mask], 'k-', lw=1.0)
    axes[1, 1].set_xlabel(r'$t/M$')
    axes[1, 1].set_ylabel(r'$\Phi_{\rm GW}$ [rad]')
    axes[1, 1].set_title('Accumulated GW phase')
    axes[1, 1].grid(True, alpha=0.3)

    fig.tight_layout()
    return fig


def plot_waveform_spectrum(wf: WaveformResult) -> Figure:
    """Power spectral density of h_+(t)."""
    dt = np.mean(np.diff(wf.t))
    freqs = np.fft.rfftfreq(len(wf.t), d=dt)
    psd = np.abs(np.fft.rfft(wf.h_plus))**2 * dt

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.loglog(freqs[1:], psd[1:], 'b-', lw=1.0)
    ax.set_xlabel(r'$f \cdot M$ [dimensionless]')
    ax.set_ylabel(r'PSD [$h_+^2 \cdot M$]')
    ax.set_title('GW Power Spectral Density')
    ax.grid(True, alpha=0.3, which='both')
    fig.tight_layout()
    return fig
