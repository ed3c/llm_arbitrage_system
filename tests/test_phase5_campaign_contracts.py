from __future__ import annotations

from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.campaign import (
    CampaignExecutionPolicy,
    CampaignSelection,
    build_campaign_manifest,
    load_campaign_spec,
    parse_campaign_spec,
    resolve_campaign_evaluation_ids,
)
from llm_arbitrage_system.experiments.campaign_store import CampaignStore
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.evaluation import load_experiment_matrix
from llm_arbitrage_system.experiments.signing import generate_signing_keypair
from llm_arbitrage_system.experiments.walk_forward import (
    load_sweep_spec,
    matrix_payload,
)


def _matrix(tmp_path: Path):
    root = Path(__file__).parents[1]
    dataset = load_jsonl_dataset(root / "examples/phase3/market_events.jsonl")
    config = load_experiment_config(root / "examples/phase3/experiment.yaml")
    sweep = load_sweep_spec(root / "examples/phase3/sweep.yaml")
    path = tmp_path / "matrix.json"
    path.write_bytes(
        canonical_json_bytes(matrix_payload(dataset, config.config, sweep)) + b"\n"
    )
    return load_experiment_matrix(path)


def test_campaign_manifest_is_content_addressed_and_selection_is_ordered(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    matrix = _matrix(tmp_path)
    campaign = load_campaign_spec(root / "examples/phase5/campaign.yaml")
    selected = resolve_campaign_evaluation_ids(matrix, campaign.spec.selection)

    private_key = tmp_path / "signing.pem"
    public_key = tmp_path / "signing.pub.pem"
    identity = generate_signing_keypair(private_key, public_key)
    first = build_campaign_manifest(
        matrix,
        campaign,
        selected,
        code_revision="phase5-contract-test",
        signer_key_id=identity.key_id,
        package_version="0.1.0",
    )
    second = build_campaign_manifest(
        matrix,
        campaign,
        selected,
        code_revision="phase5-contract-test",
        signer_key_id=identity.key_id,
        package_version="0.1.0",
    )

    assert first == second
    assert first.campaign_id.startswith("campaign-")
    assert first.evaluation_count == len(matrix.evaluations)
    assert selected == tuple(item.evaluation_id for item in matrix.evaluations)


def test_campaign_selection_supports_explicit_include_and_exclude(
    tmp_path: Path,
) -> None:
    matrix = _matrix(tmp_path)
    first, second, third = (item.evaluation_id for item in matrix.evaluations[:3])
    selection = CampaignSelection(
        include_evaluation_ids=(first, second, third),
        exclude_evaluation_ids=(second,),
    )
    assert resolve_campaign_evaluation_ids(matrix, selection) == (first, third)

    with pytest.raises(ValueError, match="unknown evaluations"):
        resolve_campaign_evaluation_ids(
            matrix,
            CampaignSelection(include_evaluation_ids=("evaluation-missing",)),
        )


def test_campaign_contract_fails_closed_on_invalid_fields() -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        parse_campaign_spec({"schema_version": 1, "unexpected": True})
    with pytest.raises(ValueError, match="cannot contain duplicates"):
        CampaignSelection(include_evaluation_ids=("evaluation-a", "evaluation-a"))
    with pytest.raises(ValueError, match="include and exclude"):
        CampaignSelection(
            include_evaluation_ids=("evaluation-a",),
            exclude_evaluation_ids=("evaluation-a",),
        )
    with pytest.raises(ValueError, match=r"\[1, 16\]"):
        CampaignExecutionPolicy(maximum_parallel_evaluations=17)
    with pytest.raises(ValueError, match=r"\[1, 4096\]"):
        CampaignExecutionPolicy(maximum_failures=0)


def test_campaign_store_recovers_interrupted_and_enforces_terminal_states(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    matrix = _matrix(tmp_path)
    campaign = load_campaign_spec(root / "examples/phase5/campaign.yaml")
    selected = resolve_campaign_evaluation_ids(matrix, campaign.spec.selection)[:2]
    private_key = tmp_path / "signing.pem"
    public_key = tmp_path / "signing.pub.pem"
    identity = generate_signing_keypair(private_key, public_key)
    manifest = build_campaign_manifest(
        matrix,
        campaign,
        selected,
        code_revision="phase5-store-test",
        signer_key_id=identity.key_id,
        package_version="0.1.0",
    )

    store_path = tmp_path / "campaign.sqlite3"
    with CampaignStore(store_path) as store:
        assert store.initialize(manifest, selected)["status"] == "initialized"
        assert store.initialize(manifest, selected)["status"] == "already_initialized"
        store.start(manifest.campaign_id)
        store.mark_running(manifest.campaign_id, selected[0])
        assert store.recover_interrupted(manifest.campaign_id) == 1
        store.mark_running(manifest.campaign_id, selected[0])
        store.mark_registered(
            manifest.campaign_id,
            selected[0],
            experiment_id="exp-test",
            bundle_path=tmp_path / "bundle",
            attestation_path=tmp_path / "attestation.json",
        )
        store.mark_skipped_existing(
            manifest.campaign_id,
            selected[1],
            experiment_id="exp-existing",
        )
        store.finish(manifest.campaign_id, "completed")
        summary = store.summary(manifest.campaign_id)

    assert summary.integrity == "ok"
    assert summary.status == "completed"
    assert summary.registered == 1
    assert summary.skipped_existing == 1
    assert summary.recovered_interrupted == 1


def test_campaign_store_rejects_manifest_or_evaluation_drift(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    matrix = _matrix(tmp_path)
    campaign = load_campaign_spec(root / "examples/phase5/campaign.yaml")
    selected = resolve_campaign_evaluation_ids(matrix, campaign.spec.selection)[:1]
    identity = generate_signing_keypair(
        tmp_path / "private.pem",
        tmp_path / "public.pem",
    )
    manifest = build_campaign_manifest(
        matrix,
        campaign,
        selected,
        code_revision="phase5-drift-test",
        signer_key_id=identity.key_id,
        package_version="0.1.0",
    )

    with CampaignStore(tmp_path / "campaign.sqlite3") as store:
        store.initialize(manifest, selected)
        with pytest.raises(RuntimeError, match="evaluation set conflicts"):
            store.initialize(manifest, selected + ("evaluation-extra",))
        store.start(manifest.campaign_id)
        with pytest.raises(RuntimeError, match="cannot finish"):
            store.finish(manifest.campaign_id, "completed")
