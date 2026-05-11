"""Detector projection adapter — placeholder for future detector response layer."""
from __future__ import annotations
import numpy as np

class DetectorProjectionAdapter:
    """Project GW strain into a detector's antenna response.

    This is a placeholder interface. The full implementation would require
    detector geometry, noise curves, and matched filtering infrastructure.
    """

    SUPPORTED_DETECTORS = ["LISA", "ET", "CE", "generic"]

    def project(self, waveform, detector_cfg: dict) -> dict:
        """Apply antenna response pattern to h+, hx.

        waveform: WaveformResult with h_plus, h_cross, time
        detector_cfg: {"detector": "LISA", "F_plus": float, "F_cross": float, ...}

        Returns dict with projected strain and metadata.
        """
        F_plus = detector_cfg.get("F_plus", 1.0)
        F_cross = detector_cfg.get("F_cross", 0.0)
        detector = detector_cfg.get("detector", "generic")

        # h_obs = F+ h+ + Fx hx
        h_obs = F_plus * waveform.h_plus + F_cross * waveform.h_cross

        return {
            "time": waveform.time,
            "h_observed": h_obs,
            "detector": detector,
            "F_plus": F_plus,
            "F_cross": F_cross,
            "SNR_proxy": float(np.sqrt(np.trapezoid(h_obs**2, waveform.time))),
            "note": "placeholder — no noise curve applied",
        }

    def get_detector_metadata(self, detector_name: str) -> dict:
        """Return metadata for a named detector configuration."""
        defaults = {
            "LISA": {"arm_length_Gm": 2.5e6, "frequency_band": [1e-4, 1e-1], "note": "Space-based"},
            "ET": {"arm_length_km": 10.0, "frequency_band": [1.0, 1e4], "note": "Einstein Telescope"},
            "CE": {"arm_length_km": 40.0, "frequency_band": [5.0, 5e3], "note": "Cosmic Explorer"},
            "generic": {"note": "Placeholder detector"},
        }
        return defaults.get(detector_name, {"note": "Unknown detector"})
