from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from llm_arbitrage_system.experiments.canonical import canonical_datetime, sha256_hex
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset


def manifest_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_schema_version": manifest.get("bundle_schema_version"),
        "dataset_semantic_sha256": nested_string(
            manifest, "dataset", "semantic_sha256"
        ),
        "config_canonical_sha256": nested_string(
            manifest, "configuration", "canonical_sha256"
        ),
        "code_revision": required_string(manifest, "code_revision"),
        "package_version": required_string(manifest, "package_version"),
    }


def verify_inputs(
    root: Path,
    manifest: dict[str, Any],
    identity: dict[str, Any],
) -> None:
    dataset_source_path = root / "inputs" / "dataset.source.jsonl"
    dataset_canonical_path = root / "inputs" / "dataset.canonical.jsonl"
    config_source_path = root / "inputs" / "config.source.yaml"
    config_canonical_path = root / "inputs" / "config.canonical.json"
    dataset_source = dataset_source_path.read_bytes()
    dataset_canonical = dataset_canonical_path.read_bytes()
    config_source = config_source_path.read_bytes()
    config_canonical = config_canonical_path.read_bytes()

    if sha256_hex(dataset_source) != nested_string(
        manifest, "dataset", "source_sha256"
    ):
        raise ValueError("dataset source hash does not match manifest")
    if sha256_hex(dataset_canonical) != identity["dataset_semantic_sha256"]:
        raise ValueError("dataset semantic hash does not match manifest")
    if sha256_hex(config_source) != nested_string(
        manifest, "configuration", "source_sha256"
    ):
        raise ValueError("configuration source hash does not match manifest")
    if sha256_hex(config_canonical) != identity["config_canonical_sha256"]:
        raise ValueError("configuration canonical hash does not match manifest")

    dataset_snapshot = load_jsonl_dataset(dataset_source_path)
    if dataset_snapshot.canonical_jsonl != dataset_canonical:
        raise ValueError("dataset canonical input does not match its source")
    if dataset_snapshot.event_count != nested_integer(
        manifest, "dataset", "event_count"
    ):
        raise ValueError("dataset event count does not match manifest")
    if canonical_datetime(dataset_snapshot.first_timestamp) != nested_string(
        manifest, "dataset", "first_event_at"
    ):
        raise ValueError("dataset first timestamp does not match manifest")
    if canonical_datetime(dataset_snapshot.last_timestamp) != nested_string(
        manifest, "dataset", "last_event_at"
    ):
        raise ValueError("dataset last timestamp does not match manifest")

    config_snapshot = load_experiment_config(config_source_path)
    if config_snapshot.canonical_bytes != config_canonical:
        raise ValueError("configuration canonical input does not match its source")


def json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("JSON document must contain an object")
    return cast(dict[str, Any], parsed)


def required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"manifest.{key} must be a non-empty string")
    return value


def nested_string(payload: dict[str, Any], section: str, key: str) -> str:
    nested = payload.get(section)
    if not isinstance(nested, dict):
        raise ValueError(f"manifest.{section} must be an object")
    value = cast(dict[str, Any], nested).get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"manifest.{section}.{key} must be a non-empty string")
    return value


def nested_integer(payload: dict[str, Any], section: str, key: str) -> int:
    nested = payload.get(section)
    if not isinstance(nested, dict):
        raise ValueError(f"manifest.{section} must be an object")
    value = cast(dict[str, Any], nested).get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"manifest.{section}.{key} must be an integer")
    return value
