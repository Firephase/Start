"""Results storage: save and load inspiral run artifacts to/from disk."""

from pathlib import Path
import json

import numpy as np

from emri_lab.domain.models import InspiralResult, RunMetadata

OUTPUT_DIR = Path(__file__).parent.parent.parent.parent.parent / "output" / "runs"


def save_run(
    result: InspiralResult,
    meta: RunMetadata,
    output_dir: Path | None = None,
) -> Path:
    """Save inspiral result and metadata to disk.

    Creates a subdirectory named by ``meta.run_id`` under ``output_dir``
    (or the default ``output/runs/`` directory) and writes:

    - ``trajectory.npz``  — NumPy compressed archive with arrays t, p, e, E, L, r_circ.
    - ``metadata.json``   — JSON with run bookkeeping and orbit/config parameters.

    Parameters
    ----------
    result : InspiralResult
        Inspiral trajectory arrays and termination info.
    meta : RunMetadata
        Bookkeeping metadata for this run.
    output_dir : Path, optional
        Base output directory. Defaults to ``output/runs/`` relative to the repo root.

    Returns
    -------
    Path
        Path to the run directory that was created.
    """
    base = output_dir or OUTPUT_DIR
    run_dir = base / meta.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save trajectory as npz
    np.savez(
        run_dir / "trajectory.npz",
        t=result.t,
        p=result.p_arr,
        e=result.e_arr,
        E=result.E_arr,
        L=result.L_arr,
        r_circ=result.r_circ,
    )

    # Save metadata as JSON
    meta_dict = {
        "run_id": meta.run_id,
        "timestamp": meta.timestamp,
        "duration_s": meta.duration_s,
        "plunged": result.plunged,
        "message": result.message,
        "orbit": {
            "p": meta.orbit.p,
            "e": meta.orbit.e,
            "chi_r0": meta.orbit.chi_r0,
        },
        "config": {
            "eta": meta.config.eta,
            "flux_model": meta.config.flux_model.value,
            "use_horizon_flux": meta.config.use_horizon_flux,
        },
    }
    with open(run_dir / "metadata.json", "w") as f:
        json.dump(meta_dict, f, indent=2)

    return run_dir


def load_run(run_id: str, output_dir: Path | None = None) -> dict:
    """Load a saved run by ID.

    Parameters
    ----------
    run_id : str
        Run identifier (name of the run subdirectory).
    output_dir : Path, optional
        Base output directory. Defaults to ``output/runs/`` relative to the repo root.

    Returns
    -------
    dict
        Dictionary with keys:
        - ``"trajectory"``  : dict of arrays (t, p, e, E, L, r_circ).
        - ``"metadata"``    : dict loaded from ``metadata.json``.

    Raises
    ------
    FileNotFoundError
        If the run directory or its files do not exist.
    """
    base = output_dir or OUTPUT_DIR
    run_dir = base / run_id
    traj = np.load(run_dir / "trajectory.npz")
    with open(run_dir / "metadata.json") as f:
        meta = json.load(f)
    return {"trajectory": dict(traj), "metadata": meta}
