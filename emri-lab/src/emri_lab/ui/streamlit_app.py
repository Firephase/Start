"""EMRI Research Console — Streamlit UI."""

import streamlit as st
import numpy as np
import matplotlib.pyplot as plt

from emri_lab.domain.enums import AppState, FluxModelId, OrbitType
from emri_lab.domain.models import OrbitParams, PhysicsConfig
from emri_lab.domain.states import UISessionState
from emri_lab.application.use_cases import run_geodesic_simulation, run_adiabatic_simulation
from emri_lab.physics.orbit_parametrization import classify_orbit


def init_session():
    """Initialize Streamlit session state with a fresh UISessionState if not present."""
    if "ui_state" not in st.session_state:
        st.session_state.ui_state = UISessionState()


def render_sidebar(state: UISessionState):
    """Render configuration sidebar.

    Returns
    -------
    tuple[OrbitParams, PhysicsConfig, int, float]
        (orbit, config, n_points, t_max) from sidebar widgets.
    """
    st.sidebar.title("EMRI Configuration")

    p = st.sidebar.slider("Semi-latus rectum p", 7.0, 30.0, 12.0, 0.5)
    e = st.sidebar.slider("Eccentricity e", 0.0, 0.9, 0.0, 0.05)
    eta = st.sidebar.select_slider(
        "Mass ratio η",
        options=[1e-6, 1e-5, 1e-4, 1e-3],
        value=1e-5,
    )
    flux_model = st.sidebar.selectbox(
        "Flux model",
        options=[m.value for m in FluxModelId],
    )
    t_max = st.sidebar.number_input("t_max (M)", value=1e7, format="%e")
    n_points = st.sidebar.number_input(
        "n_points", value=2000, min_value=100, max_value=20000
    )

    orbit = OrbitParams(p=p, e=e)
    config = PhysicsConfig(eta=eta, flux_model=FluxModelId(flux_model))

    orbit_type = classify_orbit(p, e)
    if orbit_type == OrbitType.CIRCULAR_STABLE:
        color = "green"
    elif orbit_type == OrbitType.BOUND_ECCENTRIC:
        color = "orange"
    else:
        color = "red"
    st.sidebar.markdown(f"**Orbit type:** :{color}[{orbit_type.value}]")

    return orbit, config, int(n_points), t_max


def render_results(state: UISessionState):
    """Render inspiral results plots and summary metrics."""
    result = state.inspiral_result
    if result is None:
        return

    st.subheader("Inspiral Results")
    col1, col2 = st.columns(2)

    with col1:
        fig, ax = plt.subplots()
        ax.plot(result.t, result.r_circ)
        ax.set_xlabel("t (M)")
        ax.set_ylabel("r_circ (M)")
        ax.set_title("Orbital Radius Evolution")
        st.pyplot(fig)
        plt.close(fig)

    with col2:
        fig, ax = plt.subplots()
        ax.plot(result.p_arr, result.e_arr)
        ax.set_xlabel("p (M)")
        ax.set_ylabel("e")
        ax.set_title("(p, e) Trajectory")
        # Draw separatrix p = 6 + 2e
        e_line = np.linspace(0, 0.9, 100)
        ax.plot(6 + 2 * e_line, e_line, "r--", label="separatrix")
        ax.legend()
        st.pyplot(fig)
        plt.close(fig)

    if result.plunged:
        st.success("Inspiral terminated at ISCO (plunge)")

    st.metric("Final r_circ", f"{result.r_circ[-1]:.3f} M")
    st.metric("Final p", f"{result.p_arr[-1]:.3f} M")
    st.metric("Final e", f"{result.e_arr[-1]:.4f}")


def main():
    """Entry point for the Streamlit EMRI Research Console."""
    st.set_page_config(page_title="EMRI Research Console", layout="wide")
    st.title("EMRI Research Console")

    init_session()
    state: UISessionState = st.session_state.ui_state

    orbit, config, n_points, t_max = render_sidebar(state)

    col_run, col_status = st.columns([1, 3])
    with col_run:
        if st.button("Run Geodesic Analysis", type="secondary"):
            state.transition(AppState.RUNNING_GEODESIC)
            geo = run_geodesic_simulation(orbit, config)
            st.info(f"E={geo.E:.6f}, L={geo.L:.6f}, type={geo.orbit_type}")
            state.transition(AppState.VIEWING_RESULTS)

        if st.button("Run Adiabatic Inspiral", type="primary"):
            state.transition(AppState.RUNNING_INSPIRAL)
            state.orbit = orbit
            state.config = config
            with st.spinner("Integrating inspiral..."):
                result, meta = run_adiabatic_simulation(
                    orbit, config, t_max=t_max, n_points=n_points
                )
            state.inspiral_result = result
            state.transition(AppState.VIEWING_RESULTS)

    render_results(state)


if __name__ == "__main__":
    main()
