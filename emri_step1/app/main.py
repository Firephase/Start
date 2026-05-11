"""
EMRI Step 1 — Streamlit Research Interface
Schwarzschild Geodesic Simulator (G = c = M = 1)
"""

from __future__ import annotations

import io
import yaml
import numpy as np
import pandas as pd
import streamlit as st

# Page config must be first
st.set_page_config(
    page_title="EMRI Step 1 — Schwarzschild Geodesics",
    page_icon="🌑",
    layout="wide",
)

# ── Lazy imports (heavy) ──────────────────────────────────────────────
@st.cache_resource(show_spinner="Deriving Hamiltonian equations (SymPy)…")
def get_hamiltonian():
    from emri_step1.physics.hamiltonian import SchwarzschildHamiltonian
    return SchwarzschildHamiltonian()


@st.cache_resource
def get_solver():
    from emri_step1.physics.geodesic import GeodesicSolver
    return GeodesicSolver(get_hamiltonian())


# ── Title ─────────────────────────────────────────────────────────────
st.title("🌑 EMRI Step 1 — Schwarzschild Geodesic Simulator")
st.caption("Test-particle motion in Schwarzschild spacetime · G = c = M = 1 · Equatorial plane")

# ═════════════════════════════════════════════════════════════════════
# SECTION A — Physics Setup (informational)
# ═════════════════════════════════════════════════════════════════════
with st.expander("A · Physics Setup", expanded=False):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
| Parameter | Value |
|-----------|-------|
| Spacetime | Schwarzschild |
| Motion type | Timelike geodesic |
| Units | G = c = M = 1 |
| Plane | Equatorial (θ = π/2) |
| Metric | ds² = −f dt² + f⁻¹ dr² + r² dφ² |
| f(r) | 1 − 2/r |
""")
    with col2:
        st.markdown(r"""
**Superhamiltonian:**

$$\mathcal{H} = \tfrac{1}{2}\!\left(-\frac{p_t^2}{f} + f\,p_r^2 + \frac{p_\phi^2}{r^2}\right) = -\tfrac{1}{2}$$

**Conserved quantities:** $E = -p_t$, $L = p_\phi$

**Effective potential:**

$$V_{\rm eff}(r;L) = \left(1-\frac{2}{r}\right)\!\left(1+\frac{L^2}{r^2}\right)$$
""")

# Show symbolic equations
with st.expander("Symbolic equations of motion (SymPy)", expanded=False):
    ham = get_hamiltonian()
    latex = ham.latex_summary()
    st.latex(r"\dot{t} = " + latex["dt_dtau"])
    st.latex(r"\dot{r} = " + latex["dr_dtau"])
    st.latex(r"\dot{\phi} = " + latex["dphi_dtau"])
    st.latex(r"\dot{p}_r = " + latex["dpr_dtau"])

# ═════════════════════════════════════════════════════════════════════
# SECTION B — Orbit Parametrization
# ═════════════════════════════════════════════════════════════════════
st.header("B · Orbit Parametrization")

orbit_mode = st.radio(
    "Orbit specification mode",
    ["Circular orbit by radius", "Direct (E, L)", "Turning points (r_peri, r_apo)", "Semi-latus rectum (p, e)"],
    horizontal=True,
)

from emri_step1.physics.circular import CircularOrbitAnalyzer
from emri_step1.physics.potential import EffectivePotential

E_val = L_val = r_start = pr0 = None
orbit_warning: str | None = None

if orbit_mode == "Circular orbit by radius":
    col1, col2 = st.columns([1, 2])
    with col1:
        r0 = st.number_input("r₀ (M)", min_value=3.01, max_value=200.0, value=10.0, step=0.5)
    with col2:
        if r0 <= 3.0:
            st.error("r₀ must be > 3 (photon sphere at r=3).")
        else:
            try:
                info = CircularOrbitAnalyzer().analyze(r0)
                E_val, L_val = info.E, info.L
                r_start, pr0 = r0, 0.0
                st.markdown(f"""
| Quantity | Value |
|----------|-------|
| E | `{E_val:.8f}` |
| L | `{L_val:.8f}` |
| Stable | {'✅ Yes' if info.is_stable else '⚠️ No (unstable)'} |
| ISCO | {'Yes r=6' if info.is_isco else 'No'} |
| Ω (dφ/dt) | `{info.omega:.6f}` |
| T_φ coord | `{info.T_phi:.4f} M` |
| T_φ proper | `{info.T_tau:.4f} M` |
""")
                if not info.is_stable:
                    orbit_warning = f"⚠️ r₀={r0} < 6 (ISCO): this circular orbit is **unstable** and will spiral away under any perturbation."
            except ValueError as e:
                st.error(str(e))

elif orbit_mode == "Direct (E, L)":
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        E_val = st.number_input("E (energy)", min_value=0.001, max_value=5.0, value=0.968, step=0.001, format="%.4f")
    with col2:
        L_val = st.number_input("L (ang. momentum)", min_value=0.001, max_value=30.0, value=3.46, step=0.01, format="%.4f")
    with col3:
        r_start = st.number_input("r_start (M)", min_value=2.01, max_value=500.0, value=10.0, step=0.5)
    with col4:
        pr0 = st.number_input("p_r initial", min_value=-5.0, max_value=5.0, value=0.0, step=0.001, format="%.4f")

    # Check turning points
    try:
        veff = EffectivePotential(L_val)
        tp = veff.find_turning_points(E_val)
        if tp.allowed_region_exists:
            st.info(tp.message)
        else:
            orbit_warning = f"⚠️ {tp.message}"
    except Exception:
        pass

elif orbit_mode == "Turning points (r_peri, r_apo)":
    col1, col2 = st.columns(2)
    with col1:
        r_peri = st.number_input("r_peri (periastron)", min_value=2.01, max_value=500.0, value=6.0, step=0.5)
    with col2:
        r_apo = st.number_input("r_apo (apastron)", min_value=2.01, max_value=1000.0, value=20.0, step=0.5)

    if r_peri >= r_apo:
        st.error("r_peri must be < r_apo")
    elif r_peri <= 2.0:
        st.error("r_peri must be > 2 (outside horizon)")
    else:
        try:
            E_val, L_val = CircularOrbitAnalyzer.turning_points_to_EL(r_peri, r_apo)
            r_start, pr0 = r_apo, 0.0
            st.success(f"Computed: E = {E_val:.8f},  L = {L_val:.8f}")
        except ValueError as e:
            orbit_warning = str(e)
            st.error(str(e))

elif orbit_mode == "Semi-latus rectum (p, e)":
    col1, col2 = st.columns(2)
    with col1:
        p_param = st.number_input("p (semi-latus rectum)", min_value=3.01, max_value=200.0, value=10.0, step=0.5)
    with col2:
        e_param = st.number_input("e (eccentricity)", min_value=0.0, max_value=0.999, value=0.3, step=0.01)

    try:
        r_peri_p, r_apo_p = CircularOrbitAnalyzer.pe_to_turning_points(p_param, e_param)
        E_val, L_val = CircularOrbitAnalyzer.turning_points_to_EL(r_peri_p, r_apo_p)
        r_start, pr0 = r_apo_p, 0.0
        st.success(f"r_peri={r_peri_p:.4f}, r_apo={r_apo_p:.4f} → E={E_val:.8f}, L={L_val:.8f}")
    except ValueError as e:
        orbit_warning = str(e)
        st.error(str(e))

if orbit_warning:
    st.warning(orbit_warning)

# ═════════════════════════════════════════════════════════════════════
# SECTION C — Solver Setup
# ═════════════════════════════════════════════════════════════════════
st.header("C · Numerical Solver Setup")

col1, col2, col3 = st.columns(3)
with col1:
    integrator = st.selectbox("Integrator", ["DOP853", "Radau", "RK45", "LSODA"], index=0)
    tau_max = st.number_input("τ_max (proper time / M)", min_value=10.0, max_value=1e6, value=2000.0, step=100.0)
with col2:
    rtol = st.select_slider("rtol", options=[1e-6, 1e-8, 1e-10, 1e-12], value=1e-10)
    atol = st.select_slider("atol", options=[1e-8, 1e-10, 1e-12, 1e-14], value=1e-12)
with col3:
    max_step = st.number_input("Max step size", min_value=0.01, max_value=10.0, value=1.0, step=0.1)
    n_output = st.number_input("Output points", min_value=500, max_value=100000, value=10000, step=500)

# ═════════════════════════════════════════════════════════════════════
# SECTION D — Run Controls
# ═════════════════════════════════════════════════════════════════════
st.header("D · Run Controls")

col_btn1, col_btn2, col_btn3 = st.columns(3)

run_pressed = col_btn1.button("▶ Run Simulation", type="primary", use_container_width=True)
reset_pressed = col_btn2.button("↺ Reset Parameters", use_container_width=True)
export_cfg_pressed = col_btn3.button("⬇ Export Config", use_container_width=True)

if reset_pressed:
    st.rerun()

if export_cfg_pressed and E_val is not None:
    from emri_step1.models.parameters import SimulationConfig, OrbitConfig, SolverConfig, OrbitMode
    cfg_export = SimulationConfig(
        name="emri_export",
        orbit=OrbitConfig(mode=OrbitMode.el_direct, E=E_val, L=L_val, r_start=r_start, pr0=pr0),
        solver=SolverConfig(integrator=integrator, tau_max=tau_max, rtol=rtol, atol=atol,
                            max_step=max_step, n_output=int(n_output)),
    )
    yaml_str = yaml.dump(cfg_export.to_yaml_dict(), default_flow_style=False)
    st.download_button("Download config YAML", yaml_str, file_name="emri_config.yaml", mime="text/yaml")

# ═════════════════════════════════════════════════════════════════════
# RUN
# ═════════════════════════════════════════════════════════════════════
if run_pressed:
    if E_val is None or L_val is None:
        st.error("Please specify a valid orbit configuration before running.")
        st.stop()

    from emri_step1.models.parameters import SolverConfig
    from emri_step1.physics.geodesic import GeodesicSolver

    solver = get_solver()
    scfg = SolverConfig(
        integrator=integrator,
        tau_max=float(tau_max),
        rtol=float(rtol),
        atol=float(atol),
        max_step=float(max_step),
        n_output=int(n_output),
    )
    y0 = solver.initial_conditions(float(r_start), float(pr0 if pr0 else 0.0), E_val, L_val, float(pr0 if pr0 else 0.0))
    # Fix: correct arg order  initial_conditions(r0, phi0, E, L, pr0)
    y0 = [0.0, float(r_start), 0.0, float(pr0 if pr0 else 0.0)]

    with st.spinner("Integrating geodesic equations…"):
        result = solver.run(E_val, L_val, y0, scfg)

    st.session_state["result"] = result
    st.session_state["E_val"] = E_val
    st.session_state["L_val"] = L_val

# ═════════════════════════════════════════════════════════════════════
# RESULTS
# ═════════════════════════════════════════════════════════════════════
if "result" in st.session_state:
    result = st.session_state["result"]
    E_show = st.session_state["E_val"]
    L_show = st.session_state["L_val"]

    from emri_step1.physics.visualization import (
        plot_effective_potential,
        plot_trajectory_cartesian,
        plot_r_tau,
        plot_phi_tau,
        plot_hamiltonian_drift,
    )

    # ── Section E: Diagnostics ────────────────────────────────────────
    st.header("E · Diagnostics")

    if result.is_plunge:
        st.error("⚠️ PLUNGE detected: r_min ≤ 2.05 — the particle crossed the horizon.")
    elif not result.solver_success:
        st.warning(f"Solver did not fully converge: {result.solver_message}")
    else:
        st.success(f"Integration successful · {result.solver_message}")

    T_r = result.estimated_radial_period
    diag_data = {
        "E": f"{E_show:.8f}",
        "L": f"{L_show:.8f}",
        "H max drift |ΔH|": f"{result.H_max_drift:.2e}",
        "r_min / M": f"{result.r_min:.6f}",
        "r_max / M": f"{result.r_max:.6f}",
        "Est. radial period τ_r": f"{T_r:.4f}" if T_r else "N/A",
        "N output points": str(result.n_steps),
        "Wall time (s)": f"{result.wall_time:.3f}",
        "Plunge": "Yes ⚠️" if result.is_plunge else "No",
    }
    st.table(pd.DataFrame({"Quantity": diag_data.keys(), "Value": diag_data.values()}))

    # ── Section F: Plots ──────────────────────────────────────────────
    st.header("F · Plots")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Effective Potential", "Orbit (x-y)", "r(τ) & φ(τ)", "Hamiltonian Drift", "Phase Space"]
    )

    with tab1:
        r_plot_max = min(result.r_max * 1.5, 60.0)
        fig_veff = plot_effective_potential(result, r_range=(2.1, r_plot_max))
        st.plotly_chart(fig_veff, use_container_width=True)

    with tab2:
        fig_xy = plot_trajectory_cartesian(result)
        st.plotly_chart(fig_xy, use_container_width=True)

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(plot_r_tau(result), use_container_width=True)
        with c2:
            st.plotly_chart(plot_phi_tau(result), use_container_width=True)

    with tab4:
        st.plotly_chart(plot_hamiltonian_drift(result), use_container_width=True)
        max_drift = result.H_max_drift
        if max_drift > 1e-6:
            st.warning(f"Large Hamiltonian drift: {max_drift:.2e}. Consider tighter tolerances or smaller max_step.")
        else:
            st.success(f"Hamiltonian conserved to {max_drift:.2e}.")

    with tab5:
        import plotly.graph_objects as go
        fig_ps = go.Figure()
        fig_ps.add_trace(go.Scatter(
            x=result.r, y=result.p_r, mode="lines",
            line=dict(color="darkviolet", width=1),
        ))
        fig_ps.update_layout(
            title="Phase space: r vs p_r",
            xaxis_title="r / M",
            yaxis_title="p_r",
            height=400,
        )
        st.plotly_chart(fig_ps, use_container_width=True)

    # ── Section G: Export ─────────────────────────────────────────────
    st.header("G · Output Artifacts")

    col_dl1, col_dl2, col_dl3 = st.columns(3)

    with col_dl1:
        df = result.to_dataframe()
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        st.download_button(
            "⬇ Download trajectory CSV",
            csv_buf.getvalue(),
            file_name="geodesic_trajectory.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_dl2:
        from emri_step1.models.parameters import SimulationConfig, OrbitConfig, SolverConfig, OrbitMode
        cfg_out = SimulationConfig(
            name="emri_result",
            orbit=OrbitConfig(mode=OrbitMode.el_direct, E=E_show, L=L_show,
                              r_start=float(result.r[0]), pr0=float(result.p_r[0])),
            solver=SolverConfig(integrator=integrator, tau_max=float(tau_max),
                                rtol=float(rtol), atol=float(atol),
                                max_step=float(max_step), n_output=int(n_output)),
        )
        yaml_str = yaml.dump(cfg_out.to_yaml_dict(), default_flow_style=False)
        st.download_button(
            "⬇ Download config YAML",
            yaml_str,
            file_name="emri_config.yaml",
            mime="text/yaml",
            use_container_width=True,
        )

    with col_dl3:
        T_r_str = f"{T_r:.4f} M" if T_r else "N/A"
        summary_md = f"""# EMRI Step 1 — Simulation Summary

**Spacetime:** Schwarzschild (G=c=M=1, equatorial plane)

## Orbit Parameters
| Parameter | Value |
|-----------|-------|
| E | {E_show:.8f} |
| L | {L_show:.8f} |
| r_min | {result.r_min:.6f} M |
| r_max | {result.r_max:.6f} M |
| Est. radial period | {T_r_str} |
| Plunge | {'Yes' if result.is_plunge else 'No'} |

## Solver
| Parameter | Value |
|-----------|-------|
| Integrator | {integrator} |
| τ_max | {tau_max} M |
| rtol | {rtol} |
| atol | {atol} |
| N points | {result.n_steps} |
| H max drift | {result.H_max_drift:.2e} |
| Wall time | {result.wall_time:.3f} s |
"""
        st.download_button(
            "⬇ Download summary Markdown",
            summary_md,
            file_name="emri_summary.md",
            mime="text/markdown",
            use_container_width=True,
        )
