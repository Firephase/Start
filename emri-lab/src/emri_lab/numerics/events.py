"""Event functions for scipy solve_ivp integration."""

from __future__ import annotations


def make_separatrix_event(margin: float = 0.05):
    """Terminal event: orbit reaches separatrix p = 6 + 2*e + margin."""
    def event(t: float, state) -> float:
        p, e = state[0], max(state[1], 0.0)
        return p - (6.0 + 2.0 * e + margin)

    event.terminal = True
    event.direction = -1.0
    return event


def make_plunge_event(margin: float = 0.05):
    """Alias for separatrix event (p approaching last stable orbit)."""
    return make_separatrix_event(margin)


def make_periapsis_event(r_peri_target: float):
    """Non-terminal event: r passes through r_peri_target (downward crossing)."""
    def event(t: float, state) -> float:
        r = state[0]
        return r - r_peri_target

    event.terminal = False
    event.direction = -1.0
    return event


def make_apoapsis_event(r_apo_target: float):
    """Non-terminal event: r passes through r_apo_target (upward crossing)."""
    def event(t: float, state) -> float:
        r = state[0]
        return r - r_apo_target

    event.terminal = False
    event.direction = 1.0
    return event
