"""Experiment registry: single source of truth for all runs."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from datetime import datetime

_DEFAULT_REGISTRY_PATH = Path(__file__).parent.parent.parent.parent.parent / "output" / "registry.json"

class ExperimentRegistry:
    """Persistent registry of simulation runs stored as a JSON file."""

    def __init__(self, registry_path: Path | None = None):
        self._path = registry_path or _DEFAULT_REGISTRY_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("[]")

    def _load(self) -> list[dict]:
        try:
            return json.loads(self._path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, records: list[dict]) -> None:
        self._path.write_text(json.dumps(records, indent=2))

    def register_run(self, metadata: dict) -> str:
        """Register a new run. Returns the run_id."""
        records = self._load()
        run_id = metadata.get("run_id") or str(uuid.uuid4())[:8]
        record = {
            "run_id": run_id,
            "registered_at": datetime.utcnow().isoformat(),
            **metadata,
        }
        records.append(record)
        self._save(records)
        return run_id

    def list_runs(self, filters: dict | None = None) -> list[dict]:
        """List all runs, optionally filtered by metadata fields."""
        records = self._load()
        if not filters:
            return records
        result = []
        for rec in records:
            if all(str(rec.get(k, "")) == str(v) for k, v in filters.items()):
                result.append(rec)
        return result

    def get_run(self, run_id: str) -> dict | None:
        """Retrieve a single run by ID."""
        for rec in self._load():
            if rec.get("run_id") == run_id:
                return rec
        return None

    def compare_runs(self, run_ids: list[str]) -> dict:
        """Return side-by-side metadata for given run IDs."""
        runs = {rid: self.get_run(rid) for rid in run_ids}
        return {
            "run_ids": run_ids,
            "runs": runs,
            "found": [rid for rid, v in runs.items() if v is not None],
            "missing": [rid for rid, v in runs.items() if v is None],
        }

    def delete_run(self, run_id: str) -> bool:
        """Remove a run record from the registry."""
        records = self._load()
        new_records = [r for r in records if r.get("run_id") != run_id]
        if len(new_records) < len(records):
            self._save(new_records)
            return True
        return False
