from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.experiments.canonical import (
    canonical_decimal,
    canonical_json_bytes,
    sha256_hex,
)
from llm_arbitrage_system.experiments.oos_statistics import (
    CandidateOOSStatistics,
    OOSStatisticsReport,
)
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_POLICY_SCHEMA_VERSION = 1
_REPORT_SCHEMA_VERSION = 1
_POLICY_MODE = "descriptive_only"
_NOT_VERIFIED = "NOT_VERIFIED"
_NOT_EVALUATED = "NOT_EVALUATED"
_NOT_APPLIED = "NOT_APPLIED"


@dataclass(frozen=True, slots=True)
class StabilityThresholds:
    minimum_window_count: int
    zero_pnl_tolerance_usd: Decimal
    minimum_positive_window_fraction: Decimal
    maximum_largest_absolute_pnl_share: Decimal
    minimum_return_observation_count: int
    maximum_drawdown_pct: Decimal | None
    maximum_alpha_decay_bps_per_window: Decimal | None
    candidate_family_warning_threshold: int

    def __post_init__(self) -> None:
        if not 1 <= self.minimum_window_count <= 4096:
            raise ValueError("minimum_window_count must be in [1, 4096]")
        if not 0 <= self.minimum_return_observation_count <= 4096:
            raise ValueError(
                "minimum_return_observation_count must be in [0, 4096]"
            )
        if not 1 <= self.candidate_family_warning_threshold <= 4096:
            raise ValueError(
                "candidate_family_warning_threshold must be in [1, 4096]"
            )
        _validate_decimal_range(
            self.zero_pnl_tolerance_usd,
            "zero_pnl_tolerance_usd",
            minimum=Decimal("0"),
        )
        _validate_decimal_range(
            self.minimum_positive_window_fraction,
            "minimum_positive_window_fraction",
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        _validate_decimal_range(
            self.maximum_largest_absolute_pnl_share,
            "maximum_largest_absolute_pnl_share",
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        _validate_optional_decimal_range(
            self.maximum_drawdown_pct,
            "maximum_drawdown_pct",
            minimum=Decimal("0"),
            maximum=Decimal("100"),
        )
        _validate_optional_decimal_range(
            self.maximum_alpha_decay_bps_per_window,
            "maximum_alpha_decay_bps_per_window",
            minimum=Decimal("0"),
        )


@dataclass(frozen=True, slots=True)
class StabilityPolicy:
    mode: str
    diagnostics: StabilityThresholds

    def __post_init__(self) -> None:
        if self.mode != _POLICY_MODE:
            raise ValueError("stability policy mode must be descriptive_only")


@dataclass(frozen=True, slots=True)
class StabilityPolicySnapshot:
    source_path: Path
    policy: StabilityPolicy
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "policy": stability_policy_payload(self.policy),
        }


@dataclass(frozen=True, slots=True)
class CandidateStabilityDiagnostics:
    candidate_id: str
    candidate_config_sha256: str
    diagnostic_state: str
    window_count: int
    positive_window_count: int
    negative_window_count: int
    zero_window_count: int
    positive_window_fraction: Decimal
    negative_window_fraction: Decimal
    zero_window_fraction: Decimal
    sign_pattern: str
    total_mark_to_market_pnl_usd: Decimal
    median_window_pnl_usd: Decimal
    pnl_population_stddev_usd: Decimal
    best_window_pnl_usd: Decimal
    worst_window_pnl_usd: Decimal
    largest_absolute_window_share: Decimal
    worst_loss_share_of_total_absolute_pnl: Decimal
    return_observation_count: int
    median_period_return: Decimal | None
    period_return_population_stddev: Decimal | None
    maximum_drawdown_pct: Decimal
    drawdown_threshold_status: str
    alpha_decay_bps_per_window: Decimal | None
    alpha_decay_threshold_status: str
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.diagnostic_state not in {
            "within_declared_bounds",
            "warnings_present",
        }:
            raise ValueError("invalid candidate diagnostic state")

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "diagnostic_state": self.diagnostic_state,
            "window_count": self.window_count,
            "positive_window_count": self.positive_window_count,
            "negative_window_count": self.negative_window_count,
            "zero_window_count": self.zero_window_count,
            "positive_window_fraction": canonical_decimal(
                self.positive_window_fraction
            ),
            "negative_window_fraction": canonical_decimal(
                self.negative_window_fraction
            ),
            "zero_window_fraction": canonical_decimal(self.zero_window_fraction),
            "sign_pattern": self.sign_pattern,
            "total_mark_to_market_pnl_usd": canonical_decimal(
                self.total_mark_to_market_pnl_usd
            ),
            "median_window_pnl_usd": canonical_decimal(
                self.median_window_pnl_usd
            ),
            "pnl_population_stddev_usd": canonical_decimal(
                self.pnl_population_stddev_usd
            ),
            "best_window_pnl_usd": canonical_decimal(self.best_window_pnl_usd),
            "worst_window_pnl_usd": canonical_decimal(self.worst_window_pnl_usd),
            "largest_absolute_window_share": canonical_decimal(
                self.largest_absolute_window_share
            ),
            "worst_loss_share_of_total_absolute_pnl": canonical_decimal(
                self.worst_loss_share_of_total_absolute_pnl
            ),
            "return_observation_count": self.return_observation_count,
            "median_period_return": _optional_decimal_text(
                self.median_period_return
            ),
            "period_return_population_stddev": _optional_decimal_text(
                self.period_return_population_stddev
            ),
            "maximum_drawdown_pct": canonical_decimal(self.maximum_drawdown_pct),
            "drawdown_threshold_status": self.drawdown_threshold_status,
            "alpha_decay_bps_per_window": _optional_decimal_text(
                self.alpha_decay_bps_per_window
            ),
            "alpha_decay_threshold_status": self.alpha_decay_threshold_status,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class StabilityDiagnosticsReport:
    report_id: str
    statistics_report_id: str
    matrix_sha256: str
    policy_sha256: str
    policy_mode: str
    candidates: tuple[CandidateStabilityDiagnostics, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _REPORT_SCHEMA_VERSION,
            "report_id": self.report_id,
            "statistics_report_id": self.statistics_report_id,
            "matrix_sha256": self.matrix_sha256,
            "policy_sha256": self.policy_sha256,
            "policy_mode": self.policy_mode,
            "candidate_count": len(self.candidates),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
            "verification": {
                "holdout_independence": _NOT_VERIFIED,
                "policy_preregistration_timing": _NOT_VERIFIED,
                "candidate_family_independence": _NOT_VERIFIED,
            },
            "statistical_significance": _NOT_EVALUATED,
            "multiple_testing_adjustment": _NOT_APPLIED,
            "selection": None,
            "promotion": None,
            "human_admit_required": True,
            "assumptions": [
                (
                    "Window diagnostics are descriptive summaries of captured Phase 6 "
                    "terminal OOS observations."
                ),
                (
                    "No p-value, confidence interval, false-discovery correction, "
                    "ranking, score aggregation, or winner inference is performed."
                ),
                (
                    "Warnings identify declared diagnostic boundaries only; they do "
                    "not establish causal alpha or future performance."
                ),
            ],
            "evidence_boundary": (
                "This report describes sign consistency, dispersion, concentration, "
                "return availability, drawdown, and alpha-decay availability for "
                "captured paper OOS windows. It does not prove holdout independence, "
                "policy timing, market-data truth, causal alpha, live realized profit, "
                "future returns, legal suitability, or production readiness."
            ),
        }


def load_stability_policy(path: Path) -> StabilityPolicySnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: stability policy is not UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid stability-policy YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("stability policy must be a mapping")
    policy = parse_stability_policy(cast(Mapping[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(stability_policy_payload(policy)) + b"\n"
    return StabilityPolicySnapshot(
        source_path=resolved,
        policy=policy,
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=sha256_hex(canonical_bytes),
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_stability_policy(payload: Mapping[str, Any]) -> StabilityPolicy:
    _require_exact_fields(
        "stability policy",
        payload,
        {"schema_version", "mode", "diagnostics"},
    )
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _POLICY_SCHEMA_VERSION:
        raise ValueError("stability policy schema_version must be 1")
    mode = _required_string(payload.get("mode"), "stability policy mode")
    diagnostics_payload = _required_mapping(payload, "diagnostics")
    _require_exact_fields(
        "stability policy diagnostics",
        diagnostics_payload,
        {
            "minimum_window_count",
            "zero_pnl_tolerance_usd",
            "minimum_positive_window_fraction",
            "maximum_largest_absolute_pnl_share",
            "minimum_return_observation_count",
            "maximum_drawdown_pct",
            "maximum_alpha_decay_bps_per_window",
            "candidate_family_warning_threshold",
        },
    )
    diagnostics = StabilityThresholds(
        minimum_window_count=_required_integer(
            diagnostics_payload.get("minimum_window_count"),
            "stability policy diagnostics minimum_window_count",
        ),
        zero_pnl_tolerance_usd=_required_decimal_string(
            diagnostics_payload.get("zero_pnl_tolerance_usd"),
            "stability policy diagnostics zero_pnl_tolerance_usd",
        ),
        minimum_positive_window_fraction=_required_decimal_string(
            diagnostics_payload.get("minimum_positive_window_fraction"),
            "stability policy diagnostics minimum_positive_window_fraction",
        ),
        maximum_largest_absolute_pnl_share=_required_decimal_string(
            diagnostics_payload.get("maximum_largest_absolute_pnl_share"),
            "stability policy diagnostics maximum_largest_absolute_pnl_share",
        ),
        minimum_return_observation_count=_required_integer(
            diagnostics_payload.get("minimum_return_observation_count"),
            "stability policy diagnostics minimum_return_observation_count",
        ),
        maximum_drawdown_pct=_optional_decimal_string(
            diagnostics_payload.get("maximum_drawdown_pct"),
            "stability policy diagnostics maximum_drawdown_pct",
        ),
        maximum_alpha_decay_bps_per_window=_optional_decimal_string(
            diagnostics_payload.get("maximum_alpha_decay_bps_per_window"),
            (
                "stability policy diagnostics "
                "maximum_alpha_decay_bps_per_window"
            ),
        ),
        candidate_family_warning_threshold=_required_integer(
            diagnostics_payload.get("candidate_family_warning_threshold"),
            "stability policy diagnostics candidate_family_warning_threshold",
        ),
    )
    return StabilityPolicy(mode=mode, diagnostics=diagnostics)


def stability_policy_payload(policy: StabilityPolicy) -> dict[str, Any]:
    thresholds = policy.diagnostics
    return {
        "schema_version": _POLICY_SCHEMA_VERSION,
        "mode": policy.mode,
        "diagnostics": {
            "minimum_window_count": thresholds.minimum_window_count,
            "zero_pnl_tolerance_usd": canonical_decimal(
                thresholds.zero_pnl_tolerance_usd
            ),
            "minimum_positive_window_fraction": canonical_decimal(
                thresholds.minimum_positive_window_fraction
            ),
            "maximum_largest_absolute_pnl_share": canonical_decimal(
                thresholds.maximum_largest_absolute_pnl_share
            ),
            "minimum_return_observation_count": (
                thresholds.minimum_return_observation_count
            ),
            "maximum_drawdown_pct": _optional_decimal_text(
                thresholds.maximum_drawdown_pct
            ),
            "maximum_alpha_decay_bps_per_window": _optional_decimal_text(
                thresholds.maximum_alpha_decay_bps_per_window
            ),
            "candidate_family_warning_threshold": (
                thresholds.candidate_family_warning_threshold
            ),
        },
    }


def build_stability_diagnostics_report(
    statistics: OOSStatisticsReport,
    policy: StabilityPolicySnapshot,
) -> StabilityDiagnosticsReport:
    _validate_statistics_report(statistics)
    candidates = tuple(sorted(statistics.candidates, key=lambda item: item.candidate_id))
    diagnostics = tuple(
        _diagnose_candidate(candidate, policy.policy.diagnostics)
        for candidate in candidates
    )
    warnings = _global_warnings(len(candidates), policy.policy.diagnostics)
    identity = {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "statistics_report_id": statistics.report_id,
        "matrix_sha256": statistics.matrix_sha256,
        "policy_sha256": policy.canonical_sha256,
        "policy_mode": policy.policy.mode,
        "candidates": [candidate.as_dict() for candidate in diagnostics],
        "warnings": list(warnings),
        "verification": {
            "holdout_independence": _NOT_VERIFIED,
            "policy_preregistration_timing": _NOT_VERIFIED,
            "candidate_family_independence": _NOT_VERIFIED,
        },
        "statistical_significance": _NOT_EVALUATED,
        "multiple_testing_adjustment": _NOT_APPLIED,
    }
    report_id = (
        "stability-report-"
        + sha256_hex(canonical_json_bytes(identity))[:40]
    )
    return StabilityDiagnosticsReport(
        report_id=report_id,
        statistics_report_id=statistics.report_id,
        matrix_sha256=statistics.matrix_sha256,
        policy_sha256=policy.canonical_sha256,
        policy_mode=policy.policy.mode,
        candidates=diagnostics,
        warnings=warnings,
    )


def _diagnose_candidate(
    candidate: CandidateOOSStatistics,
    policy: StabilityThresholds,
) -> CandidateStabilityDiagnostics:
    observations = candidate.observations
    pnl_values = tuple(item.mark_to_market_pnl_usd for item in observations)
    return_values = tuple(
        Decimal(str(item.period_return))
        for item in observations
        if item.period_return is not None
    )
    tolerance = policy.zero_pnl_tolerance_usd
    positive_count = sum(value > tolerance for value in pnl_values)
    negative_count = sum(value < -tolerance for value in pnl_values)
    zero_count = len(pnl_values) - positive_count - negative_count
    window_count = len(pnl_values)
    positive_fraction = Decimal(positive_count) / Decimal(window_count)
    negative_fraction = Decimal(negative_count) / Decimal(window_count)
    zero_fraction = Decimal(zero_count) / Decimal(window_count)
    absolute_total = sum((abs(value) for value in pnl_values), Decimal("0"))
    largest_absolute_share = (
        Decimal("0")
        if absolute_total == 0
        else max(abs(value) for value in pnl_values) / absolute_total
    )
    worst_window = min(pnl_values)
    worst_loss = abs(min(worst_window, Decimal("0")))
    worst_loss_share = (
        Decimal("0")
        if absolute_total == 0
        else worst_loss / absolute_total
    )
    drawdown = Decimal(str(candidate.maximum_drawdown_pct))
    drawdown_status = _maximum_threshold_status(
        drawdown,
        policy.maximum_drawdown_pct,
    )
    alpha_status = _optional_maximum_threshold_status(
        candidate.alpha_decay_bps_per_window,
        policy.maximum_alpha_decay_bps_per_window,
    )

    warnings: list[str] = []
    if window_count < policy.minimum_window_count:
        warnings.append(
            f"Window count {window_count} is below the declared minimum "
            f"{policy.minimum_window_count}."
        )
    if positive_fraction < policy.minimum_positive_window_fraction:
        warnings.append(
            f"Positive-window fraction {canonical_decimal(positive_fraction)} is "
            f"below the declared minimum "
            f"{canonical_decimal(policy.minimum_positive_window_fraction)}."
        )
    if largest_absolute_share > policy.maximum_largest_absolute_pnl_share:
        warnings.append(
            f"Largest absolute-window share "
            f"{canonical_decimal(largest_absolute_share)} exceeds the declared "
            f"maximum "
            f"{canonical_decimal(policy.maximum_largest_absolute_pnl_share)}."
        )
    if len(return_values) < policy.minimum_return_observation_count:
        warnings.append(
            f"Return observation count {len(return_values)} is below the declared "
            f"minimum {policy.minimum_return_observation_count}."
        )
    if drawdown_status == "exceeds_threshold":
        warnings.append(
            f"Maximum drawdown {canonical_decimal(drawdown)} exceeds the declared "
            f"maximum {canonical_decimal(cast(Decimal, policy.maximum_drawdown_pct))}."
        )
    if alpha_status == "unavailable":
        warnings.append("Alpha-decay metric is unavailable for this candidate.")
    elif alpha_status == "exceeds_threshold":
        warnings.append(
            f"Alpha decay "
            f"{canonical_decimal(cast(Decimal, candidate.alpha_decay_bps_per_window))} "
            f"exceeds the declared maximum "
            f"{canonical_decimal(cast(Decimal, policy.maximum_alpha_decay_bps_per_window))}."
        )

    return CandidateStabilityDiagnostics(
        candidate_id=candidate.candidate_id,
        candidate_config_sha256=candidate.candidate_config_sha256,
        diagnostic_state=(
            "warnings_present" if warnings else "within_declared_bounds"
        ),
        window_count=window_count,
        positive_window_count=positive_count,
        negative_window_count=negative_count,
        zero_window_count=zero_count,
        positive_window_fraction=positive_fraction,
        negative_window_fraction=negative_fraction,
        zero_window_fraction=zero_fraction,
        sign_pattern=_sign_pattern(
            positive_count,
            negative_count,
            zero_count,
            window_count,
        ),
        total_mark_to_market_pnl_usd=candidate.total_mark_to_market_pnl_usd,
        median_window_pnl_usd=_median_decimal(pnl_values),
        pnl_population_stddev_usd=_population_stddev(pnl_values),
        best_window_pnl_usd=max(pnl_values),
        worst_window_pnl_usd=worst_window,
        largest_absolute_window_share=largest_absolute_share,
        worst_loss_share_of_total_absolute_pnl=worst_loss_share,
        return_observation_count=len(return_values),
        median_period_return=(
            None if not return_values else _median_decimal(return_values)
        ),
        period_return_population_stddev=(
            None if not return_values else _population_stddev(return_values)
        ),
        maximum_drawdown_pct=drawdown,
        drawdown_threshold_status=drawdown_status,
        alpha_decay_bps_per_window=candidate.alpha_decay_bps_per_window,
        alpha_decay_threshold_status=alpha_status,
        warnings=tuple(warnings),
    )


def _global_warnings(
    candidate_count: int,
    policy: StabilityThresholds,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if candidate_count > policy.candidate_family_warning_threshold:
        warnings.append(
            f"Candidate family contains {candidate_count} configurations, exceeding "
            f"the declared warning threshold "
            f"{policy.candidate_family_warning_threshold}; no multiple-testing "
            "adjustment or significance claim is made."
        )
    warnings.extend(
        (
            "Holdout independence is NOT_VERIFIED by the Phase 6 OOS report.",
            "Policy pre-registration timing is NOT_VERIFIED by captured evidence.",
            "Candidate-family independence is NOT_VERIFIED.",
        )
    )
    return tuple(warnings)


def _sign_pattern(
    positive_count: int,
    negative_count: int,
    zero_count: int,
    total: int,
) -> str:
    if positive_count == total:
        return "all_positive"
    if negative_count == total:
        return "all_negative"
    if zero_count == total:
        return "all_zero"
    return "mixed"


def _median_decimal(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("median requires at least one value")
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _population_stddev(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("population standard deviation requires at least one value")
    if len(values) == 1:
        return Decimal("0")
    with localcontext() as context:
        context.prec = 50
        mean = sum(values, Decimal("0")) / Decimal(len(values))
        variance = sum(
            ((value - mean) * (value - mean) for value in values),
            Decimal("0"),
        ) / Decimal(len(values))
        return +variance.sqrt()


def _maximum_threshold_status(
    observed: Decimal,
    threshold: Decimal | None,
) -> str:
    if threshold is None:
        return "not_configured"
    return "within_threshold" if observed <= threshold else "exceeds_threshold"


def _optional_maximum_threshold_status(
    observed: Decimal | None,
    threshold: Decimal | None,
) -> str:
    if threshold is None:
        return "not_configured"
    if observed is None:
        return "unavailable"
    return "within_threshold" if observed <= threshold else "exceeds_threshold"


def _validate_statistics_report(report: OOSStatisticsReport) -> None:
    _validate_report_id(report.report_id)
    _validate_digest(report.matrix_sha256, "statistics matrix_sha256")
    if not report.candidates:
        raise ValueError("statistics report must contain at least one candidate")
    candidate_ids = [candidate.candidate_id for candidate in report.candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("statistics report contains duplicate candidate IDs")
    config_hashes = [
        candidate.candidate_config_sha256 for candidate in report.candidates
    ]
    if len(set(config_hashes)) != len(config_hashes):
        raise ValueError("statistics report contains duplicate candidate configurations")
    for config_hash in config_hashes:
        _validate_digest(config_hash, "candidate_config_sha256")
    for candidate in report.candidates:
        _validate_candidate(candidate)


def _validate_candidate(candidate: CandidateOOSStatistics) -> None:
    if not candidate.candidate_id or "\x00" in candidate.candidate_id:
        raise ValueError("candidate_id must be a non-empty NUL-free string")
    if not candidate.initial_equity_usd.is_finite() or candidate.initial_equity_usd <= 0:
        raise ValueError("candidate initial equity must be positive and finite")
    if not candidate.total_mark_to_market_pnl_usd.is_finite():
        raise ValueError("candidate total PnL must be finite")
    if (
        not math.isfinite(candidate.maximum_drawdown_pct)
        or candidate.maximum_drawdown_pct < 0
    ):
        raise ValueError("candidate maximum drawdown must be finite and non-negative")
    if (
        candidate.annualized_sharpe_ratio is not None
        and not math.isfinite(candidate.annualized_sharpe_ratio)
    ):
        raise ValueError("candidate Sharpe ratio must be finite")
    for metric_name, metric_value in (
        ("candidate OOS PnL slope", candidate.oos_pnl_slope_bps_per_window),
        ("candidate alpha decay", candidate.alpha_decay_bps_per_window),
    ):
        if metric_value is not None and not metric_value.is_finite():
            raise ValueError(f"{metric_name} must be finite")
    observations = candidate.observations
    if not observations:
        raise ValueError("candidate must contain at least one OOS observation")
    if candidate.expected_evaluation_count != len(observations):
        raise ValueError("candidate OOS evidence is not complete")
    window_indexes = tuple(item.window_index for item in observations)
    if window_indexes != tuple(sorted(window_indexes)):
        raise ValueError("candidate observations must be ordered by window index")
    if len(set(window_indexes)) != len(window_indexes):
        raise ValueError("candidate observations contain duplicate window indexes")
    evaluation_ids = [item.evaluation_id for item in observations]
    valuation_ids = [item.valuation_id for item in observations]
    if len(set(evaluation_ids)) != len(evaluation_ids):
        raise ValueError("candidate observations contain duplicate evaluation IDs")
    if len(set(valuation_ids)) != len(valuation_ids):
        raise ValueError("candidate observations contain duplicate valuation IDs")
    pnl_total = Decimal("0")
    for observation in observations:
        if observation.candidate_id != candidate.candidate_id:
            raise ValueError("observation candidate ID does not match candidate")
        if observation.candidate_config_sha256 != candidate.candidate_config_sha256:
            raise ValueError("observation configuration hash does not match candidate")
        if not observation.mark_to_market_pnl_usd.is_finite():
            raise ValueError("observation PnL must be finite")
        if observation.period_return is not None and not math.isfinite(
            observation.period_return
        ):
            raise ValueError("observation period return must be finite")
        pnl_total += observation.mark_to_market_pnl_usd
    if pnl_total != candidate.total_mark_to_market_pnl_usd:
        raise ValueError("candidate total PnL does not match observations")
    expected_ending_equity = candidate.initial_equity_usd + pnl_total
    if candidate.ending_equity_usd != expected_ending_equity:
        raise ValueError("candidate ending equity does not match observations")


def _required_mapping(
    payload: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"stability policy {key} must be a mapping")
    return cast(Mapping[str, Any], value)


def _require_exact_fields(
    name: str,
    payload: Mapping[str, Any],
    expected: set[str],
) -> None:
    missing = sorted(expected - set(payload))
    unknown = sorted(set(payload) - expected)
    if missing:
        raise ValueError(f"{name} is missing fields: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value


def _required_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _required_decimal_string(value: object, name: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a decimal string")
    return _parse_finite_decimal(value, name)


def _optional_decimal_string(value: object, name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a decimal string or null")
    return _parse_finite_decimal(value, name)


def _parse_finite_decimal(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a decimal string") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


def _validate_decimal_range(
    value: Decimal,
    name: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> None:
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {canonical_decimal(minimum)}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {canonical_decimal(maximum)}")


def _validate_optional_decimal_range(
    value: Decimal | None,
    name: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> None:
    if value is None:
        return
    _validate_decimal_range(
        value,
        name,
        minimum=minimum,
        maximum=maximum,
    )


def _validate_report_id(value: str) -> None:
    suffix = value.removeprefix("oos-report-")
    if (
        not value.startswith("oos-report-")
        or len(suffix) != 40
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError("statistics report_id must use oos-report-<40 lowercase hex>")


def _validate_digest(value: str, name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be 64 lowercase hex characters")
