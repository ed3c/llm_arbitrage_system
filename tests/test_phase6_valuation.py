from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.runner import run_experiment
from llm_arbitrage_system.experiments.valuation import (
    load_terminal_marks,
    value_bundle,
)


def _write_marks(
    path: Path,
    *,
    as_of: str = "2026-01-01T00:12:00Z",
    marks: list[tuple[str, str]] | None = None,
) -> Path:
    items = marks if marks is not None else [
        ("BTC:PERP", "100.6"),
        ("BTC-SPOT", "100.6"),
    ]
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "as_of": as_of,
                "marks": [
                    {"symbol": symbol, "price": price}
                    for symbol, price in items
                ],
            },
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_terminal_marks_are_strict_and_semantically_content_addressed(
    tmp_path: Path,
) -> None:
    first = load_terminal_marks(
        _write_marks(
            tmp_path / "first.json",
            marks=[("BTC:PERP", "100.6"), ("BTC-SPOT", "100.6")],
        )
    )
    second = load_terminal_marks(
        _write_marks(
            tmp_path / "second.json",
            marks=[("BTC-SPOT", "100.6"), ("BTC:PERP", "100.6")],
        )
    )

    assert first.source_sha256 != second.source_sha256
    assert first.semantic_sha256 == second.semantic_sha256
    assert tuple(mark.symbol for mark in first.marks) == ("BTC-SPOT", "BTC:PERP")
    assert first.summary()["mark_count"] == 2


def test_terminal_marks_fail_closed_on_invalid_documents(tmp_path: Path) -> None:
    cases = {
        "duplicate-key.json": (
            '{"schema_version":1,"schema_version":1,"as_of":"2026-01-01T00:12:00Z","marks":[]}\n',
            "duplicate",
        ),
        "unknown.json": (
            '{"schema_version":1,"as_of":"2026-01-01T00:12:00Z","marks":[],"extra":true}\n',
            "unknown or missing",
        ),
        "naive.json": (
            '{"schema_version":1,"as_of":"2026-01-01T00:12:00","marks":[]}\n',
            "timezone",
        ),
        "float-price.json": (
            '{"schema_version":1,"as_of":"2026-01-01T00:12:00Z","marks":[{"symbol":"BTC","price":100.6}]}\n',
            "not a float",
        ),
        "duplicate-symbol.json": (
            '{"schema_version":1,"as_of":"2026-01-01T00:12:00Z","marks":[{"symbol":"BTC","price":"100"},{"symbol":"BTC","price":"101"}]}\n',
            "duplicate terminal mark symbol",
        ),
        "non-finite.json": (
            '{"schema_version":1,"as_of":"2026-01-01T00:12:00Z","marks":[{"symbol":"BTC","price":NaN}]}\n',
            "non-finite",
        ),
    }
    for filename, (content, message) in cases.items():
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            load_terminal_marks(path)


@pytest.mark.asyncio
async def test_bundle_valuation_separates_settlement_cash_from_terminal_pnl(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    experiment = await run_experiment(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase6-valuation-bundle",
    )
    marks_path = _write_marks(tmp_path / "marks.json")

    first = value_bundle(
        experiment.bundle.bundle_path,
        marks_path,
        code_revision="phase6-valuation-test",
        package_version="0.1.0",
    )
    second = value_bundle(
        experiment.bundle.bundle_path,
        marks_path,
        code_revision="phase6-valuation-test",
        package_version="0.1.0",
    )

    assert first == second
    assert first.execution_result_count == 1
    assert first.fill_count == 2
    assert first.fees_usd > 0
    assert first.gross_turnover_usd > 0
    assert len(first.positions) == 2
    assert first.mark_to_market_pnl_usd == (
        first.settlement_cash_usd + first.open_position_market_value_usd
    )
    assert first.mark_to_market_pnl_usd != first.settlement_cash_usd
    payload = first.as_dict()
    assert payload["metrics"]["mark_to_market_pnl_usd"] == str(
        first.mark_to_market_pnl_usd
    )
    assert "realized_pnl_usd" not in payload["metrics"]


@pytest.mark.asyncio
async def test_valuation_identity_changes_with_marks_or_code_revision(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    experiment = await run_experiment(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase6-identity-bundle",
    )
    first_marks = _write_marks(tmp_path / "first.json")
    second_marks = _write_marks(
        tmp_path / "second.json",
        marks=[("BTC:PERP", "101.0"), ("BTC-SPOT", "100.6")],
    )

    first = value_bundle(
        experiment.bundle.bundle_path,
        first_marks,
        code_revision="revision-a",
        package_version="0.1.0",
    )
    changed_marks = value_bundle(
        experiment.bundle.bundle_path,
        second_marks,
        code_revision="revision-a",
        package_version="0.1.0",
    )
    changed_revision = value_bundle(
        experiment.bundle.bundle_path,
        first_marks,
        code_revision="revision-b",
        package_version="0.1.0",
    )

    assert first.valuation_id != changed_marks.valuation_id
    assert first.valuation_id != changed_revision.valuation_id
    assert first.mark_to_market_pnl_usd != changed_marks.mark_to_market_pnl_usd


@pytest.mark.asyncio
async def test_bundle_valuation_requires_exact_fresh_open_position_marks(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    experiment = await run_experiment(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase6-coverage-bundle",
    )

    missing = _write_marks(
        tmp_path / "missing.json",
        marks=[("BTC:PERP", "100.6")],
    )
    extra = _write_marks(
        tmp_path / "extra.json",
        marks=[
            ("BTC:PERP", "100.6"),
            ("BTC-SPOT", "100.6"),
            ("ETH", "2000"),
        ],
    )
    stale = _write_marks(
        tmp_path / "stale.json",
        as_of="2026-01-01T00:10:00Z",
    )

    with pytest.raises(ValueError, match="missing open positions"):
        value_bundle(
            experiment.bundle.bundle_path,
            missing,
            code_revision="phase6-coverage-test",
        )
    with pytest.raises(ValueError, match="non-open positions"):
        value_bundle(
            experiment.bundle.bundle_path,
            extra,
            code_revision="phase6-coverage-test",
        )
    with pytest.raises(ValueError, match="cannot precede"):
        value_bundle(
            experiment.bundle.bundle_path,
            stale,
            code_revision="phase6-coverage-test",
        )


@pytest.mark.asyncio
async def test_compensated_evidence_values_closed_positions_without_marks(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    source_config = (root / "examples/phase3/experiment.yaml").read_text(
        encoding="utf-8"
    )
    compensated_config = tmp_path / "compensated.yaml"
    compensated_config.write_text(
        source_config.replace("fail_leg_indexes: []", "fail_leg_indexes: [1]"),
        encoding="utf-8",
    )
    experiment = await run_experiment(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=compensated_config,
        output_root=tmp_path / "runs",
        code_revision="phase6-compensation-bundle",
    )
    empty_marks = _write_marks(tmp_path / "empty.json", marks=[])

    report = value_bundle(
        experiment.bundle.bundle_path,
        empty_marks,
        code_revision="phase6-compensation-test",
        package_version="0.1.0",
    )

    assert report.fill_count == 2
    assert report.positions == ()
    assert report.open_position_market_value_usd == 0
    assert report.mark_to_market_pnl_usd == report.settlement_cash_usd
    assert report.mark_to_market_pnl_usd == -report.fees_usd
