"""Dataset builder for collecting waveform/trajectory data from multiple runs."""
from __future__ import annotations
import json
import numpy as np
from pathlib import Path
from emri_lab.io.results_store import load_run

class DatasetBuilder:
    """Collect and package simulation results into analysis-ready datasets."""

    def build_trajectory_dataset(self, run_ids: list[str], out_path: str) -> str:
        """Collect trajectory arrays from multiple runs into a single npz file.

        Returns the path to the saved dataset.
        """
        out_path = str(out_path)
        if not out_path.endswith(".npz"):
            out_path += ".npz"

        arrays = {}
        for run_id in run_ids:
            try:
                data = load_run(run_id)
                traj = data["trajectory"]
                for key, arr in traj.items():
                    arrays[f"{run_id}__{key}"] = arr
                arrays[f"{run_id}__meta"] = np.array([json.dumps(data["metadata"])], dtype=object)
            except FileNotFoundError:
                pass  # Skip missing runs

        np.savez(out_path, **arrays)
        return out_path

    def build_waveform_dataset(self, run_ids: list[str], out_path: str) -> str:
        """Build a dataset of waveform parameters (p, e, eta, plunged) as a CSV summary."""
        out_path = str(out_path)
        if not out_path.endswith(".csv"):
            out_path += ".csv"

        rows = []
        for run_id in run_ids:
            try:
                data = load_run(run_id)
                meta = data["metadata"]
                traj = data["trajectory"]
                rows.append({
                    "run_id": run_id,
                    "p0": meta["orbit"]["p"],
                    "e0": meta["orbit"]["e"],
                    "eta": meta["config"]["eta"],
                    "flux_model": meta["config"]["flux_model"],
                    "plunged": meta["plunged"],
                    "n_points": len(traj["t"]),
                    "t_final": float(traj["t"][-1]) if len(traj["t"]) > 0 else 0.0,
                    "p_final": float(traj["p"][-1]) if "p" in traj and len(traj["p"]) > 0 else 0.0,
                })
            except FileNotFoundError:
                rows.append({"run_id": run_id, "status": "missing"})

        # Write CSV
        if rows:
            keys = list(rows[0].keys())
            with open(out_path, "w") as f:
                f.write(",".join(keys) + "\n")
                for row in rows:
                    f.write(",".join(str(row.get(k, "")) for k in keys) + "\n")

        return out_path

    def export_summary_json(self, run_ids: list[str], out_path: str) -> str:
        """Export a JSON summary of all runs."""
        out_path = str(out_path)
        summary = []
        for run_id in run_ids:
            try:
                data = load_run(run_id)
                summary.append(data["metadata"])
            except FileNotFoundError:
                summary.append({"run_id": run_id, "status": "missing"})
        with open(out_path, "w") as f:
            json.dump(summary, f, indent=2)
        return out_path
