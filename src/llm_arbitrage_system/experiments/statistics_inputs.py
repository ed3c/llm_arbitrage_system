from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.oos_statistics import EvaluationValuationInput

_SCHEMA_VERSION = 1


class _DuplicateJsonKey(ValueError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class StatisticsInputSnapshot:
    source_path: Path
    candidate_ids: tuple[str, ...]
    valuation_inputs: tuple[EvaluationValuationInput, ...]
    source_sha256: str
    canonical_sha256: str

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "candidate_ids": list(self.candidate_ids),
            "evaluation_ids": [
                item.evaluation_id for item in self.valuation_inputs
            ],
        }


def load_statistics_inputs(path: Path) -> StatisticsInputSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: statistics inputs are not valid UTF-8") from error
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=lambda value: _raise_non_finite(value),
        )
    except _DuplicateJsonKey as error:
        raise ValueError(f"duplicate statistics-input JSON key: {error.key}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"{resolved}: invalid statistics-input JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValueError("statistics inputs must be a JSON object")
    payload = cast(dict[str, Any], parsed)
    if set(payload) != {"schema_version", "candidate_ids", "valuations"}:
        raise ValueError("statistics inputs contain unknown or missing fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _SCHEMA_VERSION:
        raise ValueError("statistics inputs schema_version must be 1")

    candidate_ids = tuple(sorted(_string_list(payload.get("candidate_ids"), "candidate_ids")))
    if not candidate_ids:
        raise ValueError("statistics inputs candidate_ids cannot be empty")
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("statistics inputs candidate_ids cannot contain duplicates")

    raw_valuations = payload.get("valuations")
    if not isinstance(raw_valuations, list) or not raw_valuations:
        raise ValueError("statistics inputs valuations must be a non-empty list")
    valuation_inputs: list[EvaluationValuationInput] = []
    seen: set[str] = set()
    canonical_valuations: list[dict[str, str]] = []
    for index, raw_value in enumerate(raw_valuations):
        if not isinstance(raw_value, dict):
            raise ValueError(f"statistics inputs valuation {index} must be an object")
        item = cast(dict[str, Any], raw_value)
        if set(item) != {"evaluation_id", "bundle", "marks"}:
            raise ValueError(
                f"statistics inputs valuation {index} contains unknown or missing fields"
            )
        evaluation_id = _required_string(
            item.get("evaluation_id"),
            f"valuation {index} evaluation_id",
        )
        if evaluation_id in seen:
            raise ValueError(
                f"duplicate statistics-input evaluation_id: {evaluation_id}"
            )
        seen.add(evaluation_id)
        bundle_text = _required_string(item.get("bundle"), f"valuation {index} bundle")
        marks_text = _required_string(item.get("marks"), f"valuation {index} marks")
        bundle = _resolve_input_path(resolved.parent, bundle_text)
        marks = _resolve_input_path(resolved.parent, marks_text)
        if not bundle.is_dir():
            raise ValueError(f"statistics input bundle is not a directory: {bundle}")
        if not marks.is_file():
            raise ValueError(f"statistics input marks are not a file: {marks}")
        valuation_inputs.append(
            EvaluationValuationInput(
                evaluation_id=evaluation_id,
                bundle_path=bundle,
                marks_path=marks,
            )
        )
        canonical_valuations.append(
            {
                "evaluation_id": evaluation_id,
                "bundle": str(bundle),
                "marks": str(marks),
            }
        )
    valuation_inputs.sort(key=lambda item: item.evaluation_id)
    canonical_valuations.sort(key=lambda item: item["evaluation_id"])
    canonical_payload = {
        "schema_version": _SCHEMA_VERSION,
        "candidate_ids": list(candidate_ids),
        "valuations": canonical_valuations,
    }
    return StatisticsInputSnapshot(
        source_path=resolved,
        candidate_ids=candidate_ids,
        valuation_inputs=tuple(valuation_inputs),
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=sha256_hex(canonical_json_bytes(canonical_payload)),
    )


def _resolve_input_path(root: Path, value: str) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def _string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"statistics inputs {name} must be a list")
    return [
        _required_string(item, f"statistics inputs {name} item")
        for item in value
    ]


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value


def _raise_non_finite(value: str) -> None:
    raise ValueError(f"statistics inputs contain a non-finite number: {value}")
