"""Run bundle format — standardized output package for reproducibility."""
from __future__ import annotations
import json
import zipfile
import yaml
import numpy as np
from pathlib import Path
from dataclasses import dataclass

@dataclass
class RunBundle:
    """All outputs for a single simulation run in a structured directory."""
    run_id: str
    base_dir: Path

    @property
    def metadata_path(self) -> Path:
        return self.base_dir / "metadata.json"

    @property
    def config_path(self) -> Path:
        return self.base_dir / "config.yaml"

    @property
    def trajectory_path(self) -> Path:
        return self.base_dir / "trajectory.csv"

    @property
    def evolution_path(self) -> Path:
        return self.base_dir / "evolution.csv"

    @property
    def waveform_path(self) -> Path:
        return self.base_dir / "waveform.csv"

    @property
    def modes_path(self) -> Path:
        return self.base_dir / "modes.json"

    @property
    def diagnostics_path(self) -> Path:
        return self.base_dir / "diagnostics.json"

def save_run_bundle(
    run_id: str,
    metadata: dict,
    config: dict,
    trajectory: dict,
    base_dir: Path,
    waveform_data: dict | None = None,
    modes_data: dict | None = None,
    diagnostics: dict | None = None,
) -> RunBundle:
    """Save all run artifacts in the standard run-bundle directory structure."""
    bundle_dir = base_dir / run_id
    bundle_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = bundle_dir / "plots"
    plots_dir.mkdir(exist_ok=True)
    logs_dir = bundle_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    # metadata.json
    with open(bundle_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # config.yaml
    with open(bundle_dir / "config.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    # trajectory.csv — (t, p, e, E, L)
    if trajectory:
        keys = list(trajectory.keys())
        with open(bundle_dir / "trajectory.csv", "w") as f:
            f.write(",".join(keys) + "\n")
            arrays = [np.asarray(trajectory[k]) for k in keys]
            n = min(len(a) for a in arrays)
            for i in range(n):
                f.write(",".join(str(a[i]) for a in arrays) + "\n")

    # waveform.csv
    if waveform_data:
        wf_keys = list(waveform_data.keys())
        with open(bundle_dir / "waveform.csv", "w") as f:
            f.write(",".join(wf_keys) + "\n")
            arrays = [np.asarray(waveform_data[k]) for k in wf_keys]
            n = min(len(a) for a in arrays)
            for i in range(n):
                f.write(",".join(str(a[i]) for a in arrays) + "\n")

    # modes.json
    if modes_data:
        with open(bundle_dir / "modes.json", "w") as f:
            json.dump(modes_data, f, indent=2)

    # diagnostics.json
    if diagnostics:
        with open(bundle_dir / "diagnostics.json", "w") as f:
            json.dump(diagnostics, f, indent=2)

    return RunBundle(run_id=run_id, base_dir=bundle_dir)

def load_run_bundle(bundle_dir: Path) -> dict:
    """Load all artifacts from a run bundle directory."""
    result = {}
    meta_path = bundle_dir / "metadata.json"
    if meta_path.exists():
        result["metadata"] = json.loads(meta_path.read_text())

    config_path = bundle_dir / "config.yaml"
    if config_path.exists():
        result["config"] = yaml.safe_load(config_path.read_text())

    for name in ["modes", "diagnostics"]:
        p = bundle_dir / f"{name}.json"
        if p.exists():
            result[name] = json.loads(p.read_text())

    for name in ["trajectory", "waveform", "evolution"]:
        p = bundle_dir / f"{name}.csv"
        if p.exists():
            with open(p) as f:
                header = f.readline().strip().split(",")
                rows = [line.strip().split(",") for line in f if line.strip()]
            if rows:
                result[name] = {h: [float(r[i]) if i < len(r) else 0.0 for r in rows]
                                for i, h in enumerate(header)}

    return result

def zip_bundle(bundle_dir: Path, out_path: Path | None = None) -> Path:
    """Zip the run bundle directory into a single archive."""
    out_path = out_path or bundle_dir.parent / f"{bundle_dir.name}.zip"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in bundle_dir.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(bundle_dir.parent))
    return out_path
