from __future__ import annotations

import json
from pathlib import Path

from llm_arbitrage_system.experiments.cli import main


def test_phase3_cli_validation_run_verify_and_matrix(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    dataset = root / "examples" / "phase3" / "market_events.jsonl"
    config = root / "examples" / "phase3" / "experiment.yaml"
    sweep = root / "examples" / "phase3" / "sweep.yaml"
    output = tmp_path / "runs"

    assert main(["validate-dataset", str(dataset)]) == 0
    assert main(["validate-config", str(config)]) == 0
    assert (
        main(
            [
                "run",
                "--dataset",
                str(dataset),
                "--config",
                str(config),
                "--output",
                str(output),
                "--code-revision",
                "phase3-cli-test",
            ]
        )
        == 0
    )
    bundle = next(path for path in output.iterdir() if path.name.startswith("exp-"))
    assert main(["verify", str(bundle)]) == 0

    matrix = tmp_path / "matrix.json"
    assert (
        main(
            [
                "plan-matrix",
                "--dataset",
                str(dataset),
                "--config",
                str(config),
                "--sweep",
                str(sweep),
                "--output",
                str(matrix),
            ]
        )
        == 0
    )
    payload = json.loads(matrix.read_text(encoding="utf-8"))
    assert payload["candidate_count"] == 6
    assert payload["window_count"] == 2
    assert payload["evaluation_count"] == 12


def test_phase3_cli_returns_nonzero_for_invalid_input(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jsonl"
    assert main(["validate-dataset", str(missing)]) == 2
