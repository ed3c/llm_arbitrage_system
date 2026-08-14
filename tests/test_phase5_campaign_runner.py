from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.campaign_runner import (
    campaign_status,
    run_campaign,
)
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.evaluation import load_experiment_matrix
from llm_arbitrage_system.experiments.registry import ExperimentRegistry
from llm_arbitrage_system.experiments.signing import generate_signing_keypair
from llm_arbitrage_system.experiments.walk_forward import (
    load_sweep_spec,
    matrix_payload,
)


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, tuple[str, ...]]:
    root = Path(__file__).parents[1]
    dataset_path = root / "examples/phase3/market_events.jsonl"
    config_path = root / "examples/phase3/experiment.yaml"
    dataset = load_jsonl_dataset(dataset_path)
    config = load_experiment_config(config_path)
    sweep = load_sweep_spec(root / "examples/phase3/sweep.yaml")
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_bytes(
        canonical_json_bytes(matrix_payload(dataset, config.config, sweep)) + b"\n"
    )
    matrix = load_experiment_matrix(matrix_path)
    evaluation_ids = tuple(item.evaluation_id for item in matrix.evaluations[:2])
    return dataset_path, config_path, matrix_path, evaluation_ids


def _campaign(path: Path, evaluation_ids: tuple[str, ...], *, stop: bool) -> None:
    quoted = "\n".join(f"    - {evaluation_id}" for evaluation_id in evaluation_ids)
    path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "execution:",
                "  maximum_parallel_evaluations: 1",
                "  maximum_failures: 1",
                f"  stop_on_failure: {'true' if stop else 'false'}",
                "selection:",
                "  include_evaluation_ids:",
                quoted,
                "  exclude_evaluation_ids: []",
                "",
            ]
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_campaign_runs_signs_registers_and_resumes(tmp_path: Path) -> None:
    dataset, config, matrix, evaluation_ids = _inputs(tmp_path)
    campaign_path = tmp_path / "campaign.yaml"
    _campaign(campaign_path, evaluation_ids, stop=False)
    private_key = tmp_path / "keys/private.pem"
    public_key = tmp_path / "keys/public.pem"
    generate_signing_keypair(private_key, public_key)
    registry_path = tmp_path / "registry.sqlite3"
    with ExperimentRegistry(registry_path) as registry:
        registry.trust_public_key(public_key)

    first = await run_campaign(
        dataset_path=dataset,
        config_path=config,
        matrix_path=matrix,
        campaign_path=campaign_path,
        registry_path=registry_path,
        private_key_path=private_key,
        output_root=tmp_path / "campaigns",
        code_revision="phase5-runner-test",
    )
    second = await run_campaign(
        dataset_path=dataset,
        config_path=config,
        matrix_path=matrix,
        campaign_path=campaign_path,
        registry_path=registry_path,
        private_key_path=private_key,
        output_root=tmp_path / "campaigns",
        code_revision="phase5-runner-test",
    )

    assert first.manifest == second.manifest
    assert first.summary.status == "completed"
    assert first.summary.registered == 2
    assert first.summary.failed == 0
    assert first.aggregate["registered_evaluation_count"] == 2
    assert (first.workspace / "manifest.json").is_file()
    assert (first.workspace / "campaign.sqlite3").is_file()
    assert (first.workspace / "aggregate.json").is_file()
    assert (first.workspace / "report.json").is_file()
    assert len(tuple((first.workspace / "attestations").glob("*.json"))) == 2
    assert campaign_status(first.workspace)["summary"]["status"] == "completed"

    with ExperimentRegistry(registry_path) as registry:
        summary = registry.verify()
    assert summary.evaluations == 2


def test_campaign_status_rejects_missing_workspace(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        campaign_status(tmp_path / "missing")


@pytest.mark.asyncio
async def test_campaign_skips_trusted_registry_evidence_in_a_new_identity(
    tmp_path: Path,
) -> None:
    dataset, config, matrix, evaluation_ids = _inputs(tmp_path)
    first_campaign = tmp_path / "first.yaml"
    second_campaign = tmp_path / "second.yaml"
    _campaign(first_campaign, evaluation_ids, stop=False)
    second_campaign.write_text(
        first_campaign.read_text(encoding="utf-8").replace(
            "maximum_parallel_evaluations: 1",
            "maximum_parallel_evaluations: 2",
        ),
        encoding="utf-8",
    )
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    generate_signing_keypair(private_key, public_key)
    registry_path = tmp_path / "registry.sqlite3"
    with ExperimentRegistry(registry_path) as registry:
        registry.trust_public_key(public_key)

    await run_campaign(
        dataset_path=dataset,
        config_path=config,
        matrix_path=matrix,
        campaign_path=first_campaign,
        registry_path=registry_path,
        private_key_path=private_key,
        output_root=tmp_path / "campaigns",
        code_revision="phase5-skip-test",
    )
    skipped = await run_campaign(
        dataset_path=dataset,
        config_path=config,
        matrix_path=matrix,
        campaign_path=second_campaign,
        registry_path=registry_path,
        private_key_path=private_key,
        output_root=tmp_path / "campaigns",
        code_revision="phase5-skip-test",
    )

    assert skipped.summary.status == "completed"
    assert skipped.summary.registered == 0
    assert skipped.summary.skipped_existing == 2
    assert not any((skipped.workspace / "evaluations").iterdir())


@pytest.mark.asyncio
async def test_campaign_stops_after_untrusted_registration_failure(
    tmp_path: Path,
) -> None:
    dataset, config, matrix, evaluation_ids = _inputs(tmp_path)
    campaign_path = tmp_path / "campaign.yaml"
    _campaign(campaign_path, evaluation_ids, stop=True)
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    generate_signing_keypair(private_key, public_key)
    registry_path = tmp_path / "registry.sqlite3"
    with ExperimentRegistry(registry_path) as registry:
        assert registry.verify().trusted_keys == 0

    result = await run_campaign(
        dataset_path=dataset,
        config_path=config,
        matrix_path=matrix,
        campaign_path=campaign_path,
        registry_path=registry_path,
        private_key_path=private_key,
        output_root=tmp_path / "campaigns",
        code_revision="phase5-untrusted-test",
    )

    assert result.summary.status == "failed"
    assert result.summary.failed == 1
    assert result.summary.pending == 1
    report = json.loads((result.workspace / "report.json").read_text(encoding="utf-8"))
    assert report["selection"] is None
    assert report["realized_pnl"] is None
    assert report["sharpe_ratio"] is None
    assert report["alpha_decay"] is None


@pytest.mark.asyncio
async def test_campaign_rejects_existing_evidence_from_a_different_signer(
    tmp_path: Path,
) -> None:
    dataset, config, matrix, evaluation_ids = _inputs(tmp_path)
    first_campaign = tmp_path / "first.yaml"
    second_campaign = tmp_path / "second.yaml"
    _campaign(first_campaign, evaluation_ids, stop=False)
    second_campaign.write_text(
        first_campaign.read_text(encoding="utf-8").replace(
            "maximum_parallel_evaluations: 1",
            "maximum_parallel_evaluations: 2",
        ),
        encoding="utf-8",
    )
    first_private = tmp_path / "first-private.pem"
    first_public = tmp_path / "first-public.pem"
    second_private = tmp_path / "second-private.pem"
    second_public = tmp_path / "second-public.pem"
    generate_signing_keypair(first_private, first_public)
    generate_signing_keypair(second_private, second_public)
    registry_path = tmp_path / "registry.sqlite3"
    with ExperimentRegistry(registry_path) as registry:
        registry.trust_public_key(first_public)
        registry.trust_public_key(second_public)

    await run_campaign(
        dataset_path=dataset,
        config_path=config,
        matrix_path=matrix,
        campaign_path=first_campaign,
        registry_path=registry_path,
        private_key_path=first_private,
        output_root=tmp_path / "campaigns",
        code_revision="phase5-signer-drift-test",
    )

    with pytest.raises(RuntimeError, match="different signer"):
        await run_campaign(
            dataset_path=dataset,
            config_path=config,
            matrix_path=matrix,
            campaign_path=second_campaign,
            registry_path=registry_path,
            private_key_path=second_private,
            output_root=tmp_path / "campaigns",
            code_revision="phase5-signer-drift-test",
        )
