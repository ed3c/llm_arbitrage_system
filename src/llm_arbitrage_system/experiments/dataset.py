from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from llm_arbitrage_system.domain.contracts import InstrumentKind, MarketEvent, Venue
from llm_arbitrage_system.experiments.canonical import (
    canonical_json_bytes,
    market_event_payload,
    sha256_hex,
)

_DATASET_SCHEMA_VERSION = 1
_REQUIRED_FIELDS = {
    "schema_version",
    "venue",
    "symbol",
    "instrument",
    "price",
    "timestamp",
}
_ALLOWED_FIELDS = _REQUIRED_FIELDS | {
    "bid",
    "ask",
    "high",
    "low",
    "volume_24h",
    "funding_rate_hourly",
    "sentiment_score",
    "reference_price",
    "reference_market_open",
    "metadata",
}
_DECIMAL_FIELDS = (
    "price",
    "bid",
    "ask",
    "high",
    "low",
    "volume_24h",
    "funding_rate_hourly",
    "reference_price",
)


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


class DatasetValidationError(ValueError):
    def __init__(self, path: Path, line_number: int, message: str) -> None:
        super().__init__(f"{path}:{line_number}: {message}")
        self.path = path
        self.line_number = line_number
        self.message = message


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    source_path: Path
    events: tuple[MarketEvent, ...]
    source_sha256: str
    semantic_sha256: str
    event_sha256: tuple[str, ...]
    canonical_jsonl: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def first_timestamp(self) -> datetime:
        return self.events[0].timestamp

    @property
    def last_timestamp(self) -> datetime:
        return self.events[-1].timestamp

    def slice_semantic_sha256(self, start: int, end: int) -> str:
        if not 0 <= start < end <= self.event_count:
            raise ValueError("dataset slice must satisfy 0 <= start < end <= event_count")
        lines = self.canonical_jsonl.splitlines(keepends=True)
        return sha256_hex(b"".join(lines[start:end]))

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "event_count": self.event_count,
            "source_sha256": self.source_sha256,
            "semantic_sha256": self.semantic_sha256,
            "first_timestamp": self.first_timestamp.isoformat(),
            "last_timestamp": self.last_timestamp.isoformat(),
            "symbols": sorted({event.symbol for event in self.events}),
        }


def load_jsonl_dataset(path: Path) -> DatasetSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    if source_bytes.startswith(b"\xef\xbb\xbf"):
        raise DatasetValidationError(resolved, 1, "UTF-8 BOM is not permitted")
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DatasetValidationError(resolved, error.start + 1, "dataset is not UTF-8") from error

    events: list[MarketEvent] = []
    canonical_lines: list[bytes] = []
    event_hashes: list[str] = []
    previous_timestamp: datetime | None = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            raise DatasetValidationError(resolved, line_number, "blank JSONL records are not permitted")
        event = _parse_line(resolved, line_number, raw_line)
        if previous_timestamp is not None and event.timestamp < previous_timestamp:
            raise DatasetValidationError(
                resolved,
                line_number,
                "timestamps must be globally non-decreasing",
            )
        previous_timestamp = event.timestamp
        canonical_line = canonical_json_bytes(market_event_payload(event)) + b"\n"
        events.append(event)
        canonical_lines.append(canonical_line)
        event_hashes.append(sha256_hex(canonical_line))

    if not events:
        raise DatasetValidationError(resolved, 1, "dataset must contain at least one event")

    canonical_jsonl = b"".join(canonical_lines)
    return DatasetSnapshot(
        source_path=resolved,
        events=tuple(events),
        source_sha256=sha256_hex(source_bytes),
        semantic_sha256=sha256_hex(canonical_jsonl),
        event_sha256=tuple(event_hashes),
        canonical_jsonl=canonical_jsonl,
        source_bytes=source_bytes,
    )


def _parse_line(path: Path, line_number: int, raw_line: str) -> MarketEvent:
    try:
        parsed = json.loads(raw_line, object_pairs_hook=_unique_json_object)
    except _DuplicateJsonKey as error:
        raise DatasetValidationError(
            path,
            line_number,
            f"duplicate JSON object key: {error.key}",
        ) from error
    except json.JSONDecodeError as error:
        raise DatasetValidationError(path, line_number, f"invalid JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise DatasetValidationError(path, line_number, "record must be a JSON object")
    record = cast(dict[str, Any], parsed)
    keys = set(record)
    missing = sorted(_REQUIRED_FIELDS - keys)
    unknown = sorted(keys - _ALLOWED_FIELDS)
    if missing:
        raise DatasetValidationError(path, line_number, f"missing fields: {', '.join(missing)}")
    if unknown:
        raise DatasetValidationError(path, line_number, f"unknown fields: {', '.join(unknown)}")
    if record["schema_version"] != _DATASET_SCHEMA_VERSION:
        raise DatasetValidationError(path, line_number, "schema_version must be 1")

    symbol = record["symbol"]
    timestamp_value = record["timestamp"]
    if not isinstance(symbol, str) or not symbol.strip():
        raise DatasetValidationError(path, line_number, "symbol must be a non-empty string")
    if not isinstance(timestamp_value, str):
        raise DatasetValidationError(path, line_number, "timestamp must be an ISO-8601 string")
    timestamp = _parse_timestamp(path, line_number, timestamp_value)

    decimal_values = {
        key: _optional_decimal(path, line_number, key, record.get(key))
        for key in _DECIMAL_FIELDS
    }
    sentiment = _optional_float(path, line_number, "sentiment_score", record.get("sentiment_score"))
    reference_open = record.get("reference_market_open")
    if reference_open is not None and not isinstance(reference_open, bool):
        raise DatasetValidationError(
            path,
            line_number,
            "reference_market_open must be a boolean or null",
        )
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        raise DatasetValidationError(path, line_number, "metadata must be a JSON object")
    _validate_metadata(path, line_number, cast(Mapping[str, Any], metadata))

    try:
        return MarketEvent(
            venue=Venue(_required_string(path, line_number, "venue", record["venue"])),
            symbol=symbol.strip(),
            instrument=InstrumentKind(
                _required_string(path, line_number, "instrument", record["instrument"])
            ),
            price=_required_decimal(path, line_number, "price", decimal_values["price"]),
            timestamp=timestamp,
            bid=decimal_values["bid"],
            ask=decimal_values["ask"],
            high=decimal_values["high"],
            low=decimal_values["low"],
            volume_24h=decimal_values["volume_24h"] or Decimal("0"),
            funding_rate_hourly=decimal_values["funding_rate_hourly"] or Decimal("0"),
            sentiment_score=sentiment,
            reference_price=decimal_values["reference_price"],
            reference_market_open=reference_open,
            metadata=cast(Mapping[str, Any], metadata),
        )
    except (ValueError, TypeError) as error:
        raise DatasetValidationError(path, line_number, str(error)) from error


def _required_string(path: Path, line_number: int, name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise DatasetValidationError(path, line_number, f"{name} must be a non-empty string")
    return value


def _parse_timestamp(path: Path, line_number: int, value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise DatasetValidationError(path, line_number, "timestamp is not valid ISO-8601") from error
    if timestamp.tzinfo is None:
        raise DatasetValidationError(path, line_number, "timestamp must include a timezone")
    return timestamp


def _optional_decimal(
    path: Path,
    line_number: int,
    name: str,
    value: Any,
) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise DatasetValidationError(
            path,
            line_number,
            f"{name} must be encoded as a JSON string or integer, not a float",
        )
    if not isinstance(value, (str, int)):
        raise DatasetValidationError(path, line_number, f"{name} must be a decimal string")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise DatasetValidationError(path, line_number, f"{name} is not a decimal") from error
    if not parsed.is_finite():
        raise DatasetValidationError(path, line_number, f"{name} must be finite")
    return parsed


def _required_decimal(
    path: Path,
    line_number: int,
    name: str,
    value: Decimal | None,
) -> Decimal:
    if value is None:
        raise DatasetValidationError(path, line_number, f"{name} is required")
    return value


def _optional_float(
    path: Path,
    line_number: int,
    name: str,
    value: Any,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DatasetValidationError(path, line_number, f"{name} must be a number or null")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise DatasetValidationError(path, line_number, f"{name} must be finite")
    return parsed


def _validate_metadata(path: Path, line_number: int, value: Mapping[str, Any]) -> None:
    for key, item in value.items():
        if not isinstance(key, str):
            raise DatasetValidationError(path, line_number, "metadata keys must be strings")
        _validate_json_value(path, line_number, f"metadata.{key}", item)


def _validate_json_value(path: Path, line_number: int, name: str, value: Any) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DatasetValidationError(path, line_number, f"{name} must be finite")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(path, line_number, f"{name}[{index}]", item)
        return
    if isinstance(value, dict):
        _validate_metadata(path, line_number, cast(Mapping[str, Any], value))
        return
    raise DatasetValidationError(path, line_number, f"{name} is not a JSON value")
