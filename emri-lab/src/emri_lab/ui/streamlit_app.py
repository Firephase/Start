"""EMRI Waveform Console — полный интерфейс для анализа гравволн."""
from __future__ import annotations

import io
import json
import traceback
import tempfile
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

from emri_lab.domain.enums import AppState, FluxModelId, OrbitType
from emri_lab.domain.models import OrbitParams, PhysicsConfig, InspiralResult
from emri_lab.domain.states import UISessionState
from emri_lab.physics.orbit_parametrization import classify_orbit, pe_to_EL
from emri_lab.physics.adiabatic import integrate_adiabatic_pe
from emri_lab.waveform.pipeline import WaveformPipeline, WaveformConfig
from emri_lab.waveform.mode_manager import HarmonicMode, ModeSelectionPolicy
from emri_lab.waveform.result import WaveformResult
from emri_lab.waveform.export import (
    export_waveform_csv, export_waveform_npy, export_mode_table_json
)
from emri_lab.eob.comparison import ModelComparisonService
from emri_lab.eob.adapter import TrajectoryAdapter

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_PIPELINE = WaveformPipeline()
_COMPARISON = ModelComparisonService()
_ADAPTER = TrajectoryAdapter()

plt.style.use("dark_background")
PLOT_COLOR_1 = "#00d4ff"
PLOT_COLOR_2 = "#ff6b35"
PLOT_COLOR_3 = "#a8ff78"


def _fig(nrows=1, ncols=1, **kw) -> tuple[plt.Figure, plt.Axes]:
    kw.setdefault("figsize", (10, 3.5 * nrows))
    fig, ax = plt.subplots(nrows, ncols, **kw)
    fig.patch.set_facecolor("#0e1117")
    if nrows == 1 and ncols == 1:
        ax.set_facecolor("#1a1d24")
    else:
        for a in np.array(ax).ravel():
            a.set_facecolor("#1a1d24")
    return fig, ax


def _show(fig):
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)


# ─────────────────────────────────────────────────────────────────────────────
# Session init
# ─────────────────────────────────────────────────────────────────────────────

def _init():
    defaults = {
        "ui_state": UISessionState(),
        "inspiral": None,
        "wf_result": None,
        "mode_table": None,
        "phase_diag": None,
        "spectrum": None,
        "inspiral_b": None,   # second run for Compare tab
        "wf_result_b": None,
        "script_log": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — все параметры
# ─────────────────────────────────────────────────────────────────────────────

def _sidebar() -> tuple[OrbitParams, PhysicsConfig, WaveformConfig, int, float]:
    st.sidebar.title("⚙️ Parameters")

    # ── Orbital ──────────────────────────────────────────────────────────────
    with st.sidebar.expander("🌀 Orbital", expanded=True):
        p = st.slider("Semi-latus rectum  p (M)", 6.5, 40.0, 12.0, 0.5,
                      help="Орбитальный радиус. ISCO ≈ 6M. Разумный диапазон: 7–30M.")
        e = st.slider("Eccentricity  e", 0.0, 0.95, 0.0, 0.01,
                      help="0 = круговая орбита; >0 = эллиптическая.")
        iota = st.slider("Inclination  ι (rad)", 0.0, 3.14159, 0.0, 0.05,
                         help="Угол наклона орбиты к наблюдателю. 0 = face-on.")

    otype = classify_orbit(p, e)
    colors = {
        OrbitType.CIRCULAR_STABLE: ("🟢", "green"),
        OrbitType.BOUND_ECCENTRIC: ("🟡", "orange"),
        OrbitType.PLUNGING: ("🔴", "red"),
        OrbitType.CIRCULAR_UNSTABLE: ("🔴", "red"),
    }
    icon, col = colors.get(otype, ("⚪", "white"))
    st.sidebar.markdown(f"{icon} **Orbit:** :{col}[{otype.value}]")
    if otype in (OrbitType.PLUNGING, OrbitType.CIRCULAR_UNSTABLE):
        st.sidebar.error("Orbit is at/below separatrix — increase p!")

    # ── Physics ──────────────────────────────────────────────────────────────
    with st.sidebar.expander("⚛️ Physics", expanded=True):
        eta_options = [1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2]
        eta = st.select_slider(
            "Mass ratio  η = μ/M",
            options=eta_options, value=1e-5,
            format_func=lambda x: f"{x:.0e}",
            help="Отношение масс: малое тело / центральная ЧД. EMRI: η~10⁻⁵–10⁻⁷.",
        )
        flux_model = st.selectbox(
            "Flux model",
            options=[m.value for m in FluxModelId],
            format_func=lambda x: {
                "baseline_pn": "Baseline PN (Peters–Mathews 2.5PN)",
                "extended_test_mass": "Extended (+ Horizon flux, Poisson–Sasaki)",
            }.get(x, x),
            help="Модель потоков энергии/момента в гравволны.",
        )
        use_horizon = st.toggle(
            "Include horizon flux",
            value=False,
            help="Добавить поглощение горизонтом (член ~r⁻⁹). Мал при r≫6M.",
        )
        distance = st.number_input(
            "Observer distance (M)", value=1.0, min_value=0.01,
            format="%.2f",
            help="Расстояние до наблюдателя в единицах M. Амплитуда ∝ 1/d.",
        )

    # ── Integration ───────────────────────────────────────────────────────────
    with st.sidebar.expander("🔧 Integration"):
        t_max = st.number_input("t_max (M)", value=5e6, min_value=1e3,
                                format="%e",
                                help="Максимальное время эволюции орбиты.")
        n_points = st.slider("n_points (trajectory)", 200, 10000, 2000, 200,
                             help="Число точек выходной траектории.")
        rtol = st.select_slider("ODE rtol", [1e-6, 1e-8, 1e-10, 1e-12], value=1e-10)
        atol = st.select_slider("ODE atol", [1e-6, 1e-8, 1e-10, 1e-12], value=1e-10)

    # ── Waveform ──────────────────────────────────────────────────────────────
    with st.sidebar.expander("📡 Waveform"):
        mode_policy = st.selectbox(
            "Mode selection policy",
            ["dominant_only", "low_order_eccentric", "fixed_grid", "user_custom"],
            help=(
                "dominant_only — только (0,2).\n"
                "low_order_eccentric — n=−2..2, m=±2.\n"
                "fixed_grid — все (n,m) до n_max.\n"
                "user_custom — список ниже."
            ),
        )
        n_max = st.slider("Max harmonic index n_max", 1, 6, 3,
                          help="Используется для fixed_grid и low_order_eccentric.")
        custom_modes_str = st.text_input(
            "Custom modes [(n,m), ...]",
            value="(0,2),(1,2),(-1,2)",
            help="Активно только при user_custom. Формат: (n,m), через запятую.",
        )
        domain = st.radio("Waveform domain", ["time", "frequency", "both"],
                          horizontal=True)

    # parse custom modes
    custom_modes = None
    if mode_policy == "user_custom":
        try:
            custom_modes = [
                tuple(int(x) for x in s.strip("() ").split(","))
                for s in custom_modes_str.split("),(")
            ]
        except Exception:
            custom_modes = [(0, 2)]

    orbit = OrbitParams(p=p, e=e)
    config = PhysicsConfig(
        eta=eta,
        flux_model=FluxModelId(flux_model),
        use_horizon_flux=use_horizon,
        rtol=rtol,
        atol=atol,
    )
    wf_cfg = WaveformConfig(
        mode_policy=mode_policy,
        amplitude_model="baseline_quadrupole",
        eta=eta,
        distance=float(distance),
        iota=float(iota),
        domain=domain,
        n_max=int(n_max),
        custom_modes=custom_modes,
    )
    return orbit, config, wf_cfg, int(n_points), float(t_max)


# ─────────────────────────────────────────────────────────────────────────────
# Run logic
# ─────────────────────────────────────────────────────────────────────────────

def _run_pipeline(orbit, config, wf_cfg, n_points, t_max, tag=""):
    """Integrate inspiral + build waveform. Store into session_state."""
    suffix = f"_{tag}" if tag else ""
    with st.spinner(f"Integrating inspiral{' (B)' if tag else ''}..."):
        inspiral = integrate_adiabatic_pe(orbit, config, t_max=t_max, n_points=n_points)
    with st.spinner("Building waveform..."):
        wf_result, mode_table, phase_diag, spectrum = _PIPELINE.run(inspiral, wf_cfg)

    st.session_state[f"inspiral{suffix}"] = inspiral
    st.session_state[f"wf_result{suffix}"] = wf_result
    st.session_state[f"mode_table{suffix}"] = mode_table
    st.session_state[f"phase_diag{suffix}"] = phase_diag
    st.session_state[f"spectrum{suffix}"] = spectrum
    return inspiral, wf_result, mode_table, phase_diag, spectrum


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Waveform
# ─────────────────────────────────────────────────────────────────────────────

def _tab_waveform():
    wf: WaveformResult | None = st.session_state.wf_result
    phase_diag = st.session_state.phase_diag
    spectrum = st.session_state.spectrum

    if wf is None:
        st.info("👈 Configure parameters in the sidebar and click **Run**.")
        return

    t = wf.time
    n = len(t)

    # ── h+  hx ───────────────────────────────────────────────────────────────
    st.subheader("Gravitational wave strain  h+(t) · hₓ(t)")
    fig, axes = _fig(2, 1, figsize=(11, 5), sharex=True)
    axes[0].plot(t, wf.h_plus, color=PLOT_COLOR_1, lw=0.8)
    axes[0].set_ylabel("h₊", fontsize=11)
    axes[0].grid(alpha=0.2)
    axes[1].plot(t, wf.h_cross, color=PLOT_COLOR_2, lw=0.8)
    axes[1].set_ylabel("h×", fontsize=11)
    axes[1].set_xlabel("t  (M)", fontsize=11)
    axes[1].grid(alpha=0.2)
    fig.tight_layout(h_pad=0)
    _show(fig)

    # ── Phase + instantaneous frequency ──────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Orbital phase  Φ(t)")
        fig, ax = _fig()
        ax.plot(t, wf.phase, color=PLOT_COLOR_3, lw=1.0)
        ax.set_xlabel("t  (M)")
        ax.set_ylabel("Φ  (rad)")
        ax.grid(alpha=0.2)
        _show(fig)

    with col2:
        st.subheader("Instantaneous GW frequency")
        f_inst = wf.instantaneous_frequency
        fig, ax = _fig()
        ax.plot(t, f_inst, color=PLOT_COLOR_2, lw=1.0)
        ax.set_xlabel("t  (M)")
        ax.set_ylabel("f  (M⁻¹)")
        ax.set_yscale("log")
        ax.grid(alpha=0.2, which="both")
        _show(fig)

    # ── Amplitude envelope ───────────────────────────────────────────────────
    st.subheader("Amplitude envelope  |h(t)|")
    fig, ax = _fig()
    ax.plot(t, wf.amplitude_envelope, color=PLOT_COLOR_1, lw=1.0)
    ax.fill_between(t, 0, wf.amplitude_envelope, alpha=0.15, color=PLOT_COLOR_1)
    ax.set_xlabel("t  (M)")
    ax.set_ylabel("|h|")
    ax.grid(alpha=0.2)
    _show(fig)

    # ── Spectrum ─────────────────────────────────────────────────────────────
    if spectrum is not None:
        st.subheader("Power spectrum  |h̃(f)|²  with mode peaks")
        fig, ax = _fig()
        ax.semilogy(spectrum.frequencies[1:], spectrum.power_plus[1:],
                    color=PLOT_COLOR_1, lw=0.8, label="h+ power")
        ax.semilogy(spectrum.frequencies[1:], spectrum.power_cross[1:],
                    color=PLOT_COLOR_2, lw=0.8, alpha=0.6, label="hx power")
        for f_peak, label in zip(spectrum.peak_frequencies, spectrum.peak_mode_labels):
            ax.axvline(f_peak, color="white", lw=0.6, alpha=0.5)
            ax.text(f_peak, ax.get_ylim()[1] if ax.get_ylim()[1] > 0 else 1,
                    label, color="white", fontsize=7, rotation=90, va="top", ha="right")
        ax.set_xlabel("f  (M⁻¹)")
        ax.set_ylabel("Power")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.2, which="both")
        _show(fig)

    # ── Metrics ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total phase (rad)", f"{wf.phase[-1]:.1f}")
    c2.metric("Peak |h+|", f"{np.max(np.abs(wf.h_plus)):.3e}")
    c3.metric("Peak |hx|", f"{np.max(np.abs(wf.h_cross)):.3e}")
    c4.metric("Modes used", len(wf.selected_modes))


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Inspiral
# ─────────────────────────────────────────────────────────────────────────────

def _tab_inspiral():
    ins: InspiralResult | None = st.session_state.inspiral

    if ins is None:
        st.info("Run the inspiral first.")
        return

    t = ins.t

    st.subheader("Orbital evolution")
    col1, col2 = st.columns(2)

    with col1:
        fig, ax = _fig()
        ax.plot(t, ins.r_circ, color=PLOT_COLOR_1)
        ax.axhline(6.0, color="red", lw=1, ls="--", label="ISCO (r=6M)")
        ax.set_xlabel("t  (M)")
        ax.set_ylabel("r_circ  (M)")
        ax.legend()
        ax.grid(alpha=0.2)
        _show(fig)

    with col2:
        fig, ax = _fig()
        ax.plot(ins.p_arr, ins.e_arr, color=PLOT_COLOR_3, lw=1.5)
        e_line = np.linspace(0, 0.95, 200)
        ax.plot(6 + 2 * e_line, e_line, color="red", ls="--", lw=1, label="separatrix")
        ax.set_xlabel("p  (M)")
        ax.set_ylabel("e")
        ax.set_title("(p, e) phase portrait")
        ax.legend()
        ax.grid(alpha=0.2)
        _show(fig)

    col3, col4 = st.columns(2)

    with col3:
        fig, ax = _fig()
        ax.plot(t, ins.E_arr, color=PLOT_COLOR_2)
        ax.set_xlabel("t  (M)")
        ax.set_ylabel("E  (specific energy)")
        ax.set_title("Energy evolution")
        ax.grid(alpha=0.2)
        _show(fig)

    with col4:
        fig, ax = _fig()
        ax.plot(t, ins.L_arr, color=PLOT_COLOR_1)
        ax.set_xlabel("t  (M)")
        ax.set_ylabel("L  (specific ang. mom.)")
        ax.set_title("Angular momentum evolution")
        ax.grid(alpha=0.2)
        _show(fig)

    if ins.plunged:
        st.success(f"✅ Plunge detected at t = {t[-1]:.3e} M, r = {ins.r_circ[-1]:.2f} M")
    else:
        st.warning("⚠️ Integration reached t_max without plunge (increase t_max or η)")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Initial p", f"{ins.p_arr[0]:.2f} M")
    c2.metric("Final p", f"{ins.p_arr[-1]:.2f} M")
    c3.metric("ΔE / E₀", f"{abs(ins.E_arr[-1]-ins.E_arr[0])/abs(ins.E_arr[0]):.4f}")
    c4.metric("Plunged", "Yes" if ins.plunged else "No")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Mode Decomposition
# ─────────────────────────────────────────────────────────────────────────────

def _tab_modes():
    wf: WaveformResult | None = st.session_state.wf_result
    mt = st.session_state.mode_table

    if wf is None or mt is None:
        st.info("Run the inspiral + waveform first.")
        return

    st.subheader("Mode amplitude decomposition")

    # bar chart
    labels = [str(m) for m in mt.modes]
    amps = mt.amplitudes
    fig, ax = _fig(figsize=(max(7, len(labels) * 0.8), 4))
    bars = ax.bar(labels, amps, color=PLOT_COLOR_1, edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Mode (n, m)")
    ax.set_ylabel("|A_{n,m}|")
    ax.set_title("Amplitude per harmonic mode")
    ax.grid(alpha=0.2, axis="y")
    _show(fig)

    # per-mode contribution plot
    if len(wf.selected_modes) > 1:
        st.subheader("Individual mode contributions to h+(t)")
        phase_svc = _PIPELINE._phase_svc
        inspiral = st.session_state.inspiral
        if inspiral is not None:
            omega_r, omega_phi = phase_svc.extract_frequencies(inspiral)
            t = wf.time
            fig, ax = _fig(figsize=(11, 4))
            for mode, amp in zip(mt.modes, mt.amplitudes):
                phi_nm = phase_svc.accumulate_harmonic_phase(
                    t, omega_r, omega_phi, mode.n, mode.m
                )
                h_mode = amp * np.cos(phi_nm)
                ax.plot(t, h_mode, lw=0.7, alpha=0.8, label=str(mode))
            ax.set_xlabel("t  (M)")
            ax.set_ylabel("h+ contribution")
            ax.legend(fontsize=8, ncol=4)
            ax.grid(alpha=0.2)
            _show(fig)

    # table
    st.subheader("Mode amplitude table")
    rows = [{"mode": str(m), "|A|": f"{a:.4e}", "phase (rad)": f"{p:.4f}"}
            for m, a, p in zip(mt.modes, mt.amplitudes, mt.phases)]
    st.dataframe(rows, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Compare
# ─────────────────────────────────────────────────────────────────────────────

def _tab_compare(orbit, config, wf_cfg, n_points, t_max):
    st.subheader("Model comparison — run A vs run B")

    wf_a: WaveformResult | None = st.session_state.wf_result
    wf_b: WaveformResult | None = st.session_state.wf_result_b

    with st.expander("Run B configuration", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            p_b = st.slider("p_B (M)", 6.5, 40.0, float(orbit.p), 0.5, key="p_b")
            e_b = st.slider("e_B", 0.0, 0.95, float(orbit.e), 0.01, key="e_b")
            eta_b = st.select_slider("η_B", [1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2],
                                     value=config.eta, format_func=lambda x: f"{x:.0e}",
                                     key="eta_b")
        with col2:
            flux_b = st.selectbox("Flux model B",
                                  [m.value for m in FluxModelId],
                                  index=0, key="flux_b")
            hor_b = st.toggle("Horizon flux B", value=False, key="hor_b")
            t_max_b = st.number_input("t_max_B (M)", value=float(t_max),
                                      format="%e", key="tmax_b")

    if st.button("▶ Run B", type="secondary"):
        orbit_b = OrbitParams(p=p_b, e=e_b)
        config_b = PhysicsConfig(eta=eta_b, flux_model=FluxModelId(flux_b),
                                 use_horizon_flux=hor_b)
        _run_pipeline(orbit_b, config_b, wf_cfg, n_points, t_max_b, tag="b")
        st.rerun()

    if wf_a is None or wf_b is None:
        st.info("Run both A (main Run button) and B to compare.")
        return

    # ── Overlay h+ ───────────────────────────────────────────────────────────
    st.subheader("h+(t) overlay")
    fig, ax = _fig()
    ax.plot(wf_a.time, wf_a.h_plus, color=PLOT_COLOR_1, lw=0.8, label="Run A")
    ax.plot(wf_b.time, wf_b.h_plus, color=PLOT_COLOR_2, lw=0.8, ls="--", label="Run B")
    ax.set_xlabel("t  (M)")
    ax.set_ylabel("h+")
    ax.legend()
    ax.grid(alpha=0.2)
    _show(fig)

    # ── Phase residual ────────────────────────────────────────────────────────
    cmp = _COMPARISON.compare_phases(wf_a, wf_b)
    st.subheader("GW phase residual  ΔΦ(t) = Φ_A − Φ_B")
    fig, ax = _fig()
    ax.plot(cmp["t"], cmp["phase_residual"], color=PLOT_COLOR_3, lw=1.0)
    ax.axhline(0, color="white", lw=0.5, ls="--")
    ax.set_xlabel("t  (M)")
    ax.set_ylabel("ΔΦ  (rad)")
    ax.grid(alpha=0.2)
    _show(fig)

    # trajectory comparison
    traj_a = _ADAPTER.from_adiabatic(st.session_state.inspiral)
    traj_b = _ADAPTER.from_adiabatic(st.session_state.inspiral_b)
    traj_cmp = _COMPARISON.compare_trajectories(traj_a, traj_b)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Max dephasing (rad)", f"{cmp['max_dephasing']:.4f}")
    c2.metric("RMS phase diff (rad)", f"{cmp['rms_phase_diff']:.4f}")
    c3.metric("Waveform mismatch", f"{_COMPARISON.waveform_mismatch(wf_a, wf_b):.6f}")
    c4.metric("Δr RMS (M)", f"{traj_cmp.get('r_rms_diff', 0):.4f}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Script
# ─────────────────────────────────────────────────────────────────────────────

_SCRIPT_TEMPLATE = '''\
"""
Скрипт автоматизации EMRI waveform.

Доступные объекты в пространстве имён:
  np                       — NumPy
  OrbitParams, PhysicsConfig, WaveformConfig
  integrate_adiabatic_pe   — запуск орбитальной эволюции
  WaveformPipeline         — построение waveform
  FluxModelId              — выбор flux-модели

После исполнения скрипт должен определить переменные:
  inspiral   — InspiralResult
  wf_result  — WaveformResult
  mode_table — ModeAmplitudeTable
  phase_diag — PhaseDiagnostics
  spectrum   — SpectrumDiagnostics | None
"""
import numpy as np
from emri_lab.domain.models import OrbitParams, PhysicsConfig
from emri_lab.domain.enums import FluxModelId
from emri_lab.physics.adiabatic import integrate_adiabatic_pe
from emri_lab.waveform.pipeline import WaveformPipeline, WaveformConfig

# ── Параметры ────────────────────────────────────────────────────────────────
orbit = OrbitParams(p=12.0, e=0.3)
config = PhysicsConfig(eta=1e-5, flux_model=FluxModelId.BASELINE_PN)

wf_cfg = WaveformConfig(
    mode_policy="low_order_eccentric",
    eta=1e-5,
    distance=1.0,
    iota=0.0,
    domain="both",
    n_max=2,
)

# ── Вычисление ───────────────────────────────────────────────────────────────
inspiral = integrate_adiabatic_pe(orbit, config, t_max=5e6, n_points=3000)

pipeline = WaveformPipeline()
wf_result, mode_table, phase_diag, spectrum = pipeline.run(inspiral, wf_cfg)
'''


def _tab_script():
    st.subheader("📜 Script automation")
    st.markdown(
        "Загрузи `.py`-файл **или** вставь код вручную. "
        "Скрипт должен определить переменные `inspiral`, `wf_result`, `mode_table`, `phase_diag`, `spectrum`. "
        "После исполнения результаты появятся во вкладках **Waveform**, **Inspiral** и **Modes**."
    )

    uploaded = st.file_uploader("Upload .py script", type=["py"])
    if uploaded:
        code = uploaded.read().decode("utf-8")
    else:
        code = st.text_area("Or paste script here:", value=_SCRIPT_TEMPLATE, height=420)

    col1, col2 = st.columns([1, 3])
    with col1:
        run_script = st.button("▶ Execute script", type="primary")

    if run_script:
        ns: dict = {}
        log_buf = io.StringIO()
        try:
            with st.spinner("Running script..."):
                exec(compile(code, "<script>", "exec"), ns)

            required = ["inspiral", "wf_result", "mode_table", "phase_diag", "spectrum"]
            missing = [k for k in required if k not in ns]
            if missing:
                st.error(f"Script did not define: {missing}")
            else:
                st.session_state.inspiral   = ns["inspiral"]
                st.session_state.wf_result  = ns["wf_result"]
                st.session_state.mode_table = ns["mode_table"]
                st.session_state.phase_diag = ns["phase_diag"]
                st.session_state.spectrum   = ns["spectrum"]
                st.success("✅ Script executed. Results loaded into Waveform / Inspiral / Modes tabs.")
        except Exception:
            st.error("Script error:")
            st.code(traceback.format_exc(), language="python")

    if st.session_state.script_log:
        with st.expander("Script log"):
            st.text(st.session_state.script_log)

    with st.expander("📋 Script template reference"):
        st.code(_SCRIPT_TEMPLATE, language="python")


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Export
# ─────────────────────────────────────────────────────────────────────────────

def _tab_export():
    wf: WaveformResult | None = st.session_state.wf_result
    mt = st.session_state.mode_table

    if wf is None:
        st.info("Run the waveform first.")
        return

    st.subheader("Export results")

    # ── CSV ──────────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        csv_path = export_waveform_csv(wf, tmp / "waveform.csv")
        npy_path = export_waveform_npy(wf, tmp / "waveform")
        if mt:
            json_path = export_mode_table_json(mt, tmp / "modes.json")
        else:
            json_path = None

        col1, col2, col3 = st.columns(3)

        with col1:
            with open(csv_path, "rb") as f:
                st.download_button(
                    "⬇ Download waveform.csv",
                    f.read(), "waveform.csv", "text/csv",
                )

        with col2:
            with open(str(npy_path) + ".npz", "rb") as f:
                st.download_button(
                    "⬇ Download waveform.npz",
                    f.read(), "waveform.npz",
                    "application/octet-stream",
                )

        with col3:
            if json_path:
                with open(json_path, "rb") as f:
                    st.download_button(
                        "⬇ Download modes.json",
                        f.read(), "modes.json", "application/json",
                    )

        # diagnostics JSON
        st.subheader("Quick data preview")
        ins: InspiralResult | None = st.session_state.inspiral
        if ins is not None:
            diag = {
                "n_steps": len(wf.time),
                "t_start": float(wf.time[0]),
                "t_end": float(wf.time[-1]),
                "max_h_plus": float(np.max(np.abs(wf.h_plus))),
                "max_h_cross": float(np.max(np.abs(wf.h_cross))),
                "total_phase_rad": float(wf.phase[-1]),
                "modes": [str(m) for m in wf.selected_modes],
                "plunged": ins.plunged,
                "final_p": float(ins.p_arr[-1]),
                "final_r": float(ins.r_circ[-1]),
            }
            st.json(diag)

            diag_bytes = json.dumps(diag, indent=2).encode()
            st.download_button(
                "⬇ Download diagnostics.json",
                diag_bytes, "diagnostics.json", "application/json",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="EMRI Waveform Console",
        page_icon="🌊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _init()

    st.title("🌊 EMRI Waveform Console")
    st.caption(
        "Extreme Mass Ratio Inspiral — adiabatic inspiral → gravitational waveform. "
        "All quantities in geometrized units G = c = M = 1."
    )

    orbit, config, wf_cfg, n_points, t_max = _sidebar()

    # ── Run button in sidebar ─────────────────────────────────────────────────
    st.sidebar.divider()
    if st.sidebar.button("▶ Run Inspiral + Waveform", type="primary", use_container_width=True):
        otype = classify_orbit(orbit.p, orbit.e)
        if otype in (OrbitType.PLUNGING, OrbitType.CIRCULAR_UNSTABLE):
            st.sidebar.error("Cannot run: orbit is at or below separatrix.")
        else:
            _run_pipeline(orbit, config, wf_cfg, n_points, t_max)
            st.rerun()

    if st.sidebar.button("🗑 Clear results", use_container_width=True):
        for key in ["inspiral", "wf_result", "mode_table", "phase_diag",
                    "spectrum", "inspiral_b", "wf_result_b"]:
            st.session_state[key] = None
        st.rerun()

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tabs = st.tabs(["📡 Waveform", "🌀 Inspiral", "🎵 Modes", "⚖️ Compare", "📜 Script", "⬇ Export"])

    with tabs[0]:
        _tab_waveform()
    with tabs[1]:
        _tab_inspiral()
    with tabs[2]:
        _tab_modes()
    with tabs[3]:
        _tab_compare(orbit, config, wf_cfg, n_points, t_max)
    with tabs[4]:
        _tab_script()
    with tabs[5]:
        _tab_export()


if __name__ == "__main__":
    main()
