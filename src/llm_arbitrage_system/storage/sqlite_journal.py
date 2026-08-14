from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from llm_arbitrage_system.domain.contracts import (
    ApprovedTradePlan,
    ExecutionResult,
    MarketEvent,
    RiskEvaluation,
    StrategyDecision,
)


@dataclass(frozen=True, slots=True)
class JournalCounts:
    market_events: int
    strategy_decisions: int
    risk_evaluations: int
    execution_results: int
    replay_runs: int


class SQLiteReplayJournal:
    """Append-only SQLite evidence journal for one credential-free replay run."""

    def __init__(
        self,
        path: Path,
        *,
        run_id: str | None = None,
    ) -> None:
        self.path = path
        self.run_id = run_id or uuid4().hex
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._lock = asyncio.Lock()
        self._event_sequence = 0
        self._closed = False
        self._create_schema()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS replay_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                error TEXT,
                report_json TEXT,
                performance_report_json TEXT
            );

            CREATE TABLE IF NOT EXISTS market_events (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                event_timestamp TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence),
                FOREIGN KEY (run_id) REFERENCES replay_runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_market_events_run_symbol_time
            ON market_events (run_id, symbol, event_timestamp);

            CREATE TABLE IF NOT EXISTS strategy_decisions (
                run_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, plan_id),
                FOREIGN KEY (run_id) REFERENCES replay_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS risk_evaluations (
                run_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, plan_id),
                FOREIGN KEY (run_id) REFERENCES replay_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS execution_results (
                run_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                status TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (run_id, plan_id),
                FOREIGN KEY (run_id) REFERENCES replay_runs(run_id)
            );
            """
        )
        columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(replay_runs)")
        }
        if "performance_report_json" not in columns:
            self._connection.execute(
                "ALTER TABLE replay_runs ADD COLUMN performance_report_json TEXT"
            )
        self._connection.commit()

    async def start_run(self) -> None:
        async with self._lock:
            self._ensure_open()
            await asyncio.to_thread(self._start_run_sync)

    def _start_run_sync(self) -> None:
        self._connection.execute(
            """
            INSERT INTO replay_runs (run_id, started_at, status)
            VALUES (?, ?, ?)
            """,
            (self.run_id, _utc_now_text(), "running"),
        )
        self._connection.commit()

    async def record_market_event(self, event: MarketEvent) -> None:
        async with self._lock:
            self._ensure_open()
            self._event_sequence += 1
            await asyncio.to_thread(
                self._record_market_event_sync,
                self._event_sequence,
                event,
            )

    def _record_market_event_sync(self, sequence: int, event: MarketEvent) -> None:
        self._connection.execute(
            """
            INSERT INTO market_events (
                run_id, sequence, symbol, event_timestamp, payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                sequence,
                event.symbol,
                event.timestamp.isoformat(),
                _to_json(event),
            ),
        )
        self._connection.commit()

    async def record_decision(self, decision: StrategyDecision) -> None:
        async with self._lock:
            self._ensure_open()
            await asyncio.to_thread(self._record_decision_sync, decision)

    def _record_decision_sync(self, decision: StrategyDecision) -> None:
        plan = decision.plan
        self._connection.execute(
            """
            INSERT INTO strategy_decisions (
                run_id, plan_id, strategy, symbol, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                plan.plan_id,
                plan.strategy.value,
                plan.symbol,
                plan.created_at.isoformat(),
                _to_json(decision),
            ),
        )
        self._connection.commit()

    async def record_risk_evaluation(
        self,
        decision: StrategyDecision,
        evaluation: RiskEvaluation,
    ) -> None:
        async with self._lock:
            self._ensure_open()
            await asyncio.to_thread(
                self._record_risk_evaluation_sync,
                decision,
                evaluation,
            )

    def _record_risk_evaluation_sync(
        self,
        decision: StrategyDecision,
        evaluation: RiskEvaluation,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO risk_evaluations (
                run_id, plan_id, accepted, recorded_at, payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                decision.plan.plan_id,
                int(evaluation.accepted),
                _utc_now_text(),
                _to_json(evaluation),
            ),
        )
        self._connection.commit()

    async def record_execution_result(
        self,
        approved: ApprovedTradePlan,
        result: ExecutionResult,
    ) -> None:
        async with self._lock:
            self._ensure_open()
            await asyncio.to_thread(
                self._record_execution_result_sync,
                approved,
                result,
            )

    def _record_execution_result_sync(
        self,
        approved: ApprovedTradePlan,
        result: ExecutionResult,
    ) -> None:
        payload = {"approved": _to_jsonable(approved), "result": _to_jsonable(result)}
        self._connection.execute(
            """
            INSERT INTO execution_results (
                run_id, plan_id, status, recorded_at, payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                self.run_id,
                result.plan_id,
                result.status.value,
                _utc_now_text(),
                json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ),
        )
        self._connection.commit()

    async def complete_run(
        self,
        report: Mapping[str, int],
        performance_report: Mapping[str, Any] | None = None,
    ) -> None:
        async with self._lock:
            self._ensure_open()
            await asyncio.to_thread(
                self._complete_run_sync,
                report,
                performance_report,
            )

    def _complete_run_sync(
        self,
        report: Mapping[str, int],
        performance_report: Mapping[str, Any] | None,
    ) -> None:
        cursor = self._connection.execute(
            """
            UPDATE replay_runs
            SET completed_at = ?, status = ?, error = NULL, report_json = ?,
                performance_report_json = ?
            WHERE run_id = ? AND status = ?
            """,
            (
                _utc_now_text(),
                "completed",
                json.dumps(dict(report), sort_keys=True, separators=(",", ":")),
                None
                if performance_report is None
                else json.dumps(
                    dict(performance_report),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                self.run_id,
                "running",
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("replay run was not in the running state")
        self._connection.commit()

    async def abort_run(self, error: str) -> None:
        async with self._lock:
            self._ensure_open()
            await asyncio.to_thread(self._abort_run_sync, error)

    def _abort_run_sync(self, error: str) -> None:
        self._connection.execute(
            """
            UPDATE replay_runs
            SET completed_at = ?, status = ?, error = ?
            WHERE run_id = ? AND status = ?
            """,
            (_utc_now_text(), "aborted", error, self.run_id, "running"),
        )
        self._connection.commit()

    async def counts(self) -> JournalCounts:
        async with self._lock:
            self._ensure_open()
            values = await asyncio.to_thread(self._counts_sync)
        return JournalCounts(*values)

    def _counts_sync(self) -> tuple[int, int, int, int, int]:
        tables = (
            "market_events",
            "strategy_decisions",
            "risk_evaluations",
            "execution_results",
            "replay_runs",
        )
        counts: list[int] = []
        for table in tables:
            row = self._connection.execute(
                f"SELECT COUNT(*) AS count FROM {table} WHERE run_id = ?",
                (self.run_id,),
            ).fetchone()
            counts.append(0 if row is None else int(row["count"]))
        return cast(tuple[int, int, int, int, int], tuple(counts))

    async def load_execution_payloads(self) -> tuple[dict[str, Any], ...]:
        async with self._lock:
            self._ensure_open()
            rows = await asyncio.to_thread(self._load_execution_payloads_sync)
        return tuple(_json_object(row["payload_json"]) for row in rows)

    def _load_execution_payloads_sync(self) -> list[sqlite3.Row]:
        cursor = self._connection.execute(
            """
            SELECT payload_json FROM execution_results
            WHERE run_id = ? ORDER BY recorded_at, plan_id
            """,
            (self.run_id,),
        )
        return list(cursor.fetchall())

    async def load_report(self) -> dict[str, int] | None:
        async with self._lock:
            self._ensure_open()
            value = await asyncio.to_thread(self._load_report_sync)
        if value is None:
            return None
        parsed = _json_object(value)
        return {key: int(item) for key, item in parsed.items()}

    def _load_report_sync(self) -> str | None:
        row = self._connection.execute(
            "SELECT report_json FROM replay_runs WHERE run_id = ?",
            (self.run_id,),
        ).fetchone()
        if row is None:
            return None
        return cast(str | None, row["report_json"])

    async def load_performance_report(self) -> dict[str, Any] | None:
        async with self._lock:
            self._ensure_open()
            value = await asyncio.to_thread(self._load_performance_report_sync)
        return None if value is None else _json_object(value)

    def _load_performance_report_sync(self) -> str | None:
        row = self._connection.execute(
            "SELECT performance_report_json FROM replay_runs WHERE run_id = ?",
            (self.run_id,),
        ).fetchone()
        if row is None:
            return None
        return cast(str | None, row["performance_report_json"])

    async def load_market_event_payloads(self) -> tuple[dict[str, Any], ...]:
        async with self._lock:
            self._ensure_open()
            rows = await asyncio.to_thread(self._load_market_event_payloads_sync)
        return tuple(_json_object(row["payload_json"]) for row in rows)

    def _load_market_event_payloads_sync(self) -> list[sqlite3.Row]:
        cursor = self._connection.execute(
            """
            SELECT payload_json FROM market_events
            WHERE run_id = ? ORDER BY sequence
            """,
            (self.run_id,),
        )
        return list(cursor.fetchall())

    async def integrity_check(self) -> str:
        async with self._lock:
            self._ensure_open()
            return await asyncio.to_thread(self._integrity_check_sync)

    def _integrity_check_sync(self) -> str:
        row = self._connection.execute("PRAGMA integrity_check").fetchone()
        if row is None:
            raise RuntimeError("SQLite did not return an integrity result")
        return str(row[0])

    async def run_status(self) -> str | None:
        async with self._lock:
            self._ensure_open()
            return await asyncio.to_thread(self._run_status_sync)

    def _run_status_sync(self) -> str | None:
        row = self._connection.execute(
            "SELECT status FROM replay_runs WHERE run_id = ?",
            (self.run_id,),
        ).fetchone()
        return None if row is None else str(row["status"])

    async def close(self) -> None:
        async with self._lock:
            if self._closed:
                return
            await asyncio.to_thread(self._connection.close)
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("SQLiteReplayJournal is closed")


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json(value: object) -> str:
    return json.dumps(
        _to_jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
    )


def _to_jsonable(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _to_jsonable(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_to_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported journal value: {type(value).__name__}")


def _json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("journal payload must be a JSON object")
    return cast(dict[str, Any], parsed)
