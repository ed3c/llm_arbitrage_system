from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.manifest import ExperimentManifest

CHECKSUM_FILE = "checksums.sha256"


def write_checksums(bundle_path: Path) -> None:
    files = bundle_files(bundle_path, include_checksum=False)
    lines = [
        f"{file_sha256(path)}  {path.relative_to(bundle_path).as_posix()}"
        for path in files
    ]
    write_text(bundle_path / CHECKSUM_FILE, "\n".join(lines) + "\n")


def render_markdown_report(
    manifest: ExperimentManifest,
    replay_report: dict[str, int],
    performance_report: dict[str, Any],
    *,
    sqlite_integrity: str,
) -> str:
    metrics = performance_report.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    assumptions = performance_report.get("assumptions", [])
    if not isinstance(assumptions, list):
        assumptions = []
    lines = [
        f"# Experiment {manifest.experiment_id}",
        "",
        "## Provenance",
        "",
        f"- Run ID: `{manifest.run_id}`",
        f"- Code revision: `{manifest.code_revision}`",
        f"- Package version: `{manifest.package_version}`",
        f"- Dataset semantic SHA-256: `{manifest.dataset_semantic_sha256}`",
        f"- Configuration SHA-256: `{manifest.config_canonical_sha256}`",
        f"- Events: {manifest.event_count}",
        f"- Event interval: `{manifest.first_event_at}` to `{manifest.last_event_at}`",
        f"- SQLite integrity: `{sqlite_integrity}`",
        "",
        "## Replay state counters",
        "",
    ]
    for key in sorted(replay_report):
        lines.append(f"- {key}: {replay_report[key]}")
    lines.extend(["", "## Evidence-supported performance fields", ""])
    for key in sorted(metrics):
        lines.append(f"- {key}: {metrics[key]}")
    lines.extend(["", "## Evidence boundaries", ""])
    for assumption in assumptions:
        lines.append(f"- {assumption}")
    lines.extend(
        [
            "- Bundle integrity and content addressing do not establish profitability.",
            "- SQLite operational timestamps are excluded from the experiment identity.",
            "",
        ]
    )
    return "\n".join(lines)


def bundle_files(bundle_path: Path, *, include_checksum: bool) -> list[Path]:
    result: list[Path] = []
    for path in bundle_path.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"bundle cannot contain symbolic links: {path}")
        if path.is_file() and (include_checksum or path.name != CHECKSUM_FILE):
            result.append(path)
    return sorted(result, key=lambda path: path.relative_to(bundle_path).as_posix())


def read_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line:
            continue
        digest, separator, relative_name = raw_line.partition("  ")
        if (
            not separator
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError(f"invalid checksum line {line_number}")
        pure_path = PurePosixPath(relative_name)
        if (
            pure_path.is_absolute()
            or ".." in pure_path.parts
            or relative_name == CHECKSUM_FILE
        ):
            raise ValueError(f"unsafe checksum path on line {line_number}")
        if relative_name in result:
            raise ValueError(f"duplicate checksum path: {relative_name}")
        result[relative_name] = digest
    if not result:
        raise ValueError("checksum file is empty")
    return result


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def write_json(path: Path, payload: object) -> None:
    write_bytes(path, canonical_json_bytes(payload) + b"\n")


def write_text(path: Path, value: str) -> None:
    write_bytes(path, value.encode("utf-8"))


def write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
