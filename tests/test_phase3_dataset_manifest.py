from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import (
    DatasetValidationError,
    load_jsonl_dataset,
)
from llm_arbitrage_system.experiments.manifest import build_experiment_manifest


def _record(timestamp: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "venue": "paper",
        "symbol": "BTC",
        "instrument": "perp",
        "price": "100.00",
        "timestamp": timestamp,
        "metadata": {"paper_hedge_symbol": "BTC-SPOT"},
    }
    payload.update(extra)
    return payload


def _write_config(path: Path, *, reversed_order: bool = False) -> None:
    if reversed_order:
        value = (
            "runtime:\n  queue_size: 8\nexecution:\n  fee_bps: \"1\"\n"
            "  slippage_bps: \"5\"\n  fail_leg_indexes: []\nschema_version: 1\n"
        )
    else:
        value = (
            "schema_version: 1\nexecution:\n  slippage_bps: \"5\"\n"
            "  fee_bps: \"1\"\n  fail_leg_indexes: []\nruntime:\n  queue_size: 8\n"
        )
    path.write_text(value, encoding="utf-8")


def test_dataset_semantic_hash_ignores_json_whitespace(tmp_path: Path) -> None:
    compact = tmp_path / "compact.jsonl"
    spaced = tmp_path / "spaced.jsonl"
    record = _record("2026-01-01T00:00:00Z")
    compact.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")
    spaced.write_text(json.dumps(record, separators=(", ", ": ")) + "\n", encoding="utf-8")

    compact_snapshot = load_jsonl_dataset(compact)
    spaced_snapshot = load_jsonl_dataset(spaced)

    assert compact_snapshot.source_sha256 != spaced_snapshot.source_sha256
    assert compact_snapshot.semantic_sha256 == spaced_snapshot.semantic_sha256
    assert compact_snapshot.event_sha256 == spaced_snapshot.event_sha256


def test_dataset_rejects_unknown_fields_and_time_reversal(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.jsonl"
    unknown.write_text(
        json.dumps(_record("2026-01-01T00:00:00Z", mystery="x")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError, match="unknown fields: mystery"):
        load_jsonl_dataset(unknown)

    reversed_time = tmp_path / "reversed.jsonl"
    reversed_time.write_text(
        "\n".join(
            [
                json.dumps(_record("2026-01-01T00:01:00Z")),
                json.dumps(_record("2026-01-01T00:00:00Z")),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError, match="non-decreasing"):
        load_jsonl_dataset(reversed_time)


def test_manifest_identity_uses_semantic_inputs(tmp_path: Path) -> None:
    dataset_a = tmp_path / "a.jsonl"
    dataset_b = tmp_path / "b.jsonl"
    record = _record("2026-01-01T00:00:00Z")
    dataset_a.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")
    dataset_b.write_text(json.dumps(record, separators=(", ", ": ")) + "\n", encoding="utf-8")
    config_a = tmp_path / "a.yaml"
    config_b = tmp_path / "b.yaml"
    _write_config(config_a)
    _write_config(config_b, reversed_order=True)

    manifest_a = build_experiment_manifest(
        load_jsonl_dataset(dataset_a),
        load_experiment_config(config_a),
        code_revision="abc123",
        package_version="0.1.0",
    )
    manifest_b = build_experiment_manifest(
        load_jsonl_dataset(dataset_b),
        load_experiment_config(config_b),
        code_revision="abc123",
        package_version="0.1.0",
    )

    assert manifest_a.experiment_id == manifest_b.experiment_id
    assert manifest_a.run_id == manifest_b.run_id
    assert manifest_a.dataset_source_sha256 != manifest_b.dataset_source_sha256
    assert manifest_a.config_source_sha256 != manifest_b.config_source_sha256


def test_dataset_rejects_duplicate_keys_and_float_money(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(
        '{"schema_version":1,"venue":"paper","symbol":"BTC","symbol":"ETH",'
        '"instrument":"perp","price":"100","timestamp":"2026-01-01T00:00:00Z"}\n',
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError, match="duplicate JSON object key: symbol"):
        load_jsonl_dataset(duplicate)

    float_money = tmp_path / "float-money.jsonl"
    float_money.write_text(
        json.dumps(_record("2026-01-01T00:00:00Z", price=100.0)) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(DatasetValidationError, match="not a float"):
        load_jsonl_dataset(float_money)


def test_config_rejects_duplicate_keys_and_float_money(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        "schema_version: 1\nruntime:\n  queue_size: 8\nruntime:\n  queue_size: 16\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate key"):
        load_experiment_config(duplicate)

    float_money = tmp_path / "float-money.yaml"
    float_money.write_text(
        "schema_version: 1\nexecution:\n  slippage_bps: 5.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not a float"):
        load_experiment_config(float_money)
