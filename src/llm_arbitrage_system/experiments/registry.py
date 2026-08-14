from __future__ import annotations

import base64
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization

from llm_arbitrage_system.experiments.bundle_validation import json_object, nested_string, required_string
from llm_arbitrage_system.experiments.evaluation import load_evaluation_record, load_experiment_matrix
from llm_arbitrage_system.experiments.lineage import load_lineage_manifest
from llm_arbitrage_system.experiments.signing import (
    load_public_key,
    public_key_identity,
    verify_attestation,
)


@dataclass(frozen=True, slots=True)
class RegistrySummary:
    integrity: str
    trusted_keys: int
    lineage_nodes: int
    lineage_edges: int
    experiments: int
    evaluations: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "integrity": self.integrity,
            "trusted_keys": self.trusted_keys,
            "lineage_nodes": self.lineage_nodes,
            "lineage_edges": self.lineage_edges,
            "experiments": self.experiments,
            "evaluations": self.evaluations,
        }


class ExperimentRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._closed = False
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trusted_keys (
              key_id TEXT PRIMARY KEY, algorithm TEXT NOT NULL,
              public_key_base64 TEXT NOT NULL, label TEXT, added_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lineage_nodes (
              lineage_id TEXT PRIMARY KEY, dataset_semantic_sha256 TEXT NOT NULL,
              kind TEXT NOT NULL, manifest_json TEXT NOT NULL, imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lineage_edges (
              lineage_id TEXT NOT NULL, parent_lineage_id TEXT NOT NULL,
              PRIMARY KEY(lineage_id,parent_lineage_id),
              FOREIGN KEY(lineage_id) REFERENCES lineage_nodes(lineage_id),
              FOREIGN KEY(parent_lineage_id) REFERENCES lineage_nodes(lineage_id)
            );
            CREATE TABLE IF NOT EXISTS experiments (
              experiment_id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE,
              bundle_path TEXT NOT NULL, bundle_root_sha256 TEXT NOT NULL,
              signer_key_id TEXT NOT NULL, trusted INTEGER NOT NULL,
              lineage_id TEXT, dataset_semantic_sha256 TEXT NOT NULL,
              config_canonical_sha256 TEXT NOT NULL, manifest_json TEXT NOT NULL,
              replay_report_json TEXT NOT NULL, performance_report_json TEXT NOT NULL,
              imported_at TEXT NOT NULL,
              FOREIGN KEY(lineage_id) REFERENCES lineage_nodes(lineage_id)
            );
            CREATE TABLE IF NOT EXISTS evaluations (
              evaluation_id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL UNIQUE,
              matrix_sha256 TEXT NOT NULL, candidate_id TEXT NOT NULL,
              candidate_config_sha256 TEXT NOT NULL, test_semantic_sha256 TEXT NOT NULL,
              train_semantic_sha256 TEXT NOT NULL, window_index INTEGER NOT NULL,
              evaluation_json TEXT NOT NULL, registered_at TEXT NOT NULL,
              FOREIGN KEY(experiment_id) REFERENCES experiments(experiment_id)
            );
            CREATE INDEX IF NOT EXISTS idx_eval_matrix_candidate
              ON evaluations(matrix_sha256,candidate_id,window_index);
            """
        )
        self._connection.commit()

    def trust_public_key(self, path: Path, *, label: str | None = None) -> dict[str, Any]:
        key = load_public_key(path)
        identity = public_key_identity(key)
        raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        encoded = base64.b64encode(raw).decode("ascii")
        row = self._connection.execute(
            "SELECT public_key_base64 FROM trusted_keys WHERE key_id=?", (identity.key_id,)
        ).fetchone()
        if row is not None:
            if str(row["public_key_base64"]) != encoded:
                raise RuntimeError("trusted key ID collision")
            return {"key_id": identity.key_id, "status": "already_trusted"}
        self._connection.execute(
            "INSERT INTO trusted_keys VALUES (?,?,?,?,?)",
            (identity.key_id, identity.algorithm, encoded, label, _now()),
        )
        self._connection.commit()
        return {"key_id": identity.key_id, "label": label, "status": "trusted"}

    def import_lineage(self, path: Path) -> dict[str, Any]:
        snapshot = load_lineage_manifest(path)
        manifest = snapshot.manifest
        for parent in manifest.parents:
            if self._connection.execute(
                "SELECT 1 FROM lineage_nodes WHERE lineage_id=?", (parent,)
            ).fetchone() is None:
                raise ValueError(f"lineage parent is not registered: {parent}")
        text = _json(manifest.as_dict())
        row = self._connection.execute(
            "SELECT manifest_json FROM lineage_nodes WHERE lineage_id=?",
            (manifest.lineage_id,),
        ).fetchone()
        if row is not None:
            if str(row["manifest_json"]) != text:
                raise RuntimeError("lineage ID conflict")
            return {"lineage_id": manifest.lineage_id, "status": "already_registered"}
        with self._connection:
            self._connection.execute(
                "INSERT INTO lineage_nodes VALUES (?,?,?,?,?)",
                (
                    manifest.lineage_id,
                    manifest.dataset_semantic_sha256,
                    manifest.kind,
                    text,
                    _now(),
                ),
            )
            for parent in manifest.parents:
                self._connection.execute(
                    "INSERT INTO lineage_edges VALUES (?,?)", (manifest.lineage_id, parent)
                )
        return {"lineage_id": manifest.lineage_id, "status": "registered"}

    def import_bundle(
        self,
        bundle_path: Path,
        attestation_path: Path,
        *,
        allow_untrusted: bool = False,
    ) -> dict[str, Any]:
        verified = verify_attestation(bundle_path, attestation_path)
        trusted = self._connection.execute(
            "SELECT 1 FROM trusted_keys WHERE key_id=?", (verified.key_id,)
        ).fetchone() is not None
        if not trusted and not allow_untrusted:
            raise PermissionError(f"attestation signer is not trusted: {verified.key_id}")
        bundle = bundle_path.resolve()
        manifest = json_object((bundle / "manifest.json").read_text(encoding="utf-8"))
        experiment_id = required_string(manifest, "experiment_id")
        run_id = required_string(manifest, "run_id")
        dataset_hash = nested_string(manifest, "dataset", "semantic_sha256")
        config_hash = nested_string(manifest, "configuration", "canonical_sha256")
        lineage_id = verified.lineage_id
        if lineage_id is not None:
            row = self._connection.execute(
                "SELECT dataset_semantic_sha256 FROM lineage_nodes WHERE lineage_id=?",
                (lineage_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"attested lineage is not registered: {lineage_id}")
            if str(row["dataset_semantic_sha256"]) != dataset_hash:
                raise ValueError("attested lineage dataset hash does not match bundle")
        existing = self._connection.execute(
            "SELECT bundle_root_sha256,signer_key_id FROM experiments WHERE experiment_id=?",
            (experiment_id,),
        ).fetchone()
        if existing is not None:
            if (
                str(existing["bundle_root_sha256"]) != verified.bundle_root_sha256
                or str(existing["signer_key_id"]) != verified.key_id
            ):
                raise RuntimeError("experiment ID conflicts with immutable evidence")
            return {"experiment_id": experiment_id, "status": "already_registered"}
        replay = json_object((bundle / "replay_report.json").read_text(encoding="utf-8"))
        performance = json_object((bundle / "performance_report.json").read_text(encoding="utf-8"))
        self._connection.execute(
            """INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                experiment_id,
                run_id,
                str(bundle),
                verified.bundle_root_sha256,
                verified.key_id,
                int(trusted),
                lineage_id,
                dataset_hash,
                config_hash,
                _json(manifest),
                _json(replay),
                _json(performance),
                _now(),
            ),
        )
        self._connection.commit()
        return {
            "experiment_id": experiment_id,
            "run_id": run_id,
            "signer_key_id": verified.key_id,
            "trusted": trusted,
            "lineage_id": lineage_id,
            "status": "registered",
        }

    def register_evaluation(
        self,
        *,
        matrix_path: Path,
        evaluation_id: str,
        bundle_path: Path,
        attestation_path: Path,
        allow_untrusted: bool = False,
    ) -> dict[str, Any]:
        imported = self.import_bundle(
            bundle_path, attestation_path, allow_untrusted=allow_untrusted
        )
        matrix = load_experiment_matrix(matrix_path)
        planned = matrix.evaluation(evaluation_id)
        record = load_evaluation_record(bundle_path)
        checks = {
            "evaluation_id": evaluation_id,
            "matrix_sha256": matrix.semantic_sha256,
            "candidate_id": planned.candidate_id,
            "candidate_config_sha256": planned.candidate_config_sha256,
            "test_semantic_sha256": planned.test_semantic_sha256,
            "train_semantic_sha256": planned.train_semantic_sha256,
            "window": planned.window,
        }
        for key, expected in checks.items():
            if record.get(key) != expected:
                raise ValueError(f"bundle evaluation {key} does not match matrix plan")
        experiment_id = str(imported["experiment_id"])
        row = self._connection.execute(
            "SELECT dataset_semantic_sha256,config_canonical_sha256 FROM experiments WHERE experiment_id=?",
            (experiment_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("registered experiment is missing")
        if str(row["dataset_semantic_sha256"]) != planned.test_semantic_sha256:
            raise ValueError("experiment dataset is not the planned test slice")
        if str(row["config_canonical_sha256"]) != planned.candidate_config_sha256:
            raise ValueError("experiment config is not the planned candidate")
        existing = self._connection.execute(
            "SELECT experiment_id FROM evaluations WHERE evaluation_id=?", (evaluation_id,)
        ).fetchone()
        if existing is not None:
            if str(existing["experiment_id"]) != experiment_id:
                raise RuntimeError("evaluation ID conflict")
            return {"evaluation_id": evaluation_id, "status": "already_registered"}
        self._connection.execute(
            "INSERT INTO evaluations VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                evaluation_id,
                experiment_id,
                matrix.semantic_sha256,
                planned.candidate_id,
                planned.candidate_config_sha256,
                planned.test_semantic_sha256,
                planned.train_semantic_sha256,
                planned.window["index"],
                _json(record),
                _now(),
            ),
        )
        self._connection.commit()
        return {
            "evaluation_id": evaluation_id,
            "experiment_id": experiment_id,
            "candidate_id": planned.candidate_id,
            "window_index": planned.window["index"],
            "status": "registered",
        }

    def evaluation_rows(self, matrix_sha256: str) -> tuple[dict[str, Any], ...]:
        rows = self._connection.execute(
            """SELECT e.*,x.performance_report_json,x.replay_report_json,x.trusted
               FROM evaluations e JOIN experiments x USING(experiment_id)
               WHERE e.matrix_sha256=? ORDER BY e.candidate_id,e.window_index""",
            (matrix_sha256,),
        ).fetchall()
        return tuple(
            {
                "evaluation_id": str(row["evaluation_id"]),
                "candidate_id": str(row["candidate_id"]),
                "window_index": int(row["window_index"]),
                "performance_report": json_object(str(row["performance_report_json"])),
                "replay_report": json_object(str(row["replay_report_json"])),
                "trusted": bool(row["trusted"]),
            }
            for row in rows
        )

    def verify(self) -> RegistrySummary:
        integrity = str(self._connection.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok" or self._connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("registry integrity check failed")
        counts = {
            table: int(self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("trusted_keys", "lineage_nodes", "lineage_edges", "experiments", "evaluations")
        }
        return RegistrySummary(integrity, *counts.values())

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> ExperimentRegistry:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
