from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BundleWorkspace:
    output_root: Path
    target: Path
    staging: Path


@dataclass(frozen=True, slots=True)
class BundleVerificationResult:
    bundle_path: Path
    experiment_id: str
    run_id: str
    file_count: int
    sqlite_integrity: str
    run_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_path": str(self.bundle_path),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "file_count": self.file_count,
            "sqlite_integrity": self.sqlite_integrity,
            "run_status": self.run_status,
        }
