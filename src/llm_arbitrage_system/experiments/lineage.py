from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_LINEAGE_SCHEMA_VERSION = 1
_ALLOWED_KINDS = {"source", "derived", "slice"}


@dataclass(frozen=True, slots=True)
class LineageOperation:
    name: str
    version: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("lineage operation name and version must be non-empty")

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True, slots=True)
class DatasetLineageManifest:
    lineage_id: str
    dataset_semantic_sha256: str
    kind: str
    operation: LineageOperation
    parents: tuple[str, ...]
    source_uri: str | None = None
    notes: tuple[str, ...] = ()

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": _LINEAGE_SCHEMA_VERSION,
            "dataset_semantic_sha256": self.dataset_semantic_sha256,
            "kind": self.kind,
            "operation": self.operation.as_dict(),
            "parents": list(self.parents),
            "source_uri": self.source_uri,
            "notes": list(self.notes),
        }

    def as_dict(self) -> dict[str, Any]:
        return {"lineage_id": self.lineage_id, **self.identity_payload()}


@dataclass(frozen=True, slots=True)
class LineageSnapshot:
    source_path: Path
    manifest: DatasetLineageManifest
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "manifest": self.manifest.as_dict(),
        }


def load_lineage_manifest(path: Path) -> LineageSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: lineage manifest is not UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid lineage YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("lineage manifest must be a mapping")
    manifest = parse_lineage_manifest(cast(Mapping[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(manifest.as_dict()) + b"\n"
    return LineageSnapshot(
        source_path=resolved,
        manifest=manifest,
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=sha256_hex(canonical_bytes),
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_lineage_manifest(payload: Mapping[str, Any]) -> DatasetLineageManifest:
    allowed = {
        "schema_version",
        "lineage_id",
        "dataset_semantic_sha256",
        "kind",
        "operation",
        "parents",
        "source_uri",
        "notes",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"lineage manifest contains unknown fields: {', '.join(unknown)}")
    if payload.get("schema_version") != _LINEAGE_SCHEMA_VERSION:
        raise ValueError("lineage schema_version must be 1")

    dataset_hash = _sha256(payload.get("dataset_semantic_sha256"), "dataset_semantic_sha256")
    kind = _required_string(payload.get("kind"), "kind")
    if kind not in _ALLOWED_KINDS:
        raise ValueError(f"lineage kind must be one of: {', '.join(sorted(_ALLOWED_KINDS))}")

    operation_value = payload.get("operation")
    if not isinstance(operation_value, dict):
        raise ValueError("lineage operation must be a mapping")
    operation_payload = cast(Mapping[str, Any], operation_value)
    operation_unknown = sorted(set(operation_payload) - {"name", "version", "parameters"})
    if operation_unknown:
        raise ValueError(
            f"lineage operation contains unknown fields: {', '.join(operation_unknown)}"
        )
    parameters = operation_payload.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("lineage operation.parameters must be a mapping")
    _validate_json_value(parameters, "operation.parameters")
    operation = LineageOperation(
        name=_required_string(operation_payload.get("name"), "operation.name"),
        version=_required_string(operation_payload.get("version"), "operation.version"),
        parameters=cast(Mapping[str, Any], parameters),
    )

    parents_value = payload.get("parents", [])
    if not isinstance(parents_value, list):
        raise ValueError("lineage parents must be a sequence")
    parents = tuple(sorted(_lineage_id(item, "parent") for item in parents_value))
    if len(set(parents)) != len(parents):
        raise ValueError("lineage parents cannot contain duplicates")
    if kind == "source" and parents:
        raise ValueError("source lineage cannot have parents")
    if kind != "source" and not parents:
        raise ValueError("derived and slice lineage require at least one parent")

    source_uri_value = payload.get("source_uri")
    if source_uri_value is not None and not isinstance(source_uri_value, str):
        raise ValueError("lineage source_uri must be a string or null")
    source_uri = cast(str | None, source_uri_value)
    if source_uri is not None and not source_uri.strip():
        raise ValueError("lineage source_uri cannot be empty")

    notes_value = payload.get("notes", [])
    if not isinstance(notes_value, list) or any(
        not isinstance(item, str) or not item for item in notes_value
    ):
        raise ValueError("lineage notes must be a sequence of non-empty strings")
    notes = tuple(cast(list[str], notes_value))

    identity = {
        "schema_version": _LINEAGE_SCHEMA_VERSION,
        "dataset_semantic_sha256": dataset_hash,
        "kind": kind,
        "operation": operation.as_dict(),
        "parents": list(parents),
        "source_uri": source_uri,
        "notes": list(notes),
    }
    computed_id = f"lineage-{sha256_hex(canonical_json_bytes(identity))[:40]}"
    supplied_id = payload.get("lineage_id")
    if supplied_id is not None:
        supplied = _lineage_id(supplied_id, "lineage_id")
        if supplied != computed_id:
            raise ValueError("lineage_id does not match the content-addressed manifest")
    if computed_id in parents:
        raise ValueError("lineage manifest cannot reference itself as a parent")

    return DatasetLineageManifest(
        lineage_id=computed_id,
        dataset_semantic_sha256=dataset_hash,
        kind=kind,
        operation=operation,
        parents=parents,
        source_uri=source_uri,
        notes=notes,
    )


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"lineage {name} must be a non-empty string")
    return value.strip()


def _sha256(value: Any, name: str) -> str:
    text = _required_string(value, name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"lineage {name} must be a lowercase SHA-256 hex digest")
    return text


def _lineage_id(value: Any, name: str) -> str:
    text = _required_string(value, name)
    suffix = text.removeprefix("lineage-")
    if not text.startswith("lineage-") or len(suffix) != 40 or any(
        character not in "0123456789abcdef" for character in suffix
    ):
        raise ValueError(f"lineage {name} must use the lineage-<40 hex> format")
    return text


def _validate_json_value(value: Any, name: str) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{name}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{name} keys must be strings")
            _validate_json_value(item, f"{name}.{key}")
        return
    raise ValueError(f"{name} contains a non-JSON value")
