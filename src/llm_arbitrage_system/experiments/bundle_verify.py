from __future__ import annotations

import sqlite3
from pathlib import Path

from llm_arbitrage_system.experiments.bundle_io import (
    CHECKSUM_FILE,
    bundle_files,
    file_sha256,
    read_checksums,
)
from llm_arbitrage_system.experiments.bundle_types import BundleVerificationResult
from llm_arbitrage_system.experiments.bundle_validation import (
    json_object,
    manifest_identity,
    required_string,
    verify_inputs,
)
from llm_arbitrage_system.experiments.manifest import experiment_id_from_identity


def verify_bundle(bundle_path: Path) -> BundleVerificationResult:
    root = bundle_path.resolve()
    expected = _verify_checksums(root)
    manifest = json_object((root / "manifest.json").read_text(encoding="utf-8"))
    experiment_id = required_string(manifest, "experiment_id")
    run_id = required_string(manifest, "run_id")
    identity = manifest_identity(manifest)
    if experiment_id_from_identity(identity) != experiment_id:
        raise ValueError("manifest experiment_id does not match its identity fields")
    verify_inputs(root, manifest, identity)
    sqlite_integrity, recorded_run_id, run_status = _verify_sqlite(
        root / "evidence.sqlite3"
    )
    if recorded_run_id != run_id:
        raise ValueError("SQLite run_id does not match manifest")
    if run_status != "completed":
        raise ValueError(f"SQLite replay run is not completed: {run_status}")
    return BundleVerificationResult(
        bundle_path=root,
        experiment_id=experiment_id,
        run_id=run_id,
        file_count=len(expected) + 1,
        sqlite_integrity=sqlite_integrity,
        run_status=run_status,
    )


def _verify_checksums(root: Path) -> dict[str, str]:
    checksum_path = root / CHECKSUM_FILE
    if not checksum_path.is_file():
        raise ValueError(f"missing {CHECKSUM_FILE}")
    expected = read_checksums(checksum_path)
    actual_files = bundle_files(root, include_checksum=False)
    actual_names = {path.relative_to(root).as_posix() for path in actual_files}
    if set(expected) != actual_names:
        missing = sorted(set(expected) - actual_names)
        unexpected = sorted(actual_names - set(expected))
        raise ValueError(
            f"bundle file set mismatch; missing={missing or []}, "
            f"unexpected={unexpected or []}"
        )
    for relative_name, expected_digest in expected.items():
        if file_sha256(root / relative_name) != expected_digest:
            raise ValueError(f"checksum mismatch: {relative_name}")
    return expected


def _verify_sqlite(path: Path) -> tuple[str, str, str]:
    if not path.is_file():
        raise ValueError("missing evidence.sqlite3")
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    try:
        integrity_row = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity_row is None:
            raise ValueError("SQLite did not return an integrity result")
        integrity = str(integrity_row[0])
        if integrity != "ok":
            raise ValueError(f"SQLite integrity check failed: {integrity}")
        rows = connection.execute(
            "SELECT run_id, status FROM replay_runs ORDER BY run_id"
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("evidence database must contain exactly one replay run")
        return integrity, str(rows[0][0]), str(rows[0][1])
    finally:
        connection.close()
