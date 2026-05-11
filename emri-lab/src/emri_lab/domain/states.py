from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .enums import AppState
from .models import InspiralResult, OrbitParams, PhysicsConfig, WaveformPreview

# ---------------------------------------------------------------------------
# Allowed state transitions (adjacency list for the finite-state machine)
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: dict[AppState, set[AppState]] = {
    AppState.IDLE: {
        AppState.CONFIGURING,
        AppState.ERROR,
    },
    AppState.CONFIGURING: {
        AppState.RUNNING_GEODESIC,
        AppState.RUNNING_INSPIRAL,
        AppState.IDLE,
        AppState.ERROR,
    },
    AppState.RUNNING_GEODESIC: {
        AppState.VIEWING_RESULTS,
        AppState.CONFIGURING,
        AppState.ERROR,
    },
    AppState.RUNNING_INSPIRAL: {
        AppState.VIEWING_RESULTS,
        AppState.CONFIGURING,
        AppState.ERROR,
    },
    AppState.VIEWING_RESULTS: {
        AppState.CONFIGURING,
        AppState.IDLE,
        AppState.ERROR,
    },
    AppState.ERROR: {
        AppState.IDLE,
        AppState.CONFIGURING,
    },
}


@dataclass
class UISessionState:
    """Holds the complete mutable state of a Streamlit UI session.

    The ``transition`` method enforces the FSM defined in ``_VALID_TRANSITIONS``
    and raises ``ValueError`` for illegal transitions so bugs surface early.
    """

    app_state: AppState = AppState.IDLE
    orbit: Optional[OrbitParams] = None
    config: Optional[PhysicsConfig] = None
    inspiral_result: Optional[InspiralResult] = None
    waveform_preview: Optional[WaveformPreview] = None
    error_message: str = ""
    run_id: str = ""

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def transition(self, new_state: AppState) -> None:
        """Advance the FSM to *new_state*, raising ValueError on illegal moves."""
        allowed = _VALID_TRANSITIONS.get(self.app_state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Illegal state transition: {self.app_state!r} → {new_state!r}. "
                f"Allowed targets: {sorted(s.value for s in allowed)}"
            )
        self.app_state = new_state

    def reset(self) -> None:
        """Return to IDLE and clear all transient data."""
        self.app_state = AppState.IDLE
        self.orbit = None
        self.config = None
        self.inspiral_result = None
        self.waveform_preview = None
        self.error_message = ""
        self.run_id = ""
