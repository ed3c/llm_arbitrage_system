from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.aggregation import aggregate_registry_matrix
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.evaluation import (
    load_experiment_matrix,
    run_planned_evaluation,
)
from llm_arbitrage_system.experiments.registry import ExperimentRegistry
from llm_arbitrage_system.experiments.signing import generate_signing_keypair, sign_bundle
from llm_arbitrage_system.experiments.walk_forward import load_sweep_spec, matrix_payload


def _matrix(root: Path, output: Path) -> Path:
    dataset = load_jsonl_dataset(root / "examples/phase3/market_events.jsonl")
    config = load_experiment_config(root / "examples/phase3/experiment.yaml")
    sweep = load_sweep_spec(root / "examples/phase3/sweep.yaml")
    output.write_bytes(canonical_json_bytes(matrix_payload(dataset, config.config, sweep)) + b"\n")
    return output


@pytest.mark.asyncio
async def test_planned_evaluation_replays_only_test_slice(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    matrix_path = _matrix(root, tmp_path / "matrix.json")
    planned = load_experiment_matrix(matrix_path).evaluations[0]
    result = await run_planned_evaluation(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        matrix_path=matrix_path,
        evaluation_id=planned.evaluation_id,
        output_root=tmp_path / "runs",
        code_revision="phase4-evaluation-test",
    )
    assert result.experiment.manifest.dataset_semantic_sha256 == planned.test_semantic_sha256
    assert result.experiment.manifest.config_canonical_sha256 == planned.candidate_config_sha256
    assert result.experiment.replay_report["events_received"] == (
        planned.window["test_end"] - planned.window["test_start"]
    )
    record = json.loads(result.evaluation_path.read_text(encoding="utf-8"))
    assert record["evaluation_id"] == planned.evaluation_id


@pytest.mark.asyncio
async def test_registry_requires_trust_and_exact_matrix_binding(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    matrix_path = _matrix(root, tmp_path / "matrix.json")
    matrix = load_experiment_matrix(matrix_path)
    planned = matrix.evaluations[0]
    result = await run_planned_evaluation(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        matrix_path=matrix_path,
        evaluation_id=planned.evaluation_id,
        output_root=tmp_path / "runs",
        code_revision="phase4-registry-test",
    )
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    generate_signing_keypair(private_key, public_key)
    attestation = tmp_path / "attestation.json"
    sign_bundle(result.experiment.bundle.bundle_path, private_key, attestation)
    with ExperimentRegistry(tmp_path / "registry.sqlite3") as registry:
        with pytest.raises(PermissionError, match="not trusted"):
            registry.register_evaluation(
                matrix_path=matrix_path,
                evaluation_id=planned.evaluation_id,
                bundle_path=result.experiment.bundle.bundle_path,
                attestation_path=attestation,
            )
        registry.trust_public_key(public_key)
        registered = registry.register_evaluation(
            matrix_path=matrix_path,
            evaluation_id=planned.evaluation_id,
            bundle_path=result.experiment.bundle.bundle_path,
            attestation_path=attestation,
        )
        assert registered["evaluation_id"] == planned.evaluation_id
        assert registry.verify().evaluations == 1
        with pytest.raises(ValueError, match="evaluation_id"):
            registry.register_evaluation(
                matrix_path=matrix_path,
                evaluation_id=matrix.evaluations[1].evaluation_id,
                bundle_path=result.experiment.bundle.bundle_path,
                attestation_path=attestation,
            )


@pytest.mark.asyncio
async def test_aggregation_withholds_selection_and_alpha(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    matrix_path = _matrix(root, tmp_path / "matrix.json")
    matrix = load_experiment_matrix(matrix_path)
    planned = matrix.evaluations[0]
    result = await run_planned_evaluation(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        matrix_path=matrix_path,
        evaluation_id=planned.evaluation_id,
        output_root=tmp_path / "runs",
        code_revision="phase4-aggregate-test",
    )
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    generate_signing_keypair(private_key, public_key)
    attestation = tmp_path / "attestation.json"
    sign_bundle(result.experiment.bundle.bundle_path, private_key, attestation)
    registry_path = tmp_path / "registry.sqlite3"
    with ExperimentRegistry(registry_path) as registry:
        registry.trust_public_key(public_key)
        registry.register_evaluation(
            matrix_path=matrix_path,
            evaluation_id=planned.evaluation_id,
            bundle_path=result.experiment.bundle.bundle_path,
            attestation_path=attestation,
        )
    report = aggregate_registry_matrix(registry_path, matrix_path)
    assert report["registered_evaluation_count"] == 1
    assert report["partial_candidate_count"] == 1
    assert report["selection"] is None
    assert report["realized_pnl"] is None
    assert report["sharpe_ratio"] is None
    assert report["alpha_decay"] is None
