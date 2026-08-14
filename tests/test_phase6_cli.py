from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import llm_arbitrage_system.experiments.cli as cli_module
from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.cli import main
from llm_arbitrage_system.experiments.statistics_signing import (
    load_statistics_report,
)


def _minimal_statistics_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_id": "oos-report-" + "a" * 40,
        "matrix_sha256": "b" * 64,
        "code_revision": "phase6-cli-test",
        "package_version": "0.1.0",
        "periods_per_year": 252,
        "candidates": [{"candidate_id": "candidate-test"}],
        "selection": None,
        "assumptions": ["Synthetic canonical report for CLI signing tests."],
        "evidence_boundary": "Synthetic test evidence only.",
    }


def test_phase6_cli_values_bundle_and_signs_statistics(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    runs = tmp_path / "runs"
    assert (
        main(
            [
                "run",
                "--dataset",
                str(root / "examples/phase3/market_events.jsonl"),
                "--config",
                str(root / "examples/phase3/experiment.yaml"),
                "--output",
                str(runs),
                "--code-revision",
                "phase6-cli-bundle",
            ]
        )
        == 0
    )
    bundle = next(runs.glob("exp-*"))
    marks = root / "examples/phase6/terminal_marks.json"
    valuation = tmp_path / "valuation.json"
    assert main(["validate-marks", str(marks)]) == 0
    assert (
        main(
            [
                "value-bundle",
                "--bundle",
                str(bundle),
                "--marks",
                str(marks),
                "--output",
                str(valuation),
                "--code-revision",
                "phase6-cli-valuation",
            ]
        )
        == 0
    )
    valuation_payload = json.loads(valuation.read_text(encoding="utf-8"))
    assert valuation_payload["metrics"]["mark_to_market_pnl_usd"]
    assert "realized_pnl_usd" not in valuation_payload["metrics"]
    assert (
        main(
            [
                "value-bundle",
                "--bundle",
                str(bundle),
                "--marks",
                str(marks),
                "--output",
                str(valuation),
            ]
        )
        == 2
    )

    report = tmp_path / "statistics.json"
    write_json(report, _minimal_statistics_report())
    private_key = tmp_path / "keys/private.pem"
    public_key = tmp_path / "keys/public.pem"
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
    attestation = tmp_path / "statistics.attestation.json"
    assert (
        main(
            [
                "sign-statistics",
                "--report",
                str(report),
                "--private-key",
                str(private_key),
                "--output",
                str(attestation),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-statistics",
                "--report",
                str(report),
                "--attestation",
                str(attestation),
                "--trusted-public-key",
                str(public_key),
            ]
        )
        == 0
    )
    expected_report_id = _minimal_statistics_report()["report_id"]
    assert load_statistics_report(report).report_id == expected_report_id

    tampered = _minimal_statistics_report()
    tampered["periods_per_year"] = 365
    write_json(report, tampered)
    assert (
        main(
            [
                "verify-statistics",
                "--report",
                str(report),
                "--attestation",
                str(attestation),
                "--trusted-public-key",
                str(public_key),
            ]
        )
        == 2
    )


def test_phase6_statistics_input_manifest_and_cli_wiring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    marks = tmp_path / "marks.json"
    marks.write_text("{}\n", encoding="utf-8")
    input_manifest = tmp_path / "statistics-inputs.json"
    input_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "candidate_ids": ["candidate-test"],
                "valuations": [
                    {
                        "evaluation_id": "evaluation-test",
                        "bundle": "bundle",
                        "marks": "marks.json",
                    }
                ],
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    assert main(["validate-statistics-inputs", str(input_manifest)]) == 0

    class _FakeReport:
        def as_dict(self) -> dict[str, Any]:
            return _minimal_statistics_report()

    captured: dict[str, Any] = {}

    def _fake_build(**kwargs: Any) -> _FakeReport:
        captured.update(kwargs)
        return _FakeReport()

    monkeypatch.setattr(cli_module, "build_oos_statistics", _fake_build)
    output = tmp_path / "oos.json"
    assert (
        main(
            [
                "campaign-statistics",
                "--registry",
                str(tmp_path / "registry.sqlite3"),
                "--matrix",
                str(tmp_path / "matrix.json"),
                "--inputs",
                str(input_manifest),
                "--initial-equity",
                "100000",
                "--periods-per-year",
                "252",
                "--output",
                str(output),
                "--code-revision",
                "phase6-cli-statistics",
            ]
        )
        == 0
    )
    assert captured["candidate_ids"] == ("candidate-test",)
    assert captured["initial_equity_usd"] == 100000
    assert output.is_file()

    invalid = tmp_path / "invalid-inputs.json"
    invalid.write_text(
        '{"schema_version":1,"candidate_ids":[],"valuations":[]}\n',
        encoding="utf-8",
    )
    assert main(["validate-statistics-inputs", str(invalid)]) == 2


def test_statistics_signing_rejects_noncanonical_report_and_wrong_key(
    tmp_path: Path,
) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(_minimal_statistics_report(), indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="canonical JSON"):
        load_statistics_report(report)

    write_json(report, _minimal_statistics_report())
    first_private = tmp_path / "first/private.pem"
    first_public = tmp_path / "first/public.pem"
    second_private = tmp_path / "second/private.pem"
    second_public = tmp_path / "second/public.pem"
    assert (
        main(
            [
                "keygen",
                "--private-key",
                str(first_private),
                "--public-key",
                str(first_public),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "keygen",
                "--private-key",
                str(second_private),
                "--public-key",
                str(second_public),
            ]
        )
        == 0
    )
    attestation = tmp_path / "attestation.json"
    assert (
        main(
            [
                "sign-statistics",
                "--report",
                str(report),
                "--private-key",
                str(first_private),
                "--output",
                str(attestation),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-statistics",
                "--report",
                str(report),
                "--attestation",
                str(attestation),
                "--trusted-public-key",
                str(second_public),
            ]
        )
        == 2
    )
