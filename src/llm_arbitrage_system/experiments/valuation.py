from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from llm_arbitrage_system.experiments.bundle import verify_bundle
from llm_arbitrage_system.experiments.bundle_io import file_sha256
from llm_arbitrage_system.experiments.bundle_validation import (
    json_object,
    nested_string,
)
from llm_arbitrage_system.experiments.canonical import (
    canonical_datetime,
    canonical_json_bytes,
    sha256_hex,
)
from llm_arbitrage_system.experiments.manifest import installed_package_version

_MARKS_SCHEMA_VERSION = 1
_VALUATION_SCHEMA_VERSION = 1
_VALUATION_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "position_key": "fill.symbol",
    "fill_sources": ["fills", "compensated_fills"],
    "fill_order": "strategy_created_at,plan_id,source,index",
    "fees": "deduct_from_settlement_cash",
    "terminal_marks": "exact_non_zero_open_position_symbols",
    "funding_accrual": "excluded",
    "borrow_and_margin_costs": "excluded",
    "corporate_actions": "excluded",
}


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
class TerminalMark:
    symbol: str
    price: Decimal

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("terminal mark symbol cannot be empty")
        if len(self.symbol) > 200:
            raise ValueError("terminal mark symbol is too long")
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("terminal mark price must be positive and finite")

    def as_dict(self) -> dict[str, str]:
        return {"symbol": self.symbol, "price": str(self.price)}


@dataclass(frozen=True, slots=True)
class TerminalMarksSnapshot:
    source_path: Path
    as_of: datetime
    marks: tuple[TerminalMark, ...]
    source_sha256: str
    semantic_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("terminal marks as_of must be timezone-aware")
        symbols = tuple(mark.symbol for mark in self.marks)
        if len(set(symbols)) != len(symbols):
            raise ValueError("terminal mark symbols must be unique")
        if symbols != tuple(sorted(symbols)):
            raise ValueError("terminal marks must use canonical symbol order")

    @property
    def by_symbol(self) -> dict[str, Decimal]:
        return {mark.symbol: mark.price for mark in self.marks}

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "semantic_sha256": self.semantic_sha256,
            "as_of": canonical_datetime(self.as_of),
            "mark_count": len(self.marks),
            "symbols": [mark.symbol for mark in self.marks],
        }


@dataclass(frozen=True, slots=True)
class ValuationPosition:
    symbol: str
    signed_quantity: Decimal
    mark_price: Decimal
    market_value_usd: Decimal

    def as_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "signed_quantity": str(self.signed_quantity),
            "mark_price": str(self.mark_price),
            "market_value_usd": str(self.market_value_usd),
        }


@dataclass(frozen=True, slots=True)
class BundleValuationReport:
    valuation_id: str
    experiment_id: str
    run_id: str
    bundle_root_sha256: str
    marks_source_sha256: str
    marks_semantic_sha256: str
    as_of: str
    last_dataset_event_at: str
    code_revision: str
    package_version: str
    execution_result_count: int
    fill_count: int
    gross_turnover_usd: Decimal
    fees_usd: Decimal
    settlement_cash_usd: Decimal
    open_position_market_value_usd: Decimal
    mark_to_market_pnl_usd: Decimal
    positions: tuple[ValuationPosition, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _VALUATION_SCHEMA_VERSION,
            "valuation_id": self.valuation_id,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "bundle_root_sha256": self.bundle_root_sha256,
            "marks": {
                "source_sha256": self.marks_source_sha256,
                "semantic_sha256": self.marks_semantic_sha256,
                "as_of": self.as_of,
            },
            "last_dataset_event_at": self.last_dataset_event_at,
            "code_revision": self.code_revision,
            "package_version": self.package_version,
            "policy": _VALUATION_POLICY,
            "metrics": {
                "execution_result_count": self.execution_result_count,
                "fill_count": self.fill_count,
                "gross_turnover_usd": str(self.gross_turnover_usd),
                "fees_usd": str(self.fees_usd),
                "settlement_cash_usd": str(self.settlement_cash_usd),
                "open_position_market_value_usd": str(
                    self.open_position_market_value_usd
                ),
                "mark_to_market_pnl_usd": str(self.mark_to_market_pnl_usd),
            },
            "positions": [position.as_dict() for position in self.positions],
            "assumptions": [
                (
                    "Terminal marks are caller-supplied evidence; their market-source "
                    "authenticity is not proven."
                ),
                "Settlement cash is kept separate from mark-to-market PnL.",
                (
                    "Funding accrual, borrow costs, margin interest, liquidation "
                    "mechanics, and corporate actions are excluded."
                ),
                (
                    "This terminal valuation does not provide an intraperiod equity "
                    "curve, drawdown, Sharpe ratio, or alpha decay."
                ),
            ],
        }


@dataclass(frozen=True, slots=True)
class _FillEvidence:
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee_usd: Decimal


@dataclass(frozen=True, slots=True)
class _ExecutionEvidence:
    result_count: int
    fills: tuple[_FillEvidence, ...]


def load_terminal_marks(path: Path) -> TerminalMarksSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: terminal marks are not valid UTF-8") from error
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=lambda value: _raise_non_finite(value),
        )
    except _DuplicateJsonKey as error:
        raise ValueError(f"duplicate terminal-marks JSON key: {error.key}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"{resolved}: invalid terminal-marks JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValueError("terminal marks document must be an object")
    payload = cast(dict[str, Any], parsed)
    if set(payload) != {"schema_version", "as_of", "marks"}:
        raise ValueError("terminal marks document contains unknown or missing fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _MARKS_SCHEMA_VERSION:
        raise ValueError("terminal marks schema_version must be 1")
    as_of = _timestamp(payload.get("as_of"), "terminal marks as_of")
    raw_marks = payload.get("marks")
    if not isinstance(raw_marks, list):
        raise ValueError("terminal marks marks must be a list")

    marks: list[TerminalMark] = []
    seen: set[str] = set()
    for index, raw_mark in enumerate(raw_marks):
        if not isinstance(raw_mark, dict):
            raise ValueError(f"terminal marks item {index} must be an object")
        item = cast(dict[str, Any], raw_mark)
        if set(item) != {"symbol", "price"}:
            raise ValueError(
                f"terminal marks item {index} contains unknown or missing fields"
            )
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ValueError(f"terminal marks item {index} symbol must be non-empty")
        if symbol in seen:
            raise ValueError(f"duplicate terminal mark symbol: {symbol}")
        seen.add(symbol)
        marks.append(
            TerminalMark(
                symbol=symbol,
                price=_decimal(item.get("price"), f"terminal mark {symbol} price"),
            )
        )
    canonical_marks = tuple(sorted(marks, key=lambda mark: mark.symbol))
    canonical_payload = {
        "schema_version": _MARKS_SCHEMA_VERSION,
        "as_of": canonical_datetime(as_of),
        "marks": [mark.as_dict() for mark in canonical_marks],
    }
    canonical_bytes = canonical_json_bytes(canonical_payload) + b"\n"
    return TerminalMarksSnapshot(
        source_path=resolved,
        as_of=as_of,
        marks=canonical_marks,
        source_sha256=sha256_hex(source_bytes),
        semantic_sha256=sha256_hex(canonical_bytes),
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def value_bundle(
    bundle_path: Path,
    marks_path: Path,
    *,
    code_revision: str,
    package_version: str | None = None,
) -> BundleValuationReport:
    bundle = bundle_path.resolve()
    verification = verify_bundle(bundle)
    marks = load_terminal_marks(marks_path)
    manifest = json_object((bundle / "manifest.json").read_text(encoding="utf-8"))
    last_event_at_text = nested_string(manifest, "dataset", "last_event_at")
    last_event_at = _timestamp(last_event_at_text, "manifest dataset last_event_at")
    if marks.as_of < last_event_at:
        raise ValueError("terminal marks as_of cannot precede the bundle dataset interval")

    revision = code_revision.strip()
    if not revision:
        raise ValueError("code_revision cannot be empty")
    if len(revision) > 160:
        raise ValueError("code_revision is too long")
    resolved_version = package_version or installed_package_version()
    execution = _load_execution_evidence(
        bundle / "evidence.sqlite3",
        verification.run_id,
    )

    quantities: dict[str, Decimal] = {}
    settlement_cash = Decimal("0")
    fees = Decimal("0")
    turnover = Decimal("0")
    for fill in execution.fills:
        notional = fill.quantity * fill.price
        signed_quantity = fill.quantity if fill.side == "buy" else -fill.quantity
        quantities[fill.symbol] = quantities.get(fill.symbol, Decimal("0")) + signed_quantity
        settlement_cash += -notional if fill.side == "buy" else notional
        settlement_cash -= fill.fee_usd
        fees += fill.fee_usd
        turnover += notional

    open_quantities = {
        symbol: quantity for symbol, quantity in quantities.items() if quantity != 0
    }
    marks_by_symbol = marks.by_symbol
    required_symbols = set(open_quantities)
    supplied_symbols = set(marks_by_symbol)
    missing = sorted(required_symbols - supplied_symbols)
    extra = sorted(supplied_symbols - required_symbols)
    if missing:
        raise ValueError("terminal marks are missing open positions: " + ", ".join(missing))
    if extra:
        raise ValueError("terminal marks contain non-open positions: " + ", ".join(extra))

    positions: list[ValuationPosition] = []
    market_value = Decimal("0")
    for symbol in sorted(open_quantities):
        quantity = open_quantities[symbol]
        mark_price = marks_by_symbol[symbol]
        value = quantity * mark_price
        market_value += value
        positions.append(
            ValuationPosition(
                symbol=symbol,
                signed_quantity=quantity,
                mark_price=mark_price,
                market_value_usd=value,
            )
        )

    bundle_root = _bundle_root(bundle, verification.experiment_id)
    identity = {
        "schema_version": _VALUATION_SCHEMA_VERSION,
        "experiment_id": verification.experiment_id,
        "run_id": verification.run_id,
        "bundle_root_sha256": bundle_root,
        "marks_semantic_sha256": marks.semantic_sha256,
        "policy": _VALUATION_POLICY,
        "code_revision": revision,
        "package_version": resolved_version,
    }
    valuation_id = f"valuation-{sha256_hex(canonical_json_bytes(identity))[:40]}"
    return BundleValuationReport(
        valuation_id=valuation_id,
        experiment_id=verification.experiment_id,
        run_id=verification.run_id,
        bundle_root_sha256=bundle_root,
        marks_source_sha256=marks.source_sha256,
        marks_semantic_sha256=marks.semantic_sha256,
        as_of=canonical_datetime(marks.as_of),
        last_dataset_event_at=canonical_datetime(last_event_at),
        code_revision=revision,
        package_version=resolved_version,
        execution_result_count=execution.result_count,
        fill_count=len(execution.fills),
        gross_turnover_usd=turnover,
        fees_usd=fees,
        settlement_cash_usd=settlement_cash,
        open_position_market_value_usd=market_value,
        mark_to_market_pnl_usd=settlement_cash + market_value,
        positions=tuple(positions),
    )


def _load_execution_evidence(path: Path, run_id: str) -> _ExecutionEvidence:
    uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT d.created_at, r.plan_id, r.payload_json
            FROM execution_results AS r
            LEFT JOIN strategy_decisions AS d
              ON d.run_id = r.run_id AND d.plan_id = r.plan_id
            WHERE r.run_id = ?
            ORDER BY d.created_at, r.plan_id
            """,
            (run_id,),
        ).fetchall()
    finally:
        connection.close()

    fills: list[_FillEvidence] = []
    for row in rows:
        if row["created_at"] is None:
            raise ValueError("execution result is missing its strategy decision evidence")
        payload = json_object(str(row["payload_json"]))
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("execution result payload is missing result evidence")
        result_payload = cast(dict[str, Any], result)
        for source in ("fills", "compensated_fills"):
            raw_fills = result_payload.get(source, [])
            if not isinstance(raw_fills, list):
                raise ValueError(f"execution result {source} must be a list")
            for index, raw_fill in enumerate(raw_fills):
                fills.append(_parse_fill(raw_fill, source, index))
    return _ExecutionEvidence(result_count=len(rows), fills=tuple(fills))


def _parse_fill(value: object, source: str, index: int) -> _FillEvidence:
    if not isinstance(value, dict):
        raise ValueError(f"execution {source} item {index} must be an object")
    fill = cast(dict[str, Any], value)
    symbol = fill.get("symbol")
    side = fill.get("side")
    status = fill.get("status")
    if not isinstance(symbol, str) or not symbol:
        raise ValueError(f"execution {source} item {index} has invalid symbol")
    if side not in {"buy", "sell"}:
        raise ValueError(f"execution {source} item {index} has invalid side")
    if status not in {"filled", "partially_filled"}:
        raise ValueError(f"execution {source} item {index} is not a valuatable fill")
    quantity = _decimal(fill.get("quantity"), f"execution {source} quantity")
    price = _decimal(fill.get("price"), f"execution {source} price")
    fee = _non_negative_decimal(
        fill.get("fee_usd", "0"),
        f"execution {source} fee",
    )
    return _FillEvidence(
        symbol=symbol,
        side=cast(str, side),
        quantity=quantity,
        price=price,
        fee_usd=fee,
    )


def _bundle_root(bundle: Path, experiment_id: str) -> str:
    manifest_sha = file_sha256(bundle / "manifest.json")
    checksums_sha = file_sha256(bundle / "checksums.sha256")
    return sha256_hex(
        canonical_json_bytes(
            {
                "schema_version": 1,
                "experiment_id": experiment_id,
                "manifest_sha256": manifest_sha,
                "checksums_sha256": checksums_sha,
            }
        )
    )


def _timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be an ISO-8601 string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{name} is not valid ISO-8601") from error
    if timestamp.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return timestamp


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{name} must be encoded as a string or integer, not a float")
    if not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{name} is not a decimal") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return parsed


def _non_negative_decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{name} must be encoded as a string or integer, not a float")
    if not isinstance(value, (str, int)):
        raise ValueError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"{name} is not a decimal") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{name} must be non-negative and finite")
    return parsed


def _raise_non_finite(value: str) -> None:
    raise ValueError(f"terminal marks contain a non-finite number: {value}")
