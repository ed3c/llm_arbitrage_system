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
from llm_arbitrage_system.experiments.lineage import load_lineage_manifest
from llm_arbitrage_system.experiments.registry import ExperimentRegistry
from llm_arbitrage_system.experiments.runner import run_experiment
from llm_arbitrage_system.experiments.signing import (
    generate_signing_keypair,
    sign_bundle,
    verify_attestation,
)
from llm_arbitrage_system.experiments.walk_forward import (
    load_sweep_spec,
    matrix_payload,
)


def _root() -> Path:
    return Path(__file__).parents[1]


def _matrix(output: Path) -> Path:
    root = _root()
    dataset = load_jsonl_dataset(root / "examples/phase3/market_events.jsonl")
    config = load_experiment_config(root / "examples/phase3/experiment.yaml")
    sweep = load_sweep_spec(root / "examples/phase3/sweep.yaml")
    output.write_bytes(
        canonical_json_bytes(matrix_payload(dataset, config.config, sweep)) + b"\n"
    )
    return output


@pytest.mark.asyncio
async def test_detached_attestation_binds_bundle_trusted_key_and_lineage(
    tmp_path: Path,
) -> None:
    root = _root()
    result = await run_experiment(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase4-signing-test",
    )
    lineage = load_lineage_manifest(root / "examples/phase4/lineage.yaml")
    private_key = tmp_path / "keys/private.pem"
    public_key = tmp_path / "keys/public.pem"
    identity = generate_signing_keypair(private_key, public_key)
    assert private_key.stat().st_mode & 0o777 == 0o600
    attestation = tmp_path / "bundle.attestation.json"
    document = sign_bundle(
        result.bundle.bundle_path,
        private_key,
        attestation,
        lineage_id=lineage.manifest.lineage_id,
    )
    verification = verify_attestation(
        result.bundle.bundle_path,
        attestation,
        trusted_public_key_path=public_key,
        expected_lineage_id=lineage.manifest.lineage_id,
    )
    assert document["payload"]["key_id"] == identity.key_id
    assert verification.experiment_id == result.manifest.experiment_id
    assert verification.lineage_id == lineage.manifest.lineage_id
    assert verification.trusted_key_matched
    with pytest.raises(ValueError, match="outside the evidence bundle"):
        sign_bundle(
            result.bundle.bundle_path,
            private_key,
            result.bundle.bundle_path / "attestation.json",
        )


@pytest.mark.asyncio
async def test_attestation_detects_signature_and_bundle_tampering(
    tmp_path: Path,
) -> None:
    root = _root()
    result = await run_experiment(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase4-tamper-test",
    )
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    generate_signing_keypair(private_key, public_key)
    attestation = tmp_path / "attestation.json"
    sign_bundle(result.bundle.bundle_path, private_key, attestation)
    payload = json.loads(attestation.read_text(encoding="utf-8"))
    original = str(payload["signature_base64"])
    replacement = "A" if original[0] != "A" else "B"
    payload["signature_base64"] = replacement + original[1:]
    attestation.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="signature"):
        verify_attestation(result.bundle.bundle_path, attestation)

    sign_bundle(result.bundle.bundle_path, private_key, attestation, force=True)
    report = result.bundle.bundle_path / "report.md"
    report.write_text(
        report.read_text(encoding="utf-8") + "tampered\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        verify_attestation(result.bundle.bundle_path, attestation)


def test_lineage_is_content_addressed_and_registry_requires_parents(
    tmp_path: Path,
) -> None:
    root = _root()
    source_path = root / "examples/phase4/lineage.yaml"
    source = load_lineage_manifest(source_path)
    derived_path = tmp_path / "derived.yaml"
    derived_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                (
                    "dataset_semantic_sha256: "
                    + source.manifest.dataset_semantic_sha256
                ),
                "kind: derived",
                "operation:",
                "  name: normalize",
                '  version: "1"',
                "  parameters: {}",
                "parents:",
                f"  - {source.manifest.lineage_id}",
                "source_uri: null",
                "notes: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with ExperimentRegistry(tmp_path / "registry.sqlite3") as registry:
        with pytest.raises(ValueError, match="parent is not registered"):
            registry.import_lineage(derived_path)
        registry.import_lineage(source_path)
        registry.import_lineage(derived_path)
        summary = registry.verify()
    assert summary.lineage_nodes == 2
    assert summary.lineage_edges == 1

    altered = tmp_path / "altered.yaml"
    text = source_path.read_text(encoding="utf-8")
    altered.write_text(
        text.replace("synthetic_fixture_capture", "synthetic_fixture_capture_v2"),
        encoding="utf-8",
    )
    assert (
        load_lineage_manifest(altered).manifest.lineage_id
        != source.manifest.lineage_id
    )


def test_matrix_rejects_tampered_evaluation_identity(tmp_path: Path) -> None:
    matrix_path = _matrix(tmp_path / "matrix.json")
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    payload["evaluations"][0]["evaluation_id"] = "evaluation-" + "0" * 32
    matrix_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="evaluation_id"):
        load_experiment_matrix(matrix_path)


@pytest.mark.asyncio
async def test_planned_evaluation_replays_only_test_slice(
    tmp_path: Path,
) -> None:
    root = _root()
    matrix_path = _matrix(tmp_path / "matrix.json")
    planned = load_experiment_matrix(matrix_path).evaluations[0]
    result = await run_planned_evaluation(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        matrix_path=matrix_path,
        evaluation_id=planned.evaluation_id,
        output_root=tmp_path / "runs",
        code_revision="phase4-evaluation-test",
    )
    assert (
        result.experiment.manifest.dataset_semantic_sha256
        == planned.test_semantic_sha256
    )
    assert (
        result.experiment.manifest.config_canonical_sha256
        == planned.candidate_config_sha256
    )
    assert result.experiment.replay_report["events_received"] == (
        planned.window["test_end"] - planned.window["test_start"]
    )
    assert result.evaluation_path.is_file()


@pytest.mark.asyncio
async def test_registry_requires_trust_and_exact_matrix_binding(
    tmp_path: Path,
) -> None:
    root = _root()
    matrix_path = _matrix(tmp_path / "matrix.json")
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
async def test_aggregation_withholds_selection_and_alpha(
    tmp_path: Path,
) -> None:
    root = _root()
    matrix_path = _matrix(tmp_path / "matrix.json")
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
