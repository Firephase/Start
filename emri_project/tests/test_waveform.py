"""Tests for waveform generator."""

import numpy as np
import pytest
from emri_project.waveform.basic import (
    generate_waveform_basic, accumulated_phase, amplitude_envelope
)
from emri_project.waveform.interfaces import waveform_from_geodesic
from emri_project.dynamics.geodesic_solver import ic_circular, integrate_geodesic


class TestBasicWaveform:
    """Test basic quadrupole waveform."""

    def _make_circular_waveform(self):
        state0, E, L = ic_circular(10.0)
        sol = integrate_geodesic(state0, E, L, tau_max=200.0, n_points=2000)
        return sol

    def test_waveform_shapes(self):
        sol = self._make_circular_waveform()
        h_plus, h_cross = generate_waveform_basic(sol.t, sol.r, sol.phi, eta=1e-5)
        assert h_plus.shape == sol.t.shape
        assert h_cross.shape == sol.t.shape

    def test_waveform_amplitude_positive(self):
        sol = self._make_circular_waveform()
        h_plus, h_cross = generate_waveform_basic(sol.t, sol.r, sol.phi, eta=1e-5)
        amp = amplitude_envelope(h_plus, h_cross)
        assert np.all(amp >= 0)

    def test_circular_waveform_constant_amplitude(self):
        """Circular geodesic → near-constant amplitude."""
        sol = self._make_circular_waveform()
        h_plus, h_cross = generate_waveform_basic(sol.t, sol.r, sol.phi, eta=1e-5)
        amp = amplitude_envelope(h_plus, h_cross)
        # amplitude variation < 1% for circular orbit
        rel_var = (np.max(amp) - np.min(amp)) / np.mean(amp)
        assert rel_var < 0.01

    def test_phase_monotonically_increasing(self):
        sol = self._make_circular_waveform()
        phase = accumulated_phase(sol.phi)
        assert np.all(np.diff(phase) >= 0)

    def test_face_on_polarization_ratio(self):
        """For face-on (ι=0): |h_+| / |h_×| = 1 for circular orbit."""
        sol = self._make_circular_waveform()
        h_plus, h_cross = generate_waveform_basic(
            sol.t, sol.r, sol.phi, eta=1e-5, iota=0.0
        )
        # rms ratio
        ratio = np.sqrt(np.mean(h_plus**2)) / np.sqrt(np.mean(h_cross**2))
        assert abs(ratio - 1.0) < 0.05

    def test_waveform_from_geodesic_interface(self):
        sol = self._make_circular_waveform()
        wf = waveform_from_geodesic(sol.t, sol.r, sol.phi, eta=1e-5)
        assert wf.h_plus is not None
        assert wf.h_cross is not None
        assert wf.h22 is not None
