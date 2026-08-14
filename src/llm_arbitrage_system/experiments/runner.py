from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_arbitrage_system.analytics.engine import AnalyticsEngine
from llm_arbitrage_system.experiments.bundle import (
    BundleVerificationResult,
    finalize_bundle,
    prepare_bundle_workspace,
    write_bundle_inputs,
    write_bundle_reports,
)
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.determinism import ContentAddressedPlanner
from llm_arbitrage_system.experiments.manifest import (
    ExperimentManifest,
    build_experiment_manifest,
    resolve_code_revision,
)
from llm_arbitrage_system.simulation.approval import StatefulPaperApprover
from llm_arbitrage_system.simulation.executor import DeterministicPaperExecutor
from llm_arbitrage_system.simulation.pipeline import PaperReplayPipeline
from llm_arbitrage_system.simulation.strategy_router import PaperStrategyRouter
from llm_arbitrage_system.storage.sqlite_journal import SQLiteReplayJournal


@dataclass(frozen=True, slots=True)
class ExperimentRunResult:
    manifest: ExperimentManifest
    bundle: BundleVerificationResult
    replay_report: dict[str, int]
    performance_report: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.as_dict(),
            "bundle": self.bundle.as_dict(),
            "replay_report": self.replay_report,
            "performance_report": self.performance_report,
        }


async def run_experiment(
    *,
    dataset_path: Path,
    config_path: Path,
    output_root: Path,
    code_revision: str | None = None,
    force: bool = False,
) -> ExperimentRunResult:
    dataset = load_jsonl_dataset(dataset_path)
    config_snapshot = load_experiment_config(config_path)
    revision = resolve_code_revision(code_revision, cwd=Path.cwd())
    manifest = build_experiment_manifest(
        dataset,
        config_snapshot,
        code_revision=revision,
    )
    workspace = prepare_bundle_workspace(
        output_root,
        manifest.experiment_id,
        force=force,
    )
    write_bundle_inputs(workspace.staging, dataset, config_snapshot)

    journal = SQLiteReplayJournal(
        workspace.staging / "evidence.sqlite3",
        run_id=manifest.run_id,
    )
    config = config_snapshot.config
    pipeline = PaperReplayPipeline(
        analytics=AnalyticsEngine(config.analytics),
        planner=ContentAddressedPlanner(
            PaperStrategyRouter(config.strategy),
            dataset_semantic_sha256=dataset.semantic_sha256,
        ),
        approver=StatefulPaperApprover(config.approval, replay_mode=True),
        executor=DeterministicPaperExecutor(
            slippage_bps=config.execution.slippage_bps,
            fee_bps=config.execution.fee_bps,
            fail_leg_indexes=frozenset(config.execution.fail_leg_indexes),
        ),
        queue_size=config.runtime.queue_size,
        journal=journal,
    )

    try:
        replay = await pipeline.run(dataset.events)
        performance = pipeline.performance_report
        if performance is None:
            raise RuntimeError("pipeline completed without a performance report")
        sqlite_integrity = await journal.integrity_check()
        if sqlite_integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {sqlite_integrity}")
        run_status = await journal.run_status()
        if run_status != "completed":
            raise RuntimeError(f"replay run did not complete: {run_status}")
        await journal.close()
        _checkpoint_database(workspace.staging / "evidence.sqlite3")
        replay_payload = replay.as_dict()
        performance_payload = performance.as_dict()
        write_bundle_reports(
            workspace.staging,
            manifest,
            replay_payload,
            performance_payload,
            sqlite_integrity=sqlite_integrity,
        )
        verification = finalize_bundle(workspace)
        return ExperimentRunResult(
            manifest=manifest,
            bundle=verification,
            replay_report=replay_payload,
            performance_report=performance_payload,
        )
    except BaseException:
        try:
            await journal.close()
        except Exception:
            pass
        if workspace.staging.exists():
            shutil.rmtree(workspace.staging)
        raise


def _checkpoint_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.commit()
    finally:
        connection.close()
