from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.aggregation import aggregate_registry_matrix
from llm_arbitrage_system.experiments.bundle import verify_bundle
from llm_arbitrage_system.experiments.bundle_io import write_bytes, write_json
from llm_arbitrage_system.experiments.bundle_validation import (
    json_object,
    required_string,
)
from llm_arbitrage_system.experiments.campaign import (
    CampaignManifest,
    CampaignSpecSnapshot,
    build_campaign_manifest,
    load_campaign_spec,
    resolve_campaign_evaluation_ids,
)
from llm_arbitrage_system.experiments.campaign_store import (
    CampaignEvaluationState,
    CampaignStore,
    CampaignStoreSummary,
)
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.evaluation import (
    ExperimentMatrixSnapshot,
    load_evaluation_record,
    load_experiment_matrix,
    run_planned_evaluation,
)
from llm_arbitrage_system.experiments.manifest import resolve_code_revision
from llm_arbitrage_system.experiments.registry import ExperimentRegistry
from llm_arbitrage_system.experiments.signing import (
    load_private_key,
    public_key_identity,
    sign_bundle,
    verify_attestation,
)


@dataclass(frozen=True, slots=True)
class CampaignWorkspace:
    root: Path
    manifest_path: Path
    campaign_source_path: Path
    campaign_canonical_path: Path
    matrix_canonical_path: Path
    store_path: Path
    evaluations_root: Path
    attestations_root: Path
    aggregate_path: Path
    report_path: Path


@dataclass(frozen=True, slots=True)
class CampaignRunResult:
    manifest: CampaignManifest
    workspace: Path
    summary: CampaignStoreSummary
    aggregate: dict[str, Any]
    evaluations: tuple[CampaignEvaluationState, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.as_dict(),
            "workspace": str(self.workspace),
            "summary": self.summary.as_dict(),
            "aggregate": self.aggregate,
            "evaluations": [item.as_dict() for item in self.evaluations],
        }


async def run_campaign(
    *,
    dataset_path: Path,
    config_path: Path,
    matrix_path: Path,
    campaign_path: Path,
    registry_path: Path,
    private_key_path: Path,
    output_root: Path,
    code_revision: str | None = None,
    lineage_id: str | None = None,
    retry_failed: bool = False,
) -> CampaignRunResult:
    dataset = load_jsonl_dataset(dataset_path)
    config = load_experiment_config(config_path)
    matrix = load_experiment_matrix(matrix_path)
    campaign = load_campaign_spec(campaign_path)
    _verify_matrix_inputs(matrix, dataset.semantic_sha256, config.canonical_sha256)
    evaluation_ids = resolve_campaign_evaluation_ids(
        matrix,
        campaign.spec.selection,
    )
    revision = resolve_code_revision(code_revision, cwd=Path.cwd())
    signer = public_key_identity(load_private_key(private_key_path).public_key())
    manifest = build_campaign_manifest(
        matrix,
        campaign,
        evaluation_ids,
        code_revision=revision,
        signer_key_id=signer.key_id,
        lineage_id=lineage_id,
    )
    workspace_root = output_root.resolve() / manifest.campaign_id
    _reject_path_inside_workspace(
        workspace_root,
        private_key_path.resolve(),
        "private key",
    )
    _reject_path_inside_workspace(
        workspace_root,
        registry_path.resolve(),
        "experiment registry",
    )
    workspace = _prepare_workspace(
        output_root,
        manifest,
        campaign,
        matrix,
    )
    registration_lock = asyncio.Lock()

    with CampaignStore(workspace.store_path) as store:
        store.initialize(manifest, evaluation_ids)
        store.recover_interrupted(manifest.campaign_id)
        try:
            _reconcile_registered_evaluations(
                store,
                manifest.campaign_id,
                matrix,
                registry_path,
                signer_key_id=signer.key_id,
                lineage_id=lineage_id,
            )
            store.start(manifest.campaign_id)
            pending = list(
                store.pending_evaluation_ids(
                    manifest.campaign_id,
                    include_failed=retry_failed,
                )
            )
            failures = 0
            parallelism = campaign.spec.execution.maximum_parallel_evaluations
            stop_requested = False

            while pending and not stop_requested:
                batch = pending[:parallelism]
                del pending[:parallelism]
                outcomes = await asyncio.gather(
                    *(
                        _run_one_evaluation(
                            store=store,
                            campaign_id=manifest.campaign_id,
                            evaluation_id=evaluation_id,
                            dataset_path=dataset_path,
                            config_path=config_path,
                            matrix_path=matrix_path,
                            matrix=matrix,
                            registry_path=registry_path,
                            private_key_path=private_key_path,
                            evaluations_root=workspace.evaluations_root,
                            attestations_root=workspace.attestations_root,
                            code_revision=revision,
                            lineage_id=lineage_id,
                            registration_lock=registration_lock,
                            signer_key_id=signer.key_id,
                        )
                        for evaluation_id in batch
                    )
                )
                failures += sum(not outcome for outcome in outcomes)
                if any(not outcome for outcome in outcomes) and (
                    campaign.spec.execution.stop_on_failure
                    or failures >= campaign.spec.execution.maximum_failures
                ):
                    stop_requested = True

            terminal_status = _campaign_terminal_state(
                store,
                manifest.campaign_id,
            )
            aggregate = aggregate_registry_matrix(registry_path, matrix_path)
            write_json(workspace.aggregate_path, aggregate)
            store.finish(manifest.campaign_id, terminal_status)
            summary = store.summary(manifest.campaign_id)
            evaluations = store.evaluations(manifest.campaign_id)
            report = _campaign_report(manifest, summary, evaluations, aggregate)
            write_json(workspace.report_path, report)
            return CampaignRunResult(
                manifest=manifest,
                workspace=workspace.root,
                summary=summary,
                aggregate=aggregate,
                evaluations=evaluations,
            )
        except BaseException:
            store.recover_interrupted(manifest.campaign_id)
            try:
                store.finish(manifest.campaign_id, "aborted")
            except RuntimeError:
                pass
            raise


def campaign_status(workspace_path: Path) -> dict[str, Any]:
    root = workspace_path.resolve()
    manifest = json_object((root / "manifest.json").read_text(encoding="utf-8"))
    campaign_id = required_string(manifest, "campaign_id")
    with CampaignStore(root / "campaign.sqlite3") as store:
        summary = store.summary(campaign_id)
        evaluations = store.evaluations(campaign_id)
    aggregate_path = root / "aggregate.json"
    aggregate = (
        json_object(aggregate_path.read_text(encoding="utf-8"))
        if aggregate_path.is_file()
        else None
    )
    return {
        "manifest": manifest,
        "summary": summary.as_dict(),
        "evaluations": [item.as_dict() for item in evaluations],
        "aggregate": aggregate,
    }


async def _run_one_evaluation(
    *,
    store: CampaignStore,
    campaign_id: str,
    evaluation_id: str,
    dataset_path: Path,
    config_path: Path,
    matrix_path: Path,
    matrix: ExperimentMatrixSnapshot,
    registry_path: Path,
    private_key_path: Path,
    evaluations_root: Path,
    attestations_root: Path,
    code_revision: str,
    lineage_id: str | None,
    registration_lock: asyncio.Lock,
    signer_key_id: str,
) -> bool:
    store.mark_running(campaign_id, evaluation_id)
    try:
        bundle = _existing_evaluation_bundle(evaluations_root, evaluation_id)
        if bundle is None:
            result = await run_planned_evaluation(
                dataset_path=dataset_path,
                config_path=config_path,
                matrix_path=matrix_path,
                evaluation_id=evaluation_id,
                output_root=evaluations_root,
                code_revision=code_revision,
                lineage_id=lineage_id,
            )
            bundle = result.experiment.bundle.bundle_path

        attestation = attestations_root / f"{evaluation_id}.attestation.json"
        if attestation.exists():
            verified = verify_attestation(
                bundle,
                attestation,
                expected_lineage_id=lineage_id,
            )
            if verified.key_id != signer_key_id:
                raise ValueError(
                    "existing campaign attestation uses a different signer"
                )
        else:
            sign_bundle(
                bundle,
                private_key_path,
                attestation,
                lineage_id=lineage_id,
            )

        async with registration_lock:
            with ExperimentRegistry(registry_path) as registry:
                registered = registry.register_evaluation(
                    matrix_path=matrix_path,
                    evaluation_id=evaluation_id,
                    bundle_path=bundle,
                    attestation_path=attestation,
                )
        experiment_id = str(registered.get("experiment_id") or _experiment_id(bundle))
        store.mark_registered(
            campaign_id,
            evaluation_id,
            experiment_id=experiment_id,
            bundle_path=bundle,
            attestation_path=attestation,
        )
        return True
    except Exception as error:
        store.mark_failed(campaign_id, evaluation_id, error)
        return False


def _prepare_workspace(
    output_root: Path,
    manifest: CampaignManifest,
    campaign: CampaignSpecSnapshot,
    matrix: ExperimentMatrixSnapshot,
) -> CampaignWorkspace:
    root = output_root.resolve() / manifest.campaign_id
    if root.is_symlink():
        raise ValueError("campaign workspace cannot be a symbolic link")
    root.mkdir(parents=True, exist_ok=True)
    workspace = CampaignWorkspace(
        root=root,
        manifest_path=root / "manifest.json",
        campaign_source_path=root / "inputs/campaign.source.yaml",
        campaign_canonical_path=root / "inputs/campaign.canonical.json",
        matrix_canonical_path=root / "inputs/matrix.canonical.json",
        store_path=root / "campaign.sqlite3",
        evaluations_root=root / "evaluations",
        attestations_root=root / "attestations",
        aggregate_path=root / "aggregate.json",
        report_path=root / "report.json",
    )
    if workspace.manifest_path.exists():
        existing = json_object(
            workspace.manifest_path.read_text(encoding="utf-8")
        )
        if existing != manifest.as_dict():
            raise RuntimeError("campaign workspace manifest conflicts with identity")
    else:
        write_json(workspace.manifest_path, manifest.as_dict())
    _write_or_verify(
        workspace.campaign_source_path,
        campaign.source_bytes,
        "campaign source",
    )
    _write_or_verify(
        workspace.campaign_canonical_path,
        campaign.canonical_bytes,
        "campaign canonical input",
    )
    _write_or_verify(
        workspace.matrix_canonical_path,
        matrix.canonical_bytes,
        "matrix canonical input",
    )
    workspace.evaluations_root.mkdir(parents=True, exist_ok=True)
    workspace.attestations_root.mkdir(parents=True, exist_ok=True)
    return workspace


def _write_or_verify(path: Path, value: bytes, description: str) -> None:
    if path.is_symlink():
        raise ValueError(f"campaign workspace {description} cannot be a symlink")
    if path.exists():
        if path.read_bytes() != value:
            raise RuntimeError(f"campaign workspace {description} drift")
        return
    write_bytes(path, value)


def _reconcile_registered_evaluations(
    store: CampaignStore,
    campaign_id: str,
    matrix: ExperimentMatrixSnapshot,
    registry_path: Path,
    *,
    signer_key_id: str,
    lineage_id: str | None,
) -> None:
    with ExperimentRegistry(registry_path) as registry:
        registry.verify()
    by_id = _registry_evaluation_evidence(
        registry_path,
        matrix.semantic_sha256,
    )
    for state in store.evaluations(campaign_id):
        row = by_id.get(state.evaluation_id)
        if state.status in {"registered", "skipped_existing"}:
            if row is None or not bool(row["trusted"]):
                raise RuntimeError(
                    "campaign state references missing or untrusted registry evidence: "
                    + state.evaluation_id
                )
            _verify_registry_evidence_identity(
                state.evaluation_id,
                row,
                signer_key_id=signer_key_id,
                lineage_id=lineage_id,
            )
            continue
        if row is None:
            continue
        if not bool(row["trusted"]):
            raise PermissionError(
                "campaign cannot replace an existing untrusted evaluation: "
                + state.evaluation_id
            )
        _verify_registry_evidence_identity(
            state.evaluation_id,
            row,
            signer_key_id=signer_key_id,
            lineage_id=lineage_id,
        )
        store.mark_skipped_existing(
            campaign_id,
            state.evaluation_id,
            experiment_id=str(row["experiment_id"]),
        )


def _registry_evaluation_evidence(
    registry_path: Path,
    matrix_sha256: str,
) -> dict[str, dict[str, Any]]:
    connection = sqlite3.connect(
        f"file:{registry_path.resolve()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT e.evaluation_id, e.experiment_id, x.signer_key_id,
                   x.lineage_id, x.trusted
            FROM evaluations AS e
            JOIN experiments AS x USING (experiment_id)
            WHERE e.matrix_sha256 = ?
            ORDER BY e.evaluation_id
            """,
            (matrix_sha256,),
        ).fetchall()
    finally:
        connection.close()
    return {
        str(row["evaluation_id"]): {
            "experiment_id": str(row["experiment_id"]),
            "signer_key_id": str(row["signer_key_id"]),
            "lineage_id": (
                None if row["lineage_id"] is None else str(row["lineage_id"])
            ),
            "trusted": bool(row["trusted"]),
        }
        for row in rows
    }


def _verify_registry_evidence_identity(
    evaluation_id: str,
    row: dict[str, Any],
    *,
    signer_key_id: str,
    lineage_id: str | None,
) -> None:
    if row["signer_key_id"] != signer_key_id:
        raise RuntimeError(
            "existing registry evidence uses a different signer: "
            + evaluation_id
        )
    if row["lineage_id"] != lineage_id:
        raise RuntimeError(
            "campaign lineage does not match existing registry evidence: "
            + evaluation_id
        )


def _existing_evaluation_bundle(
    evaluations_root: Path,
    evaluation_id: str,
) -> Path | None:
    if not evaluations_root.exists():
        return None
    matches: list[Path] = []
    for candidate in sorted(evaluations_root.glob("exp-*")):
        if not candidate.is_dir():
            continue
        record_path = candidate / "evaluation.json"
        if not record_path.is_file():
            continue
        record = load_evaluation_record(candidate)
        if record.get("evaluation_id") == evaluation_id:
            verify_bundle(candidate)
            matches.append(candidate)
    if len(matches) > 1:
        raise RuntimeError(
            f"campaign contains multiple bundles for evaluation: {evaluation_id}"
        )
    return None if not matches else matches[0]


def _experiment_id(bundle: Path) -> str:
    manifest = json_object(
        (bundle.resolve() / "manifest.json").read_text(encoding="utf-8")
    )
    return required_string(manifest, "experiment_id")


def _campaign_terminal_state(
    store: CampaignStore,
    campaign_id: str,
) -> str:
    summary = store.summary(campaign_id)
    if summary.running:
        raise RuntimeError("campaign cannot finish with running evaluations")
    if summary.pending:
        return "failed"
    if summary.failed:
        return "partial"
    return "completed"


def _verify_matrix_inputs(
    matrix: ExperimentMatrixSnapshot,
    dataset_semantic_sha256: str,
    config_canonical_sha256: str,
) -> None:
    if matrix.dataset_semantic_sha256 != dataset_semantic_sha256:
        raise ValueError("campaign matrix does not match the supplied dataset")
    if matrix.base_config_sha256 != config_canonical_sha256:
        raise ValueError("campaign matrix does not match the supplied base config")


def _reject_path_inside_workspace(
    workspace: Path,
    path: Path,
    description: str,
) -> None:
    if path == workspace or workspace in path.parents:
        raise ValueError(f"{description} must be stored outside the campaign workspace")


def _campaign_report(
    manifest: CampaignManifest,
    summary: CampaignStoreSummary,
    evaluations: tuple[CampaignEvaluationState, ...],
    aggregate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest": manifest.as_dict(),
        "summary": summary.as_dict(),
        "evaluations": [item.as_dict() for item in evaluations],
        "aggregate": aggregate,
        "selection": None,
        "realized_pnl": None,
        "sharpe_ratio": None,
        "alpha_decay": None,
        "evidence_boundary": (
            "This campaign executes and registers a bounded deterministic evaluation "
            "set. It does not select a winner or establish realized profitability."
        ),
    }
