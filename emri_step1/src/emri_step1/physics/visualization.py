"""
Plotting utilities for geodesic results.
Returns Plotly figures suitable for Streamlit.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from emri_step1.physics.geodesic import GeodesicResult
from emri_step1.physics.potential import EffectivePotential


def plot_effective_potential(
    result: GeodesicResult,
    r_range: tuple[float, float] = (2.1, 30.0),
    n_pts: int = 800,
) -> go.Figure:
    """V_eff(r) with energy level and turning points marked."""
    veff = EffectivePotential(result.L)
    r_arr, v_arr = veff.plot_data(r_range, n_pts)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=r_arr, y=v_arr,
        mode="lines", name="V_eff(r)",
        line=dict(color="royalblue", width=2),
    ))
    # Energy level
    E2 = result.E**2
    fig.add_hline(
        y=E2, line_dash="dash", line_color="red",
        annotation_text=f"E² = {E2:.4f}",
        annotation_position="bottom right",
    )
    # Mark orbit range
    r_min, r_max = result.r_min, result.r_max
    if not result.is_plunge:
        for rv, label in [(r_min, "r_peri"), (r_max, "r_apo")]:
            fig.add_vline(
                x=rv, line_dash="dot", line_color="green",
                annotation_text=label, annotation_position="top",
            )
    # Horizon
    fig.add_vline(
        x=2.0, line_dash="solid", line_color="black",
        annotation_text="Horizon", annotation_position="top",
    )
    # ISCO
    fig.add_vline(
        x=6.0, line_dash="longdash", line_color="orange",
        annotation_text="ISCO r=6", annotation_position="top",
    )

    fig.update_layout(
        title="Effective Potential V_eff(r; L)",
        xaxis_title="r / M",
        yaxis_title="V_eff",
        height=400,
        legend=dict(x=0.75, y=0.95),
    )
    return fig


def plot_trajectory_cartesian(result: GeodesicResult) -> go.Figure:
    """Orbit in Cartesian (x, y) coordinates."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result.x, y=result.y_cart,
        mode="lines",
        name="Orbit",
        line=dict(color="royalblue", width=1),
    ))
    # Mark start/end
    fig.add_trace(go.Scatter(
        x=[result.x[0]], y=[result.y_cart[0]],
        mode="markers", name="Start",
        marker=dict(size=8, color="green"),
    ))
    fig.add_trace(go.Scatter(
        x=[result.x[-1]], y=[result.y_cart[-1]],
        mode="markers", name="End",
        marker=dict(size=8, color="red"),
    ))
    # Draw horizon circle
    theta = np.linspace(0, 2 * np.pi, 300)
    fig.add_trace(go.Scatter(
        x=2.0 * np.cos(theta), y=2.0 * np.sin(theta),
        mode="lines", name="Horizon (r=2)",
        line=dict(color="black", width=2, dash="solid"),
        fill="toself", fillcolor="rgba(0,0,0,0.15)",
    ))
    # ISCO circle
    fig.add_trace(go.Scatter(
        x=6.0 * np.cos(theta), y=6.0 * np.sin(theta),
        mode="lines", name="ISCO (r=6)",
        line=dict(color="orange", width=1, dash="dash"),
    ))

    fig.update_layout(
        title="Orbit in Cartesian Coordinates",
        xaxis_title="x / M",
        yaxis_title="y / M",
        yaxis_scaleanchor="x",
        height=500,
    )
    return fig


def plot_r_tau(result: GeodesicResult) -> go.Figure:
    """Radial coordinate r as a function of proper time τ."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result.tau, y=result.r,
        mode="lines", name="r(τ)",
        line=dict(color="royalblue"),
    ))
    fig.add_hline(y=6.0, line_dash="dash", line_color="orange",
                  annotation_text="ISCO r=6")
    fig.add_hline(y=2.0, line_dash="solid", line_color="black",
                  annotation_text="Horizon r=2")
    fig.update_layout(
        title="r(τ) — Radial Motion",
        xaxis_title="Proper time τ / M",
        yaxis_title="r / M",
        height=350,
    )
    return fig


def plot_phi_tau(result: GeodesicResult) -> go.Figure:
    """Azimuthal angle φ as a function of proper time τ."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result.tau, y=result.phi,
        mode="lines", name="φ(τ)",
        line=dict(color="purple"),
    ))
    fig.update_layout(
        title="φ(τ) — Azimuthal Motion",
        xaxis_title="Proper time τ / M",
        yaxis_title="φ (radians)",
        height=300,
    )
    return fig


def plot_hamiltonian_drift(result: GeodesicResult) -> go.Figure:
    """Hamiltonian constraint residual H - (-½) over proper time."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=result.tau, y=result.H_residual,
        mode="lines", name="H + ½",
        line=dict(color="crimson"),
    ))
    fig.add_hline(y=0.0, line_dash="dash", line_color="black")
    fig.update_layout(
        title="Hamiltonian Constraint Drift  H − (−½)",
        xaxis_title="Proper time τ / M",
        yaxis_title="ΔH",
        height=300,
    )
    return fig


def plot_diagnostics_panel(result: GeodesicResult) -> go.Figure:
    """Combined 2×2 diagnostics panel."""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=["r(τ)", "φ(τ)", "H constraint drift", "r vs φ (polar-like)"],
    )
    # r(τ)
    fig.add_trace(go.Scatter(x=result.tau, y=result.r, mode="lines",
                             name="r(τ)", line=dict(color="royalblue")), row=1, col=1)
    # φ(τ)
    fig.add_trace(go.Scatter(x=result.tau, y=result.phi, mode="lines",
                             name="φ(τ)", line=dict(color="purple")), row=1, col=2)
    # H drift
    fig.add_trace(go.Scatter(x=result.tau, y=result.H_residual, mode="lines",
                             name="ΔH", line=dict(color="crimson")), row=2, col=1)
    # x-y orbit
    fig.add_trace(go.Scatter(x=result.x, y=result.y_cart, mode="lines",
                             name="orbit", line=dict(color="green", width=1)), row=2, col=2)

    fig.update_layout(height=600, showlegend=True)
    return fig
