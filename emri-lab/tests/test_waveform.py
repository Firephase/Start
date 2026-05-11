"""Comprehensive tests for the Step 4 waveform layer."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from emri_lab.domain.models import InspiralResult
from emri_lab.waveform import (
    HarmonicMode,
    ModeSelectionPolicy,
    BaseAmplitudeModel,
    BaselineQuadrupoleAmplitude,
    AmplitudeModelRegistry,
    PhaseEvolutionService,
    WaveformSummationService,
    FrequencyDomainPreview,
    WaveformResult,
    ModeAmplitudeTable,
    PhaseDiagnostics,
    SpectrumDiagnostics,
    WaveformPipeline,
    WaveformConfig,
    export_waveform_csv,
    export_waveform_npy,
    export_mode_table_json,
    export_plot_bundle,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def make_inspiral(n_pts: int = 200, r0: float = 12.0, rf: float = 8.0) -> InspiralResult:
    """Create a minimal InspiralResult with smooth arrays for testing."""
    t = np.linspace(0.0, 1000.0, n_pts)
    r = np.linspace(r0, rf, n_pts)          # slowly decaying circular radius
    p = r.copy()                             # circular: p ≈ r
    e = np.full(n_pts, 0.1)                 # constant low eccentricity
    # Circular energy and angular momentum from Schwarzschild
    E = -(1.0 - 2.0 / r) / np.sqrt(1.0 - 3.0 / r)
    L = r / np.sqrt(r - 3.0)
    return InspiralResult(
        t=t,
        p_arr=p,
        e_arr=e,
        E_arr=E,
        L_arr=L,
        r_circ=r,
        plunged=False,
        message="test inspiral",
    )


# ---------------------------------------------------------------------------
# HarmonicMode tests
# ---------------------------------------------------------------------------

class TestHarmonicMode:
    def test_frozen_and_hashable(self):
        mode = HarmonicMode(n=0, m=2, l=2)
        # frozen dataclass must be hashable
        h = hash(mode)
        assert isinstance(h, int)

    def test_can_be_used_as_dict_key(self):
        mode = HarmonicMode(n=1, m=2)
        d = {mode: "value"}
        assert d[mode] == "value"

    def test_immutable(self):
        mode = HarmonicMode(n=0, m=2)
        with pytest.raises((AttributeError, TypeError)):
            mode.n = 99  # type: ignore[misc]

    def test_str_representation(self):
        mode = HarmonicMode(n=1, m=-2)
        assert str(mode) == "(1,-2)"

    def test_equality(self):
        assert HarmonicMode(n=0, m=2) == HarmonicMode(n=0, m=2)
        assert HarmonicMode(n=1, m=2) != HarmonicMode(n=0, m=2)

    def test_l_optional_default_none(self):
        mode = HarmonicMode(n=0, m=2)
        assert mode.l is None

    def test_l_stored_when_given(self):
        mode = HarmonicMode(n=0, m=2, l=2)
        assert mode.l == 2


# ---------------------------------------------------------------------------
# ModeSelectionPolicy tests
# ---------------------------------------------------------------------------

class TestModeSelectionPolicy:
    def setup_method(self):
        self.policy = ModeSelectionPolicy()
        self.inspiral = make_inspiral()

    def test_dominant_only(self):
        modes = self.policy.select_modes(self.inspiral, "dominant_only")
        assert len(modes) == 1
        assert modes[0] == HarmonicMode(n=0, m=2, l=2)

    def test_low_order_eccentric_count(self):
        modes = self.policy.select_modes(self.inspiral, "low_order_eccentric")
        # n in [-2,-1,0,1,2]: n=0 → 1 mode (m=2 only); n≠0 → 2 modes each (m=2 and m=-2)
        # = 1 + 4*2 = 9
        assert len(modes) == 9

    def test_low_order_eccentric_contains_dominant(self):
        modes = self.policy.select_modes(self.inspiral, "low_order_eccentric")
        assert HarmonicMode(n=0, m=2, l=2) in modes

    def test_low_order_eccentric_no_n0_m_minus2(self):
        modes = self.policy.select_modes(self.inspiral, "low_order_eccentric")
        assert HarmonicMode(n=0, m=-2, l=2) not in modes

    def test_fixed_grid_default_n_max(self):
        modes = self.policy.select_modes(self.inspiral, "fixed_grid")
        # n_max=3: n in [-3..3] (7 values) × m in [2,-2] (2 values) = 14
        assert len(modes) == 14

    def test_fixed_grid_custom_n_max(self):
        modes = self.policy.select_modes(self.inspiral, "fixed_grid", n_max=1)
        # n in [-1,0,1] × m in [2,-2] = 6
        assert len(modes) == 6

    def test_user_custom(self):
        modes = self.policy.select_modes(
            self.inspiral, "user_custom", modes=[(0, 2), (1, 2), (-1, 2)]
        )
        assert len(modes) == 3
        assert HarmonicMode(n=0, m=2, l=2) in modes
        assert HarmonicMode(n=1, m=2, l=2) in modes

    def test_user_custom_default_list(self):
        modes = self.policy.select_modes(self.inspiral, "user_custom")
        assert len(modes) == 1

    def test_unknown_policy_raises(self):
        with pytest.raises(ValueError, match="Unknown policy"):
            self.policy.select_modes(self.inspiral, "nonexistent_policy")


# ---------------------------------------------------------------------------
# PhaseEvolutionService tests
# ---------------------------------------------------------------------------

class TestPhaseEvolutionService:
    def setup_method(self):
        self.svc = PhaseEvolutionService()
        self.inspiral = make_inspiral()

    def test_accumulate_phase_monotone_increasing_for_positive_omega(self):
        t = np.linspace(0.0, 100.0, 500)
        omega = np.full(len(t), 0.05)
        phi = self.svc.accumulate_phase(t, omega)
        assert phi[0] == pytest.approx(0.0)
        assert np.all(np.diff(phi) >= 0.0)

    def test_accumulate_phase_initial_zero(self):
        t = np.linspace(0.0, 10.0, 100)
        omega = np.ones(100)
        phi = self.svc.accumulate_phase(t, omega)
        assert phi[0] == 0.0

    def test_accumulate_phase_constant_omega(self):
        """For constant Ω, Φ(t) ≈ Ω·t."""
        t = np.linspace(0.0, 10.0, 10000)
        omega_val = 0.1
        omega = np.full(len(t), omega_val)
        phi = self.svc.accumulate_phase(t, omega)
        expected = omega_val * t
        np.testing.assert_allclose(phi, expected, rtol=1e-4)

    def test_accumulate_harmonic_phase_dominant_mode_equals_2phi_phi(self):
        """Φ_{0,2}(t) = 2·Φ_φ(t)."""
        t = np.linspace(0.0, 100.0, 200)
        r = np.linspace(12.0, 9.0, 200)
        omega_phi = r ** (-1.5)
        ratio = np.maximum(1.0 - 6.0 / r, 0.0)
        omega_r = omega_phi * np.sqrt(ratio)

        phi_02 = self.svc.accumulate_harmonic_phase(t, omega_r, omega_phi, n=0, m=2)
        phi_phi = self.svc.accumulate_phase(t, omega_phi)

        np.testing.assert_allclose(phi_02, 2.0 * phi_phi, rtol=1e-12)

    def test_accumulate_harmonic_phase_pure_radial(self):
        """Φ_{1,0}(t) = Φ_r(t)."""
        t = np.linspace(0.0, 100.0, 200)
        r = np.linspace(12.0, 9.0, 200)
        omega_phi = r ** (-1.5)
        ratio = np.maximum(1.0 - 6.0 / r, 0.0)
        omega_r = omega_phi * np.sqrt(ratio)

        phi_10 = self.svc.accumulate_harmonic_phase(t, omega_r, omega_phi, n=1, m=0)
        phi_r = self.svc.accumulate_phase(t, omega_r)

        np.testing.assert_allclose(phi_10, phi_r, rtol=1e-12)

    def test_extract_frequencies_shape(self):
        omega_r, omega_phi = self.svc.extract_frequencies(self.inspiral)
        assert omega_r.shape == self.inspiral.t.shape
        assert omega_phi.shape == self.inspiral.t.shape

    def test_extract_frequencies_omega_phi_positive(self):
        _, omega_phi = self.svc.extract_frequencies(self.inspiral)
        assert np.all(omega_phi > 0)

    def test_extract_frequencies_omega_r_nonnegative(self):
        omega_r, _ = self.svc.extract_frequencies(self.inspiral)
        assert np.all(omega_r >= 0)

    def test_extract_frequencies_omega_r_leq_omega_phi(self):
        """Radial frequency ≤ orbital frequency (Schwarzschild, r > 6M)."""
        omega_r, omega_phi = self.svc.extract_frequencies(self.inspiral)
        assert np.all(omega_r <= omega_phi + 1e-15)

    def test_extract_frequencies_circular_limit(self):
        """At r >> 6M, Ω_r → Ω_φ."""
        inspiral_far = make_inspiral(r0=1000.0, rf=900.0)
        omega_r, omega_phi = self.svc.extract_frequencies(inspiral_far)
        ratio = omega_r / omega_phi
        np.testing.assert_allclose(ratio, np.ones_like(ratio), atol=1e-2)

    def test_build_phase_diagnostics_returns_correct_type(self):
        omega_r, omega_phi = self.svc.extract_frequencies(self.inspiral)
        diag = self.svc.build_phase_diagnostics(self.inspiral.t, omega_r, omega_phi)
        assert isinstance(diag, PhaseDiagnostics)

    def test_build_phase_diagnostics_phi_gw_is_2x_phi_orbital(self):
        omega_r, omega_phi = self.svc.extract_frequencies(self.inspiral)
        diag = self.svc.build_phase_diagnostics(self.inspiral.t, omega_r, omega_phi)
        np.testing.assert_allclose(diag.phi_gw, 2.0 * diag.phi_orbital, rtol=1e-12)

    def test_build_phase_diagnostics_phi_orbital_monotone(self):
        omega_r, omega_phi = self.svc.extract_frequencies(self.inspiral)
        diag = self.svc.build_phase_diagnostics(self.inspiral.t, omega_r, omega_phi)
        assert np.all(np.diff(diag.phi_orbital) >= 0)


# ---------------------------------------------------------------------------
# Amplitude model tests
# ---------------------------------------------------------------------------

class TestBaselineQuadrupoleAmplitude:
    def setup_method(self):
        self.model = BaselineQuadrupoleAmplitude()
        self.base_state = {
            "r": 10.0, "p": 10.0, "e": 0.1,
            "eta": 1e-5, "distance": 1.0, "iota": 0.0,
        }

    def test_dominant_mode_nonzero(self):
        mode = HarmonicMode(n=0, m=2)
        amp = self.model.amplitude(mode, self.base_state)
        assert abs(amp) > 0

    def test_dominant_mode_amplitude_magnitude(self):
        """Dominant mode |A| = |pol_factor| * 4η/r.
        At iota=0: pol_factor = -(1+1)/2 + i*(-1) = -1 - i, so |pol_factor| = sqrt(2).
        Expected |A| = sqrt(2) * 4η/r.
        """
        mode = HarmonicMode(n=0, m=2)
        amp = self.model.amplitude(mode, self.base_state)
        expected = np.sqrt(2) * 4e-5 / 10.0
        assert abs(amp) == pytest.approx(expected, rel=0.01)

    def test_eccentric_mode_smaller_than_dominant(self):
        mode_dom = HarmonicMode(n=0, m=2)
        mode_ecc = HarmonicMode(n=1, m=2)
        amp_dom = abs(self.model.amplitude(mode_dom, self.base_state))
        amp_ecc = abs(self.model.amplitude(mode_ecc, self.base_state))
        assert amp_ecc < amp_dom

    def test_eccentric_mode_scales_with_eccentricity(self):
        mode = HarmonicMode(n=1, m=2)
        state_lo = {**self.base_state, "e": 0.05}
        state_hi = {**self.base_state, "e": 0.5}
        amp_lo = abs(self.model.amplitude(mode, state_lo))
        amp_hi = abs(self.model.amplitude(mode, state_hi))
        assert amp_hi > amp_lo

    def test_iota_zero_produces_complex_amplitude(self):
        mode = HarmonicMode(n=0, m=2)
        amp = self.model.amplitude(mode, self.base_state)
        assert isinstance(amp, complex)

    def test_registry_get_returns_instance(self):
        model = AmplitudeModelRegistry.get("baseline_quadrupole")
        assert isinstance(model, BaselineQuadrupoleAmplitude)

    def test_registry_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown amplitude model"):
            AmplitudeModelRegistry.get("nonexistent_model")

    def test_registry_register_and_retrieve(self):
        class DummyAmplitudeModel(BaseAmplitudeModel):
            def amplitude(self, mode, orbit_state):
                return 1.0 + 0j

        AmplitudeModelRegistry.register("dummy", DummyAmplitudeModel)
        model = AmplitudeModelRegistry.get("dummy")
        assert isinstance(model, DummyAmplitudeModel)


# ---------------------------------------------------------------------------
# WaveformPipeline tests
# ---------------------------------------------------------------------------

class TestWaveformPipeline:
    def setup_method(self):
        self.pipeline = WaveformPipeline()
        self.inspiral = make_inspiral()

    def _run(self, **kwargs):
        cfg = WaveformConfig(**kwargs)
        return self.pipeline.run(self.inspiral, cfg)

    def test_run_returns_four_tuple(self):
        result = self._run()
        assert len(result) == 4

    def test_run_returns_correct_types(self):
        wf, mt, pd, sd = self._run()
        assert isinstance(wf, WaveformResult)
        assert isinstance(mt, ModeAmplitudeTable)
        assert isinstance(pd, PhaseDiagnostics)
        assert sd is None  # time domain only

    def test_dominant_mode_produces_nonzero_h_plus(self):
        wf, *_ = self._run(mode_policy="dominant_only", eta=1e-5)
        assert np.any(np.abs(wf.h_plus) > 0)

    def test_dominant_mode_produces_nonzero_h_cross(self):
        wf, *_ = self._run(mode_policy="dominant_only", eta=1e-5)
        assert np.any(np.abs(wf.h_cross) > 0)

    def test_h_plus_and_h_cross_shape_match_time(self):
        wf, *_ = self._run()
        assert wf.h_plus.shape == self.inspiral.t.shape
        assert wf.h_cross.shape == self.inspiral.t.shape

    def test_phase_monotone_increasing(self):
        wf, *_ = self._run()
        assert np.all(np.diff(wf.phase) >= 0)

    def test_amplitude_envelope_nonnegative(self):
        wf, *_ = self._run()
        assert np.all(wf.amplitude_envelope >= 0)

    def test_amplitude_envelope_equals_abs_strain_complex(self):
        wf, *_ = self._run()
        np.testing.assert_allclose(
            wf.amplitude_envelope,
            np.abs(wf.strain_complex),
            rtol=1e-12,
        )

    def test_mode_policy_change_changes_waveform(self):
        wf_dom, *_ = self._run(mode_policy="dominant_only", eta=1e-4)
        wf_ecc, *_ = self._run(mode_policy="low_order_eccentric", eta=1e-4)
        # Multiple modes (including eccentric) give different h_plus
        assert not np.allclose(wf_dom.h_plus, wf_ecc.h_plus)

    def test_mode_table_lengths_match_modes(self):
        wf, mt, *_ = self._run(mode_policy="fixed_grid", n_max=2)
        assert len(mt.modes) == len(mt.amplitudes) == len(mt.phases)

    def test_mode_table_dominant_amplitude_largest(self):
        """Dominant (0,2) mode should have the largest amplitude in fixed_grid."""
        wf, mt, *_ = self._run(mode_policy="fixed_grid", n_max=2, eta=1e-5)
        dominant_idx = mt.modes.index(HarmonicMode(n=0, m=2, l=2))
        dominant_amp = mt.amplitudes[dominant_idx]
        assert dominant_amp == max(mt.amplitudes)

    def test_spectrum_returned_when_domain_frequency(self):
        _, _, _, sd = self._run(domain="frequency")
        assert isinstance(sd, SpectrumDiagnostics)

    def test_spectrum_returned_when_domain_both(self):
        _, _, _, sd = self._run(domain="both")
        assert isinstance(sd, SpectrumDiagnostics)

    def test_spectrum_none_when_domain_time(self):
        _, _, _, sd = self._run(domain="time")
        assert sd is None

    def test_instantaneous_frequency_property(self):
        wf, *_ = self._run()
        freq = wf.instantaneous_frequency
        assert freq.shape == wf.time.shape
        assert np.all(np.isfinite(freq))

    def test_strain_complex_from_h_plus_h_cross(self):
        wf, *_ = self._run()
        np.testing.assert_array_equal(wf.strain_complex, wf.h_plus + 1j * wf.h_cross)

    def test_user_custom_modes_used(self):
        wf, mt, *_ = self._run(
            mode_policy="user_custom", custom_modes=[(0, 2), (1, 2)]
        )
        assert len(mt.modes) == 2
        assert HarmonicMode(n=0, m=2, l=2) in mt.modes
        assert HarmonicMode(n=1, m=2, l=2) in mt.modes

    def test_phase_diagnostics_shapes(self):
        _, _, pd, _ = self._run()
        n = len(self.inspiral.t)
        assert pd.phi_orbital.shape == (n,)
        assert pd.phi_radial.shape == (n,)
        assert pd.phi_gw.shape == (n,)
        assert pd.omega_phi.shape == (n,)
        assert pd.omega_r.shape == (n,)

    def test_eta_scales_amplitude(self):
        """Larger η → larger strain amplitude."""
        wf1, *_ = self._run(eta=1e-6)
        wf2, *_ = self._run(eta=1e-4)
        assert np.max(np.abs(wf2.h_plus)) > np.max(np.abs(wf1.h_plus))


# ---------------------------------------------------------------------------
# FrequencyDomainPreview tests
# ---------------------------------------------------------------------------

class TestFrequencyDomainPreview:
    def setup_method(self):
        self.preview = FrequencyDomainPreview()
        self.inspiral = make_inspiral()
        self.pipeline = WaveformPipeline()

    def test_spectrum_frequency_axis_positive(self):
        wf, _, _, sd = self.pipeline.run(
            self.inspiral, WaveformConfig(domain="frequency")
        )
        # rfftfreq gives [0, ..., Nyquist] — all non-negative
        assert np.all(sd.frequencies >= 0)

    def test_spectrum_frequency_axis_length(self):
        n = len(self.inspiral.t)
        wf, _, _, sd = self.pipeline.run(
            self.inspiral, WaveformConfig(domain="frequency")
        )
        expected_len = n // 2 + 1
        assert len(sd.frequencies) == expected_len

    def test_spectrum_power_nonnegative(self):
        _, _, _, sd = self.pipeline.run(
            self.inspiral, WaveformConfig(domain="frequency")
        )
        assert np.all(sd.power_plus >= 0)
        assert np.all(sd.power_cross >= 0)

    def test_spectrum_peak_labels_are_strings(self):
        _, _, _, sd = self.pipeline.run(
            self.inspiral, WaveformConfig(domain="frequency")
        )
        for label in sd.peak_mode_labels:
            assert isinstance(label, str)

    def test_spectrum_dominant_peak_labeled_correctly(self):
        """The strongest spectral peak should be labeled (0,2) for dominant mode."""
        _, _, _, sd = self.pipeline.run(
            self.inspiral,
            WaveformConfig(mode_policy="dominant_only", domain="frequency", eta=1e-4),
        )
        # peak_mode_labels are ordered by power; first should be (0,2)
        assert sd.peak_mode_labels[0] == "(0,2)"

    def test_compute_spectrum_directly(self):
        n = 256
        t = np.linspace(0.0, 100.0, n)
        f0 = 0.05
        h_plus = np.sin(2 * np.pi * f0 * t)
        h_cross = np.cos(2 * np.pi * f0 * t)
        modes = [HarmonicMode(n=0, m=2)]
        omega_phi = 2 * np.pi * f0
        sd = self.preview.compute_spectrum(t, h_plus, h_cross, modes, 0.0, omega_phi)
        assert isinstance(sd, SpectrumDiagnostics)
        assert len(sd.frequencies) == n // 2 + 1


# ---------------------------------------------------------------------------
# Export function tests
# ---------------------------------------------------------------------------

class TestExportFunctions:
    def setup_method(self):
        inspiral = make_inspiral()
        pipeline = WaveformPipeline()
        cfg = WaveformConfig(mode_policy="dominant_only", eta=1e-5)
        wf, mt, _, _ = pipeline.run(inspiral, cfg)
        self.wf = wf
        self.mt = mt

    def test_export_csv_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "waveform.csv"
            out = export_waveform_csv(self.wf, path)
            assert out.exists()
            assert out.stat().st_size > 0

    def test_export_csv_has_correct_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "waveform.csv"
            export_waveform_csv(self.wf, path)
            data = np.genfromtxt(path, delimiter=",", names=True)
            assert "time" in data.dtype.names
            assert "h_plus" in data.dtype.names
            assert "h_cross" in data.dtype.names
            assert "phase" in data.dtype.names
            assert "amplitude_envelope" in data.dtype.names

    def test_export_csv_row_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "waveform.csv"
            export_waveform_csv(self.wf, path)
            data = np.genfromtxt(path, delimiter=",", skip_header=1)
            assert len(data) == len(self.wf.time)

    def test_export_npy_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "waveform"
            out = export_waveform_npy(self.wf, path)
            assert out.exists()

    def test_export_npy_contains_correct_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "waveform"
            out = export_waveform_npy(self.wf, path)
            loaded = np.load(out)
            for key in ("time", "h_plus", "h_cross", "phase", "amplitude_envelope"):
                assert key in loaded

    def test_export_npy_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "waveform"
            out = export_waveform_npy(self.wf, path)
            loaded = np.load(out)
            np.testing.assert_array_equal(loaded["h_plus"], self.wf.h_plus)
            np.testing.assert_array_equal(loaded["h_cross"], self.wf.h_cross)

    def test_export_mode_table_json_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "modes.json"
            out = export_mode_table_json(self.mt, path)
            assert out.exists()

    def test_export_mode_table_json_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "modes.json"
            export_mode_table_json(self.mt, path)
            with open(path) as f:
                data = json.load(f)
            assert "modes" in data
            assert "amplitudes" in data
            assert "phases" in data

    def test_export_mode_table_json_lengths_consistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "modes.json"
            export_mode_table_json(self.mt, path)
            with open(path) as f:
                data = json.load(f)
            n = len(data["modes"])
            assert len(data["amplitudes"]) == n
            assert len(data["phases"]) == n

    def test_export_plot_bundle_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "plots"
            result = export_plot_bundle(self.wf, out_dir)
            assert result.is_dir()

    def test_export_plot_bundle_creates_png_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "plots"
            export_plot_bundle(self.wf, out_dir)
            assert (out_dir / "waveform.png").exists()
            assert (out_dir / "phase.png").exists()
            assert (out_dir / "amplitude.png").exists()


# ---------------------------------------------------------------------------
# WaveformResult property tests
# ---------------------------------------------------------------------------

class TestWaveformResultProperties:
    def setup_method(self):
        inspiral = make_inspiral()
        pipeline = WaveformPipeline()
        cfg = WaveformConfig()
        wf, _, _, _ = pipeline.run(inspiral, cfg)
        self.wf = wf

    def test_strain_complex_is_h_plus_plus_i_h_cross(self):
        expected = self.wf.h_plus + 1j * self.wf.h_cross
        np.testing.assert_array_equal(self.wf.strain_complex, expected)

    def test_instantaneous_frequency_same_length_as_time(self):
        freq = self.wf.instantaneous_frequency
        assert len(freq) == len(self.wf.time)

    def test_instantaneous_frequency_all_finite(self):
        freq = self.wf.instantaneous_frequency
        assert np.all(np.isfinite(freq))

    def test_instantaneous_frequency_positive(self):
        """For a monotonically increasing phase, frequency should be positive."""
        freq = self.wf.instantaneous_frequency
        assert np.all(freq >= 0)
