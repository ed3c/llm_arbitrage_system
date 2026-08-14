from __future__ import annotations

import json
import shutil
from pathlib import Path

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.cli import main
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.walk_forward import (
    load_sweep_spec,
    matrix_payload,
)


def _write_matrix_and_campaign(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    root = Path(__file__).parents[1]
    dataset = root / "examples/phase3/market_events.jsonl"
    config = root / "examples/phase3/experiment.yaml"
    sweep = root / "examples/phase3/sweep.yaml"
    matrix = tmp_path / "matrix.json"
    payload = matrix_payload(
        load_jsonl_dataset(dataset),
        load_experiment_config(config).config,
        load_sweep_spec(sweep),
    )
    matrix.write_bytes(canonical_json_bytes(payload) + b"\n")
    evaluation_ids = [
        str(item["evaluation_id"])
        for item in payload["evaluations"][:2]
    ]
    campaign = tmp_path / "campaign.yaml"
    campaign.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "execution:",
                "  maximum_parallel_evaluations: 2",
                "  maximum_failures: 1",
                "  stop_on_failure: true",
                "selection:",
                "  include_evaluation_ids:",
                *(f"    - {evaluation_id}" for evaluation_id in evaluation_ids),
                "  exclude_evaluation_ids: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return dataset, config, matrix, campaign


def test_phase5_cli_validates_runs_and_reports_campaign(tmp_path: Path) -> None:
    dataset, config, matrix, campaign = _write_matrix_and_campaign(tmp_path)
    private_key = tmp_path / "keys/provenance.pem"
    public_key = tmp_path / "keys/provenance.pub.pem"
    registry = tmp_path / "registry.sqlite3"
    output = tmp_path / "campaigns"

    assert (
        main(
            [
                "keygen",
                "--private-key",
                str(private_key),
                "--public-key",
                str(public_key),
            ]
        )
        == 0
    )
    assert main(["registry-init", str(registry)]) == 0
    assert (
        main(
            [
                "registry-trust-key",
                str(registry),
                str(public_key),
                "--label",
                "phase5-cli-test",
            ]
        )
        == 0
    )
    assert main(["validate-campaign", str(campaign)]) == 0
    assert (
        main(
            [
                "run-campaign",
                "--dataset",
                str(dataset),
                "--config",
                str(config),
                "--matrix",
                str(matrix),
                "--campaign",
                str(campaign),
                "--registry",
                str(registry),
                "--private-key",
                str(private_key),
                "--output",
                str(output),
                "--code-revision",
                "phase5-cli-test",
            ]
        )
        == 0
    )

    workspace = next(output.glob("campaign-*"))
    assert main(["campaign-status", str(workspace)]) == 0
    assert main(["registry-verify", str(registry)]) == 0
    report = json.loads((workspace / "report.json").read_text(encoding="utf-8"))
    assert report["summary"]["status"] == "completed"
    assert report["summary"]["registered"] == 2
    assert report["selection"] is None
    assert report["realized_pnl"] is None
    assert report["sharpe_ratio"] is None
    assert report["alpha_decay"] is None

    nested_private_key = workspace / "provenance.pem"
    shutil.copyfile(private_key, nested_private_key)
    assert (
        main(
            [
                "run-campaign",
                "--dataset",
                str(dataset),
                "--config",
                str(config),
                "--matrix",
                str(matrix),
                "--campaign",
                str(campaign),
                "--registry",
                str(registry),
                "--private-key",
                str(nested_private_key),
                "--output",
                str(output),
                "--code-revision",
                "phase5-cli-test",
            ]
        )
        == 2
    )


def test_phase5_cli_rejects_invalid_campaign_and_unknown_workspace(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("schema_version: 1\nunexpected: true\n", encoding="utf-8")
    assert main(["validate-campaign", str(invalid)]) == 2
    assert main(["campaign-status", str(tmp_path / "missing")]) == 2
