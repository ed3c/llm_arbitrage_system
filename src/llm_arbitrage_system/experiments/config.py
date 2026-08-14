from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.config.runtime import AnalyticsParameters
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load
from llm_arbitrage_system.simulation.approval import PaperApprovalLimits
from llm_arbitrage_system.simulation.strategy_router import ResearchThresholds

_CONFIG_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ExecutionSimulationParameters:
    slippage_bps: Decimal = Decimal("5")
    fee_bps: Decimal = Decimal("1")
    fail_leg_indexes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if self.slippage_bps < 0 or self.fee_bps < 0:
            raise ValueError("execution costs cannot be negative")
        if any(index < 0 for index in self.fail_leg_indexes):
            raise ValueError("fail_leg_indexes cannot contain negative values")
        if len(set(self.fail_leg_indexes)) != len(self.fail_leg_indexes):
            raise ValueError("fail_leg_indexes cannot contain duplicates")


@dataclass(frozen=True, slots=True)
class ExperimentRuntimeParameters:
    queue_size: int = 128

    def __post_init__(self) -> None:
        if self.queue_size < 1:
            raise ValueError("queue_size must be positive")


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    analytics: AnalyticsParameters = field(default_factory=AnalyticsParameters)
    strategy: ResearchThresholds = field(default_factory=ResearchThresholds)
    approval: PaperApprovalLimits = field(default_factory=PaperApprovalLimits)
    execution: ExecutionSimulationParameters = field(
        default_factory=ExecutionSimulationParameters
    )
    runtime: ExperimentRuntimeParameters = field(
        default_factory=ExperimentRuntimeParameters
    )


@dataclass(frozen=True, slots=True)
class ExperimentConfigSnapshot:
    source_path: Path
    config: ExperimentConfig
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "config": experiment_config_payload(self.config),
        }


def load_experiment_config(path: Path) -> ExperimentConfigSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: configuration is not valid UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid YAML configuration: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{resolved}: configuration must be a mapping")
    config = parse_experiment_config(cast(Mapping[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(experiment_config_payload(config)) + b"\n"
    return ExperimentConfigSnapshot(
        source_path=resolved,
        config=config,
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=sha256_hex(canonical_bytes),
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_experiment_config(payload: Mapping[str, Any]) -> ExperimentConfig:
    _reject_unknown(
        "configuration",
        payload,
        {"schema_version", "analytics", "strategy", "approval", "execution", "runtime"},
    )
    if payload.get("schema_version") != _CONFIG_SCHEMA_VERSION:
        raise ValueError("configuration.schema_version must be 1")

    analytics_payload = _section(payload, "analytics")
    strategy_payload = _section(payload, "strategy")
    approval_payload = _section(payload, "approval")
    execution_payload = _section(payload, "execution")
    runtime_payload = _section(payload, "runtime")

    analytics_defaults = AnalyticsParameters()
    _reject_unknown(
        "analytics",
        analytics_payload,
        {
            "efficiency_period",
            "kama_fast_period",
            "kama_slow_period",
            "zscore_window",
            "kalman_process_variance",
            "kalman_measurement_variance",
        },
    )
    analytics = AnalyticsParameters(
        efficiency_period=_integer(
            analytics_payload,
            "efficiency_period",
            analytics_defaults.efficiency_period,
        ),
        kama_fast_period=_integer(
            analytics_payload,
            "kama_fast_period",
            analytics_defaults.kama_fast_period,
        ),
        kama_slow_period=_integer(
            analytics_payload,
            "kama_slow_period",
            analytics_defaults.kama_slow_period,
        ),
        zscore_window=_integer(
            analytics_payload,
            "zscore_window",
            analytics_defaults.zscore_window,
        ),
        kalman_process_variance=_floating(
            analytics_payload,
            "kalman_process_variance",
            analytics_defaults.kalman_process_variance,
        ),
        kalman_measurement_variance=_floating(
            analytics_payload,
            "kalman_measurement_variance",
            analytics_defaults.kalman_measurement_variance,
        ),
    )

    strategy_defaults = ResearchThresholds()
    _reject_unknown(
        "strategy",
        strategy_payload,
        {
            "scenario_notional_usd",
            "estimated_round_trip_cost_bps",
            "funding_entry_apy_pct",
            "funding_holding_hours",
            "crowd_entry_zscore",
            "crowd_efficiency_ratio_maximum",
            "crowd_requires_sentiment",
            "lead_lag_entry_premium_bps",
        },
    )
    strategy = ResearchThresholds(
        scenario_notional_usd=_decimal(
            strategy_payload,
            "scenario_notional_usd",
            strategy_defaults.scenario_notional_usd,
        ),
        estimated_round_trip_cost_bps=_decimal(
            strategy_payload,
            "estimated_round_trip_cost_bps",
            strategy_defaults.estimated_round_trip_cost_bps,
        ),
        funding_entry_apy_pct=_decimal(
            strategy_payload,
            "funding_entry_apy_pct",
            strategy_defaults.funding_entry_apy_pct,
        ),
        funding_holding_hours=_decimal(
            strategy_payload,
            "funding_holding_hours",
            strategy_defaults.funding_holding_hours,
        ),
        crowd_entry_zscore=_floating(
            strategy_payload,
            "crowd_entry_zscore",
            strategy_defaults.crowd_entry_zscore,
        ),
        crowd_efficiency_ratio_maximum=_floating(
            strategy_payload,
            "crowd_efficiency_ratio_maximum",
            strategy_defaults.crowd_efficiency_ratio_maximum,
        ),
        crowd_requires_sentiment=_boolean(
            strategy_payload,
            "crowd_requires_sentiment",
            strategy_defaults.crowd_requires_sentiment,
        ),
        lead_lag_entry_premium_bps=_decimal(
            strategy_payload,
            "lead_lag_entry_premium_bps",
            strategy_defaults.lead_lag_entry_premium_bps,
        ),
    )

    approval_defaults = PaperApprovalLimits()
    _reject_unknown(
        "approval",
        approval_payload,
        {
            "maximum_event_age_seconds",
            "minimum_edge_bps",
            "maximum_leg_notional_usd",
            "maximum_gross_exposure_usd",
            "maximum_leg_imbalance_pct",
            "maximum_slippage_bps",
        },
    )
    approval = PaperApprovalLimits(
        maximum_event_age_seconds=_floating(
            approval_payload,
            "maximum_event_age_seconds",
            approval_defaults.maximum_event_age_seconds,
        ),
        minimum_edge_bps=_decimal(
            approval_payload,
            "minimum_edge_bps",
            approval_defaults.minimum_edge_bps,
        ),
        maximum_leg_notional_usd=_decimal(
            approval_payload,
            "maximum_leg_notional_usd",
            approval_defaults.maximum_leg_notional_usd,
        ),
        maximum_gross_exposure_usd=_decimal(
            approval_payload,
            "maximum_gross_exposure_usd",
            approval_defaults.maximum_gross_exposure_usd,
        ),
        maximum_leg_imbalance_pct=_decimal(
            approval_payload,
            "maximum_leg_imbalance_pct",
            approval_defaults.maximum_leg_imbalance_pct,
        ),
        maximum_slippage_bps=_decimal(
            approval_payload,
            "maximum_slippage_bps",
            approval_defaults.maximum_slippage_bps,
        ),
    )

    execution_defaults = ExecutionSimulationParameters()
    _reject_unknown(
        "execution",
        execution_payload,
        {"slippage_bps", "fee_bps", "fail_leg_indexes"},
    )
    execution = ExecutionSimulationParameters(
        slippage_bps=_decimal(
            execution_payload,
            "slippage_bps",
            execution_defaults.slippage_bps,
        ),
        fee_bps=_decimal(
            execution_payload,
            "fee_bps",
            execution_defaults.fee_bps,
        ),
        fail_leg_indexes=_integer_tuple(
            execution_payload.get("fail_leg_indexes", execution_defaults.fail_leg_indexes),
            "execution.fail_leg_indexes",
        ),
    )

    runtime_defaults = ExperimentRuntimeParameters()
    _reject_unknown("runtime", runtime_payload, {"queue_size"})
    runtime = ExperimentRuntimeParameters(
        queue_size=_integer(runtime_payload, "queue_size", runtime_defaults.queue_size)
    )
    return ExperimentConfig(
        analytics=analytics,
        strategy=strategy,
        approval=approval,
        execution=execution,
        runtime=runtime,
    )


def experiment_config_payload(config: ExperimentConfig) -> dict[str, Any]:
    return {
        "schema_version": _CONFIG_SCHEMA_VERSION,
        "analytics": {
            "efficiency_period": config.analytics.efficiency_period,
            "kama_fast_period": config.analytics.kama_fast_period,
            "kama_slow_period": config.analytics.kama_slow_period,
            "zscore_window": config.analytics.zscore_window,
            "kalman_process_variance": config.analytics.kalman_process_variance,
            "kalman_measurement_variance": config.analytics.kalman_measurement_variance,
        },
        "strategy": {
            "scenario_notional_usd": str(config.strategy.scenario_notional_usd),
            "estimated_round_trip_cost_bps": str(
                config.strategy.estimated_round_trip_cost_bps
            ),
            "funding_entry_apy_pct": str(config.strategy.funding_entry_apy_pct),
            "funding_holding_hours": str(config.strategy.funding_holding_hours),
            "crowd_entry_zscore": config.strategy.crowd_entry_zscore,
            "crowd_efficiency_ratio_maximum": (
                config.strategy.crowd_efficiency_ratio_maximum
            ),
            "crowd_requires_sentiment": config.strategy.crowd_requires_sentiment,
            "lead_lag_entry_premium_bps": str(
                config.strategy.lead_lag_entry_premium_bps
            ),
        },
        "approval": {
            "maximum_event_age_seconds": config.approval.maximum_event_age_seconds,
            "minimum_edge_bps": str(config.approval.minimum_edge_bps),
            "maximum_leg_notional_usd": str(
                config.approval.maximum_leg_notional_usd
            ),
            "maximum_gross_exposure_usd": str(
                config.approval.maximum_gross_exposure_usd
            ),
            "maximum_leg_imbalance_pct": str(
                config.approval.maximum_leg_imbalance_pct
            ),
            "maximum_slippage_bps": str(config.approval.maximum_slippage_bps),
        },
        "execution": {
            "slippage_bps": str(config.execution.slippage_bps),
            "fee_bps": str(config.execution.fee_bps),
            "fail_leg_indexes": list(config.execution.fail_leg_indexes),
        },
        "runtime": {"queue_size": config.runtime.queue_size},
    }


def apply_config_overrides(
    config: ExperimentConfig,
    overrides: Mapping[str, Any],
) -> ExperimentConfig:
    payload = experiment_config_payload(config)
    for dotted_path, value in sorted(overrides.items()):
        parts = dotted_path.split(".")
        if len(parts) != 2:
            raise ValueError(f"override path must be section.field: {dotted_path}")
        section_name, field_name = parts
        section = payload.get(section_name)
        if not isinstance(section, dict) or field_name not in section:
            raise ValueError(f"unknown override path: {dotted_path}")
        section[field_name] = value
    return parse_experiment_config(cast(Mapping[str, Any], payload))


def config_canonical_bytes(config: ExperimentConfig) -> bytes:
    return canonical_json_bytes(experiment_config_payload(config)) + b"\n"


def config_sha256(config: ExperimentConfig) -> str:
    return sha256_hex(config_canonical_bytes(config))


def _section(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"configuration.{key} must be a mapping")
    return cast(Mapping[str, Any], value)


def _reject_unknown(name: str, payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _integer(payload: Mapping[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return cast(int, value)


def _floating(payload: Mapping[str, Any], key: str, default: float) -> float:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{key} must be a number")
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(f"{key} must be a number") from error
    if not isfinite(parsed):
        raise ValueError(f"{key} must be finite")
    return parsed


def _boolean(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _decimal(payload: Mapping[str, Any], key: str, default: Decimal) -> Decimal:
    value = payload.get(key, default)
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{key} must be encoded as a string or integer, not a float")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{key} must be a decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{key} must be finite")
    return parsed


def _integer_tuple(value: Any, name: str) -> tuple[int, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of integers")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"{name} must contain integers")
        result.append(item)
    return tuple(sorted(result))
