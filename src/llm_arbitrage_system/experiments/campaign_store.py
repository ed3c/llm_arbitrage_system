from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.campaign import CampaignManifest
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes

_CAMPAIGN_STATES = {
    "planned",
    "running",
    "completed",
    "partial",
    "failed",
    "aborted",
}
_EVALUATION_STATES = {
    "pending",
    "running",
    "registered",
    "skipped_existing",
    "failed",
}
_TERMINAL_CAMPAIGN_STATES = {"completed", "partial", "failed", "aborted"}
_TERMINAL_EVALUATION_STATES = {"registered", "skipped_existing", "failed"}


@dataclass(frozen=True, slots=True)
class CampaignEvaluationState:
    evaluation_id: str
    ordinal: int
    status: str
    attempt_count: int
    experiment_id: str | None
    bundle_path: str | None
    attestation_path: str | None
    error_type: str | None
    error_message: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "ordinal": self.ordinal,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "experiment_id": self.experiment_id,
            "bundle_path": self.bundle_path,
            "attestation_path": self.attestation_path,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(frozen=True, slots=True)
class CampaignStoreSummary:
    integrity: str
    campaign_id: str
    status: str
    planned: int
    pending: int
    running: int
    registered: int
    skipped_existing: int
    failed: int
    recovered_interrupted: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "integrity": self.integrity,
            "campaign_id": self.campaign_id,
            "status": self.status,
            "planned": self.planned,
            "pending": self.pending,
            "running": self.running,
            "registered": self.registered,
            "skipped_existing": self.skipped_existing,
            "failed": self.failed,
            "recovered_interrupted": self.recovered_interrupted,
        }


class CampaignStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._closed = False
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id TEXT PRIMARY KEY,
                campaign_run_id TEXT NOT NULL UNIQUE,
                manifest_json TEXT NOT NULL,
                status TEXT NOT NULL,
                recovered_interrupted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS campaign_evaluations (
                campaign_id TEXT NOT NULL,
                evaluation_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                status TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                experiment_id TEXT,
                bundle_path TEXT,
                attestation_path TEXT,
                error_type TEXT,
                error_message TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (campaign_id, evaluation_id),
                UNIQUE (campaign_id, ordinal),
                FOREIGN KEY (campaign_id) REFERENCES campaigns(campaign_id)
            );
            CREATE INDEX IF NOT EXISTS idx_campaign_evaluation_status
            ON campaign_evaluations (campaign_id, status, ordinal);
            """
        )
        self._connection.commit()

    def initialize(
        self,
        manifest: CampaignManifest,
        evaluation_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        if not evaluation_ids:
            raise ValueError("campaign must contain at least one evaluation")
        manifest_json = _json(manifest.as_dict())
        existing = self._connection.execute(
            "SELECT campaign_run_id, manifest_json FROM campaigns WHERE campaign_id = ?",
            (manifest.campaign_id,),
        ).fetchone()
        if existing is not None:
            if (
                str(existing["campaign_run_id"]) != manifest.campaign_run_id
                or str(existing["manifest_json"]) != manifest_json
            ):
                raise RuntimeError("campaign ID conflicts with immutable manifest")
            if self._evaluation_ids(manifest.campaign_id) != evaluation_ids:
                raise RuntimeError("campaign evaluation set conflicts with stored plan")
            return {
                "campaign_id": manifest.campaign_id,
                "status": "already_initialized",
            }

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO campaigns (
                    campaign_id, campaign_run_id, manifest_json, status, created_at
                ) VALUES (?, ?, ?, 'planned', ?)
                """,
                (
                    manifest.campaign_id,
                    manifest.campaign_run_id,
                    manifest_json,
                    _now(),
                ),
            )
            self._connection.executemany(
                """
                INSERT INTO campaign_evaluations (
                    campaign_id, evaluation_id, ordinal, status, updated_at
                ) VALUES (?, ?, ?, 'pending', ?)
                """,
                [
                    (manifest.campaign_id, evaluation_id, ordinal, _now())
                    for ordinal, evaluation_id in enumerate(evaluation_ids)
                ],
            )
        return {"campaign_id": manifest.campaign_id, "status": "initialized"}

    def recover_interrupted(self, campaign_id: str) -> int:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE campaign_evaluations
                SET status = 'pending', error_type = NULL,
                    error_message = NULL, updated_at = ?
                WHERE campaign_id = ? AND status = 'running'
                """,
                (_now(), campaign_id),
            )
            recovered = int(cursor.rowcount)
            if recovered:
                self._connection.execute(
                    """
                    UPDATE campaigns
                    SET recovered_interrupted = recovered_interrupted + ?
                    WHERE campaign_id = ?
                    """,
                    (recovered, campaign_id),
                )
        return recovered

    def start(self, campaign_id: str) -> None:
        status = self.status(campaign_id)
        if status == "completed":
            return
        if status not in {"planned", "running", "partial", "failed", "aborted"}:
            raise RuntimeError(f"campaign cannot start from state: {status}")
        self._connection.execute(
            """
            UPDATE campaigns
            SET status = 'running', started_at = COALESCE(started_at, ?),
                completed_at = NULL
            WHERE campaign_id = ?
            """,
            (_now(), campaign_id),
        )
        self._connection.commit()

    def mark_running(self, campaign_id: str, evaluation_id: str) -> None:
        current = self.evaluation(campaign_id, evaluation_id)
        if current.status not in {"pending", "failed"}:
            raise RuntimeError(
                f"evaluation cannot enter running from {current.status}: {evaluation_id}"
            )
        self._connection.execute(
            """
            UPDATE campaign_evaluations
            SET status = 'running', attempt_count = attempt_count + 1,
                experiment_id = NULL, bundle_path = NULL,
                attestation_path = NULL, error_type = NULL,
                error_message = NULL, updated_at = ?
            WHERE campaign_id = ? AND evaluation_id = ?
            """,
            (_now(), campaign_id, evaluation_id),
        )
        self._connection.commit()

    def mark_registered(
        self,
        campaign_id: str,
        evaluation_id: str,
        *,
        experiment_id: str,
        bundle_path: Path,
        attestation_path: Path,
    ) -> None:
        self._set_terminal(
            campaign_id,
            evaluation_id,
            "registered",
            experiment_id=experiment_id,
            bundle_path=str(bundle_path.resolve()),
            attestation_path=str(attestation_path.resolve()),
        )

    def mark_skipped_existing(
        self,
        campaign_id: str,
        evaluation_id: str,
        *,
        experiment_id: str | None,
    ) -> None:
        self._set_terminal(
            campaign_id,
            evaluation_id,
            "skipped_existing",
            experiment_id=experiment_id,
        )

    def mark_failed(
        self,
        campaign_id: str,
        evaluation_id: str,
        error: BaseException,
    ) -> None:
        self._set_terminal(
            campaign_id,
            evaluation_id,
            "failed",
            error_type=type(error).__name__,
            error_message=_bounded_message(str(error)),
        )

    def _set_terminal(
        self,
        campaign_id: str,
        evaluation_id: str,
        status: str,
        *,
        experiment_id: str | None = None,
        bundle_path: str | None = None,
        attestation_path: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if status not in _TERMINAL_EVALUATION_STATES:
            raise ValueError(f"invalid terminal evaluation state: {status}")
        current = self.evaluation(campaign_id, evaluation_id)
        if current.status in {"registered", "skipped_existing"}:
            if current.status == status and current.experiment_id == experiment_id:
                return
            raise RuntimeError(f"immutable evaluation state conflict: {evaluation_id}")
        if current.status not in {"pending", "running", "failed"}:
            raise RuntimeError(
                f"evaluation cannot enter {status} from {current.status}: {evaluation_id}"
            )
        self._connection.execute(
            """
            UPDATE campaign_evaluations
            SET status = ?, experiment_id = ?, bundle_path = ?,
                attestation_path = ?, error_type = ?, error_message = ?,
                updated_at = ?
            WHERE campaign_id = ? AND evaluation_id = ?
            """,
            (
                status,
                experiment_id,
                bundle_path,
                attestation_path,
                error_type,
                error_message,
                _now(),
                campaign_id,
                evaluation_id,
            ),
        )
        self._connection.commit()

    def finish(self, campaign_id: str, status: str) -> None:
        if status not in _TERMINAL_CAMPAIGN_STATES:
            raise ValueError(f"invalid terminal campaign state: {status}")
        counts = self._counts(campaign_id)
        if counts["running"]:
            raise RuntimeError("campaign cannot finish while evaluations are running")
        if status == "completed" and (counts["pending"] or counts["failed"]):
            raise RuntimeError("completed campaign cannot contain pending or failed rows")
        if status == "partial" and not counts["failed"]:
            raise RuntimeError("partial campaign must contain a failed evaluation")
        if status == "failed" and not (counts["failed"] or counts["pending"]):
            raise RuntimeError("failed campaign requires failed or unattempted rows")
        self._connection.execute(
            "UPDATE campaigns SET status = ?, completed_at = ? WHERE campaign_id = ?",
            (status, _now(), campaign_id),
        )
        self._connection.commit()

    def status(self, campaign_id: str) -> str:
        row = self._connection.execute(
            "SELECT status FROM campaigns WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown campaign: {campaign_id}")
        status = str(row["status"])
        if status not in _CAMPAIGN_STATES:
            raise RuntimeError(f"campaign contains invalid state: {status}")
        return status

    def evaluation(
        self,
        campaign_id: str,
        evaluation_id: str,
    ) -> CampaignEvaluationState:
        row = self._connection.execute(
            """
            SELECT * FROM campaign_evaluations
            WHERE campaign_id = ? AND evaluation_id = ?
            """,
            (campaign_id, evaluation_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown campaign evaluation: {evaluation_id}")
        return _evaluation_state(row)

    def evaluations(self, campaign_id: str) -> tuple[CampaignEvaluationState, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM campaign_evaluations
            WHERE campaign_id = ? ORDER BY ordinal
            """,
            (campaign_id,),
        ).fetchall()
        return tuple(_evaluation_state(row) for row in rows)

    def pending_evaluation_ids(
        self,
        campaign_id: str,
        *,
        include_failed: bool = False,
    ) -> tuple[str, ...]:
        statuses = ("pending", "failed") if include_failed else ("pending",)
        placeholders = ", ".join("?" for _ in statuses)
        rows = self._connection.execute(
            "SELECT evaluation_id FROM campaign_evaluations "
            f"WHERE campaign_id = ? AND status IN ({placeholders}) ORDER BY ordinal",
            (campaign_id, *statuses),
        ).fetchall()
        return tuple(str(row["evaluation_id"]) for row in rows)

    def summary(self, campaign_id: str) -> CampaignStoreSummary:
        integrity = self._integrity()
        counts = self._counts(campaign_id)
        row = self._connection.execute(
            """
            SELECT status, recovered_interrupted FROM campaigns
            WHERE campaign_id = ?
            """,
            (campaign_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown campaign: {campaign_id}")
        status = str(row["status"])
        if status not in _CAMPAIGN_STATES:
            raise RuntimeError(f"campaign contains invalid state: {status}")
        if status in _TERMINAL_CAMPAIGN_STATES and counts["running"]:
            raise RuntimeError("terminal campaign contains running evaluations")
        return CampaignStoreSummary(
            integrity=integrity,
            campaign_id=campaign_id,
            status=status,
            planned=sum(counts.values()),
            pending=counts["pending"],
            running=counts["running"],
            registered=counts["registered"],
            skipped_existing=counts["skipped_existing"],
            failed=counts["failed"],
            recovered_interrupted=int(row["recovered_interrupted"]),
        )

    def _evaluation_ids(self, campaign_id: str) -> tuple[str, ...]:
        return tuple(
            str(row["evaluation_id"])
            for row in self._connection.execute(
                """
                SELECT evaluation_id FROM campaign_evaluations
                WHERE campaign_id = ? ORDER BY ordinal
                """,
                (campaign_id,),
            ).fetchall()
        )

    def _counts(self, campaign_id: str) -> dict[str, int]:
        result = {state: 0 for state in _EVALUATION_STATES}
        rows = self._connection.execute(
            """
            SELECT status, COUNT(*) AS count FROM campaign_evaluations
            WHERE campaign_id = ? GROUP BY status
            """,
            (campaign_id,),
        ).fetchall()
        for row in rows:
            status = str(row["status"])
            if status not in _EVALUATION_STATES:
                raise RuntimeError(f"invalid campaign evaluation state: {status}")
            result[status] = int(row["count"])
        return result

    def _integrity(self) -> str:
        row = self._connection.execute("PRAGMA integrity_check").fetchone()
        if row is None:
            raise RuntimeError("campaign store did not return an integrity result")
        integrity = str(row[0])
        if integrity != "ok":
            raise RuntimeError(f"campaign store integrity failed: {integrity}")
        if self._connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("campaign store foreign-key check failed")
        return integrity

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def __enter__(self) -> CampaignStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _evaluation_state(row: sqlite3.Row) -> CampaignEvaluationState:
    status = str(row["status"])
    if status not in _EVALUATION_STATES:
        raise RuntimeError(f"invalid campaign evaluation state: {status}")
    return CampaignEvaluationState(
        evaluation_id=str(row["evaluation_id"]),
        ordinal=int(row["ordinal"]),
        status=status,
        attempt_count=int(row["attempt_count"]),
        experiment_id=_optional_string(row["experiment_id"]),
        bundle_path=_optional_string(row["bundle_path"]),
        attestation_path=_optional_string(row["attestation_path"]),
        error_type=_optional_string(row["error_type"]),
        error_message=_optional_string(row["error_message"]),
    )


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)


def _json(value: object) -> str:
    return canonical_json_bytes(value).decode("utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _bounded_message(value: str) -> str:
    return " ".join(value.split())[:1000]
