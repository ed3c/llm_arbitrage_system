from __future__ import annotations

from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.bundle_io import (
    remove_path,
    render_markdown_report,
    write_bytes,
    write_checksums,
    write_json,
    write_text,
)
from llm_arbitrage_system.experiments.bundle_types import (
    BundleVerificationResult,
    BundleWorkspace,
)
from llm_arbitrage_system.experiments.bundle_verify import verify_bundle
from llm_arbitrage_system.experiments.config import ExperimentConfigSnapshot
from llm_arbitrage_system.experiments.dataset import DatasetSnapshot
from llm_arbitrage_system.experiments.manifest import ExperimentManifest


def prepare_bundle_workspace(
    output_root: Path,
    experiment_id: str,
    *,
    force: bool = False,
) -> BundleWorkspace:
    root = output_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / experiment_id
    staging = root / f".{experiment_id}.staging"
    if target.exists():
        if not force:
            raise FileExistsError(f"experiment bundle already exists: {target}")
        remove_path(target)
    if staging.exists():
        remove_path(staging)
    staging.mkdir(parents=True)
    return BundleWorkspace(output_root=root, target=target, staging=staging)


def write_bundle_inputs(
    staging: Path,
    dataset: DatasetSnapshot,
    config: ExperimentConfigSnapshot,
) -> None:
    input_directory = staging / "inputs"
    input_directory.mkdir(parents=True, exist_ok=True)
    write_bytes(input_directory / "dataset.source.jsonl", dataset.source_bytes)
    write_bytes(input_directory / "dataset.canonical.jsonl", dataset.canonical_jsonl)
    write_bytes(input_directory / "config.source.yaml", config.source_bytes)
    write_bytes(input_directory / "config.canonical.json", config.canonical_bytes)


def write_bundle_reports(
    staging: Path,
    manifest: ExperimentManifest,
    replay_report: dict[str, int],
    performance_report: dict[str, Any],
    *,
    sqlite_integrity: str,
) -> None:
    write_json(staging / "manifest.json", manifest.as_dict())
    write_json(staging / "replay_report.json", replay_report)
    write_json(staging / "performance_report.json", performance_report)
    write_text(
        staging / "report.md",
        render_markdown_report(
            manifest,
            replay_report,
            performance_report,
            sqlite_integrity=sqlite_integrity,
        ),
    )


def finalize_bundle(workspace: BundleWorkspace) -> BundleVerificationResult:
    write_checksums(workspace.staging)
    verification = verify_bundle(workspace.staging)
    workspace.staging.replace(workspace.target)
    return BundleVerificationResult(
        bundle_path=workspace.target,
        experiment_id=verification.experiment_id,
        run_id=verification.run_id,
        file_count=verification.file_count,
        sqlite_integrity=verification.sqlite_integrity,
        run_status=verification.run_status,
    )


__all__ = [
    "BundleVerificationResult",
    "BundleWorkspace",
    "finalize_bundle",
    "prepare_bundle_workspace",
    "render_markdown_report",
    "verify_bundle",
    "write_bundle_inputs",
    "write_bundle_reports",
    "write_checksums",
]
