from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.canonical import (
    canonical_datetime,
    canonical_json_bytes,
    sha256_hex,
)
from llm_arbitrage_system.experiments.config import ExperimentConfigSnapshot
from llm_arbitrage_system.experiments.dataset import DatasetSnapshot

_BUNDLE_SCHEMA_VERSION = 1
_PACKAGE_NAME = "llm-arbitrage-system"


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    experiment_id: str
    run_id: str
    code_revision: str
    package_version: str
    dataset_source_sha256: str
    dataset_semantic_sha256: str
    config_source_sha256: str
    config_canonical_sha256: str
    event_count: int
    first_event_at: str
    last_event_at: str

    def identity_payload(self) -> dict[str, Any]:
        return {
            "bundle_schema_version": _BUNDLE_SCHEMA_VERSION,
            "dataset_semantic_sha256": self.dataset_semantic_sha256,
            "config_canonical_sha256": self.config_canonical_sha256,
            "code_revision": self.code_revision,
            "package_version": self.package_version,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_schema_version": _BUNDLE_SCHEMA_VERSION,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "code_revision": self.code_revision,
            "package_version": self.package_version,
            "dataset": {
                "source_sha256": self.dataset_source_sha256,
                "semantic_sha256": self.dataset_semantic_sha256,
                "event_count": self.event_count,
                "first_event_at": self.first_event_at,
                "last_event_at": self.last_event_at,
            },
            "configuration": {
                "source_sha256": self.config_source_sha256,
                "canonical_sha256": self.config_canonical_sha256,
            },
            "reproducibility_scope": (
                "semantic inputs, behavior configuration, code revision, and deterministic identifiers"
            ),
            "notes": [
                (
                    "Operational SQLite timestamps are evidence metadata and are not part "
                    "of the experiment identity."
                ),
                "The bundle verifies integrity and provenance; it does not establish strategy profitability.",
            ],
        }


def build_experiment_manifest(
    dataset: DatasetSnapshot,
    config: ExperimentConfigSnapshot,
    *,
    code_revision: str,
    package_version: str | None = None,
) -> ExperimentManifest:
    normalized_revision = code_revision.strip()
    if not normalized_revision:
        raise ValueError("code_revision cannot be empty")
    if len(normalized_revision) > 160:
        raise ValueError("code_revision is too long")
    resolved_version = package_version or installed_package_version()
    identity = {
        "bundle_schema_version": _BUNDLE_SCHEMA_VERSION,
        "dataset_semantic_sha256": dataset.semantic_sha256,
        "config_canonical_sha256": config.canonical_sha256,
        "code_revision": normalized_revision,
        "package_version": resolved_version,
    }
    digest = sha256_hex(canonical_json_bytes(identity))
    return ExperimentManifest(
        experiment_id=f"exp-{digest[:40]}",
        run_id=f"run-{digest[:32]}",
        code_revision=normalized_revision,
        package_version=resolved_version,
        dataset_source_sha256=dataset.source_sha256,
        dataset_semantic_sha256=dataset.semantic_sha256,
        config_source_sha256=config.source_sha256,
        config_canonical_sha256=config.canonical_sha256,
        event_count=dataset.event_count,
        first_event_at=canonical_datetime(dataset.first_timestamp),
        last_event_at=canonical_datetime(dataset.last_timestamp),
    )


def experiment_id_from_identity(identity: dict[str, Any]) -> str:
    digest = sha256_hex(canonical_json_bytes(identity))
    return f"exp-{digest[:40]}"


def installed_package_version() -> str:
    try:
        return version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.1.0"


def resolve_code_revision(explicit: str | None, *, cwd: Path | None = None) -> str:
    if explicit is not None and explicit.strip():
        return explicit.strip()
    github_sha = os.environ.get("GITHUB_SHA")
    if github_sha:
        return github_sha.strip()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unversioned"
    revision = completed.stdout.strip()
    return revision if completed.returncode == 0 and revision else "unversioned"
