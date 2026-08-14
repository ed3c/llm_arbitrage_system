from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, TypeAlias, cast

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
_POLICY_MODE = "human_review_only"
_MULTIPLE_TESTING_MODES = {"warn_only", "require_single_candidate"}
_VALUE: TypeAlias = str | int | bool | None


@dataclass(frozen=True, slots=True)
class CandidateAdmissionPolicy:
    require_complete_coverage: bool
    minimum_evaluation_count: int
    maximum_drawdown_pct: Decimal | None
    minimum_annualized_sharpe_ratio: Decimal | None
    maximum_alpha_decay_bps_per_window: Decimal | None
    minimum_oos_pnl_slope_bps_per_window: Decimal | None
    minimum_total_mark_to_market_pnl_usd: Decimal | None
    minimum_positive_window_fraction: Decimal | None

    def __post_init__(self) -> None:
        if not 1 <= self.minimum_evaluation_count <= 4096:
            raise ValueError("minimum_evaluation_count must be in [1, 4096]")
        _validate_optional_range(
            self.maximum_drawdown_pct,
            "maximum_drawdown_pct",
            minimum=Decimal("0"),
            maximum=Decimal("100"),
        )
        _validate_optional_range(
            self.maximum_alpha_decay_bps_per_window,
            "maximum_alpha_decay_bps_per_window",
            minimum=Decimal("0"),
        )
        _validate_optional_range(
            self.minimum_positive_window_fraction,
            "minimum_positive_window_fraction",
            minimum=Decimal("0"),
            maximum=Decimal("1"),
        )
        for name, value in (
            (
                "minimum_annualized_sharpe_ratio",
                self.minimum_annualized_sharpe_ratio,
            ),
            (
                "minimum_oos_pnl_slope_bps_per_window",
                self.minimum_oos_pnl_slope_bps_per_window,
            ),
            (
                "minimum_total_mark_to_market_pnl_usd",
                self.minimum_total_mark_to_market_pnl_usd,
            ),
        ):
            if value is not None and not value.is_finite():
                raise ValueError(f"{name} must be finite")


@dataclass(frozen=True, slots=True)
class MultipleTestingPolicy:
    mode: str
    maximum_candidates_without_warning: int

    def __post_init__(self) -> None:
        if self.mode not in _MULTIPLE_TESTING_MODES:
            allowed = ", ".join(sorted(_MULTIPLE_TESTING_MODES))
            raise ValueError(f"multiple_testing.mode must be one of: {allowed}")
        if not 1 <= self.maximum_candidates_without_warning <= 4096:
            raise ValueError(
                "maximum_candidates_without_warning must be in [1, 4096]"
            )


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    mode: str
    admission: CandidateAdmissionPolicy
    multiple_testing: MultipleTestingPolicy

    def __post_init__(self) -> None:
        if self.mode != _POLICY_MODE:
            raise ValueError("selection policy mode must be human_review_only")


@dataclass(frozen=True, slots=True)
class SelectionPolicySnapshot:
    source_path: Path
    policy: SelectionPolicy
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "policy": selection_policy_payload(self.policy),
        }


@dataclass(frozen=True, slots=True)
class AdmissionCriterionResult:
    name: str
    status: str
    observed: _VALUE
    threshold: _VALUE
    reason: str

    def __post_init__(self) -> None:
        if self.status not in {"pass", "fail", "not_applicable"}:
            raise ValueError("criterion status must be pass, fail, or not_applicable")

    @property
    def blocks_admission(self) -> bool:
        return self.status == "fail"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "observed": self.observed,
            "threshold": self.threshold,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CandidateAdmissionResult:
    candidate_id: str
    candidate_config_sha256: str
    status: str
    criteria: tuple[AdmissionCriterionResult, ...]

    def __post_init__(self) -> None:
        if self.status not in {"admissible_for_human_review", "blocked"}:
            raise ValueError("candidate admission status is invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "status": self.status,
            "criteria": [criterion.as_dict() for criterion in self.criteria],
        }


@dataclass(frozen=True, slots=True)
class SelectionGovernanceReport:
    report_id: str
    statistics_report_id: str
    matrix_sha256: str
    policy_sha256: str
    policy_mode: str
    multiple_testing_mode: str
    candidates: tuple[CandidateAdmissionResult, ...]
    warnings: tuple[str, ...]

    @property
    def admissible_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            candidate.candidate_id
            for candidate in self.candidates
            if candidate.status == "admissible_for_human_review"
        )

    @property
    def blocked_candidate_ids(self) -> tuple[str, ...]:
        return tuple(
            candidate.candidate_id
            for candidate in self.candidates
            if candidate.status == "blocked"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _REPORT_SCHEMA_VERSION,
            "report_id": self.report_id,
            "statistics_report_id": self.statistics_report_id,
            "matrix_sha256": self.matrix_sha256,
            "policy_sha256": self.policy_sha256,
            "policy_mode": self.policy_mode,
            "multiple_testing_mode": self.multiple_testing_mode,
            "candidate_count": len(self.candidates),
            "admissible_candidate_ids": list(self.admissible_candidate_ids),
            "blocked_candidate_ids": list(self.blocked_candidate_ids),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
            "selection": None,
            "promotion": None,
            "human_admit_required": True,
            "assumptions": [
                (
                    "Admission is evaluated criterion-by-criterion without score "
                    "aggregation, ranking, or winner inference."
                ),
                (
                    "Phase 6 OOS evidence is treated as captured paper evidence; "
                    "holdout independence and policy registration timing are not proven."
                ),
                (
                    "Admissible means eligible for Human Admit review, not approved "
                    "for deployment, capital allocation, or live trading."
                ),
            ],
            "evidence_boundary": (
                "This report proves only that captured Phase 6 candidate evidence "
                "satisfies one content-addressed policy. It does not establish "
                "source-market truth, causal alpha, live realized profit, future "
                "returns, legal suitability, or production readiness."
            ),
        }


def load_selection_policy(path: Path) -> SelectionPolicySnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: selection policy is not UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid selection-policy YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("selection policy must be a mapping")
    policy = parse_selection_policy(cast(Mapping[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(selection_policy_payload(policy)) + b"\n"
    return SelectionPolicySnapshot(
        source_path=resolved,
        policy=policy,
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=sha256_hex(canonical_bytes),
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_selection_policy(payload: Mapping[str, Any]) -> SelectionPolicy:
    _require_exact_fields(
        "selection policy",
        payload,
        {"schema_version", "mode", "admission", "multiple_testing"},
    )
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _POLICY_SCHEMA_VERSION:
        raise ValueError("selection policy schema_version must be 1")
    mode = _required_string(payload.get("mode"), "selection policy mode")

    admission_payload = _required_mapping(payload, "admission")
    _require_exact_fields(
        "selection policy admission",
        admission_payload,
        {
            "require_complete_coverage",
            "minimum_evaluation_count",
            "maximum_drawdown_pct",
            "minimum_annualized_sharpe_ratio",
            "maximum_alpha_decay_bps_per_window",
            "minimum_oos_pnl_slope_bps_per_window",
            "minimum_total_mark_to_market_pnl_usd",
            "minimum_positive_window_fraction",
        },
    )
    admission = CandidateAdmissionPolicy(
        require_complete_coverage=_required_boolean(
            admission_payload.get("require_complete_coverage"),
            "selection policy admission require_complete_coverage",
        ),
        minimum_evaluation_count=_required_integer(
            admission_payload.get("minimum_evaluation_count"),
            "selection policy admission minimum_evaluation_count",
        ),
        maximum_drawdown_pct=_optional_decimal_string(
            admission_payload.get("maximum_drawdown_pct"),
            "selection policy admission maximum_drawdown_pct",
        ),
        minimum_annualized_sharpe_ratio=_optional_decimal_string(
            admission_payload.get("minimum_annualized_sharpe_ratio"),
            "selection policy admission minimum_annualized_sharpe_ratio",
        ),
        maximum_alpha_decay_bps_per_window=_optional_decimal_string(
            admission_payload.get("maximum_alpha_decay_bps_per_window"),
            "selection policy admission maximum_alpha_decay_bps_per_window",
        ),
        minimum_oos_pnl_slope_bps_per_window=_optional_decimal_string(
            admission_payload.get("minimum_oos_pnl_slope_bps_per_window"),
            "selection policy admission minimum_oos_pnl_slope_bps_per_window",
        ),
        minimum_total_mark_to_market_pnl_usd=_optional_decimal_string(
            admission_payload.get("minimum_total_mark_to_market_pnl_usd"),
            "selection policy admission minimum_total_mark_to_market_pnl_usd",
        ),
        minimum_positive_window_fraction=_optional_decimal_string(
            admission_payload.get("minimum_positive_window_fraction"),
            "selection policy admission minimum_positive_window_fraction",
        ),
    )

    multiple_testing_payload = _required_mapping(payload, "multiple_testing")
    _require_exact_fields(
        "selection policy multiple_testing",
        multiple_testing_payload,
        {"mode", "maximum_candidates_without_warning"},
    )
    multiple_testing = MultipleTestingPolicy(
        mode=_required_string(
            multiple_testing_payload.get("mode"),
            "selection policy multiple_testing mode",
        ),
        maximum_candidates_without_warning=_required_integer(
            multiple_testing_payload.get("maximum_candidates_without_warning"),
            (
                "selection policy multiple_testing "
                "maximum_candidates_without_warning"
            ),
        ),
    )
    return SelectionPolicy(
        mode=mode,
        admission=admission,
        multiple_testing=multiple_testing,
    )


def selection_policy_payload(policy: SelectionPolicy) -> dict[str, Any]:
    admission = policy.admission
    return {
        "schema_version": _POLICY_SCHEMA_VERSION,
        "mode": policy.mode,
        "admission": {
            "require_complete_coverage": admission.require_complete_coverage,
            "minimum_evaluation_count": admission.minimum_evaluation_count,
            "maximum_drawdown_pct": _optional_decimal_text(
                admission.maximum_drawdown_pct
            ),
            "minimum_annualized_sharpe_ratio": _optional_decimal_text(
                admission.minimum_annualized_sharpe_ratio
            ),
            "maximum_alpha_decay_bps_per_window": _optional_decimal_text(
                admission.maximum_alpha_decay_bps_per_window
            ),
            "minimum_oos_pnl_slope_bps_per_window": _optional_decimal_text(
                admission.minimum_oos_pnl_slope_bps_per_window
            ),
            "minimum_total_mark_to_market_pnl_usd": _optional_decimal_text(
                admission.minimum_total_mark_to_market_pnl_usd
            ),
            "minimum_positive_window_fraction": _optional_decimal_text(
                admission.minimum_positive_window_fraction
            ),
        },
        "multiple_testing": {
            "mode": policy.multiple_testing.mode,
            "maximum_candidates_without_warning": (
                policy.multiple_testing.maximum_candidates_without_warning
            ),
        },
    }


def build_selection_governance_report(
    statistics: OOSStatisticsReport,
    policy: SelectionPolicySnapshot,
) -> SelectionGovernanceReport:
    _validate_statistics_report(statistics)
    candidates = tuple(sorted(statistics.candidates, key=lambda item: item.candidate_id))
    candidate_count = len(candidates)
    warnings = _governance_warnings(candidate_count, policy.policy.multiple_testing)
    assessments = tuple(
        _assess_candidate(candidate, policy.policy, candidate_count)
        for candidate in candidates
    )
    identity = {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "statistics_report_id": statistics.report_id,
        "matrix_sha256": statistics.matrix_sha256,
        "policy_sha256": policy.canonical_sha256,
        "policy_mode": policy.policy.mode,
        "multiple_testing_mode": policy.policy.multiple_testing.mode,
        "candidates": [assessment.as_dict() for assessment in assessments],
        "warnings": list(warnings),
    }
    report_id = (
        "admission-report-"
        + sha256_hex(canonical_json_bytes(identity))[:40]
    )
    return SelectionGovernanceReport(
        report_id=report_id,
        statistics_report_id=statistics.report_id,
        matrix_sha256=statistics.matrix_sha256,
        policy_sha256=policy.canonical_sha256,
        policy_mode=policy.policy.mode,
        multiple_testing_mode=policy.policy.multiple_testing.mode,
        candidates=assessments,
        warnings=warnings,
    )


def _assess_candidate(
    candidate: CandidateOOSStatistics,
    policy: SelectionPolicy,
    candidate_count: int,
) -> CandidateAdmissionResult:
    thresholds = policy.admission
    criteria: list[AdmissionCriterionResult] = []

    criteria.append(
        _boolean_criterion(
            name="complete_coverage",
            observed=candidate.coverage == "complete",
            required=thresholds.require_complete_coverage,
            failure_reason="candidate coverage is not complete",
        )
    )
    criteria.append(
        _minimum_integer_criterion(
            name="minimum_evaluation_count",
            observed=candidate.observed_evaluation_count,
            threshold=thresholds.minimum_evaluation_count,
        )
    )
    criteria.append(
        _maximum_decimal_criterion(
            name="maximum_drawdown_pct",
            observed=Decimal(str(candidate.maximum_drawdown_pct)),
            threshold=thresholds.maximum_drawdown_pct,
        )
    )
    criteria.append(
        _minimum_decimal_criterion(
            name="minimum_annualized_sharpe_ratio",
            observed=_optional_float_decimal(candidate.annualized_sharpe_ratio),
            threshold=thresholds.minimum_annualized_sharpe_ratio,
        )
    )
    criteria.append(
        _maximum_decimal_criterion(
            name="maximum_alpha_decay_bps_per_window",
            observed=candidate.alpha_decay_bps_per_window,
            threshold=thresholds.maximum_alpha_decay_bps_per_window,
        )
    )
    criteria.append(
        _minimum_decimal_criterion(
            name="minimum_oos_pnl_slope_bps_per_window",
            observed=candidate.oos_pnl_slope_bps_per_window,
            threshold=thresholds.minimum_oos_pnl_slope_bps_per_window,
        )
    )
    criteria.append(
        _minimum_decimal_criterion(
            name="minimum_total_mark_to_market_pnl_usd",
            observed=candidate.total_mark_to_market_pnl_usd,
            threshold=thresholds.minimum_total_mark_to_market_pnl_usd,
        )
    )
    criteria.append(
        _minimum_decimal_criterion(
            name="minimum_positive_window_fraction",
            observed=_positive_window_fraction(candidate),
            threshold=thresholds.minimum_positive_window_fraction,
        )
    )
    criteria.append(
        _multiple_testing_criterion(
            candidate_count,
            policy.multiple_testing,
        )
    )

    status = (
        "blocked"
        if any(criterion.blocks_admission for criterion in criteria)
        else "admissible_for_human_review"
    )
    return CandidateAdmissionResult(
        candidate_id=candidate.candidate_id,
        candidate_config_sha256=candidate.candidate_config_sha256,
        status=status,
        criteria=tuple(criteria),
    )


def _boolean_criterion(
    *,
    name: str,
    observed: bool,
    required: bool,
    failure_reason: str,
) -> AdmissionCriterionResult:
    if not required:
        return AdmissionCriterionResult(
            name=name,
            status="not_applicable",
            observed=observed,
            threshold=False,
            reason="policy does not require this criterion",
        )
    return AdmissionCriterionResult(
        name=name,
        status="pass" if observed else "fail",
        observed=observed,
        threshold=True,
        reason="criterion satisfied" if observed else failure_reason,
    )


def _minimum_integer_criterion(
    *,
    name: str,
    observed: int,
    threshold: int,
) -> AdmissionCriterionResult:
    passed = observed >= threshold
    return AdmissionCriterionResult(
        name=name,
        status="pass" if passed else "fail",
        observed=observed,
        threshold=threshold,
        reason=(
            "criterion satisfied"
            if passed
            else f"observed {observed} is below minimum {threshold}"
        ),
    )


def _minimum_decimal_criterion(
    *,
    name: str,
    observed: Decimal | None,
    threshold: Decimal | None,
) -> AdmissionCriterionResult:
    if threshold is None:
        return AdmissionCriterionResult(
            name=name,
            status="not_applicable",
            observed=_optional_decimal_text(observed),
            threshold=None,
            reason="policy does not define this threshold",
        )
    if observed is None:
        return AdmissionCriterionResult(
            name=name,
            status="fail",
            observed=None,
            threshold=canonical_decimal(threshold),
            reason="required metric is unavailable",
        )
    passed = observed >= threshold
    return AdmissionCriterionResult(
        name=name,
        status="pass" if passed else "fail",
        observed=canonical_decimal(observed),
        threshold=canonical_decimal(threshold),
        reason=(
            "criterion satisfied"
            if passed
            else (
                f"observed {canonical_decimal(observed)} is below minimum "
                f"{canonical_decimal(threshold)}"
            )
        ),
    )


def _maximum_decimal_criterion(
    *,
    name: str,
    observed: Decimal | None,
    threshold: Decimal | None,
) -> AdmissionCriterionResult:
    if threshold is None:
        return AdmissionCriterionResult(
            name=name,
            status="not_applicable",
            observed=_optional_decimal_text(observed),
            threshold=None,
            reason="policy does not define this threshold",
        )
    if observed is None:
        return AdmissionCriterionResult(
            name=name,
            status="fail",
            observed=None,
            threshold=canonical_decimal(threshold),
            reason="required metric is unavailable",
        )
    passed = observed <= threshold
    return AdmissionCriterionResult(
        name=name,
        status="pass" if passed else "fail",
        observed=canonical_decimal(observed),
        threshold=canonical_decimal(threshold),
        reason=(
            "criterion satisfied"
            if passed
            else (
                f"observed {canonical_decimal(observed)} exceeds maximum "
                f"{canonical_decimal(threshold)}"
            )
        ),
    )


def _multiple_testing_criterion(
    candidate_count: int,
    policy: MultipleTestingPolicy,
) -> AdmissionCriterionResult:
    if policy.mode == "warn_only":
        return AdmissionCriterionResult(
            name="multiple_testing_gate",
            status="pass",
            observed=candidate_count,
            threshold=policy.maximum_candidates_without_warning,
            reason=(
                "warn-only policy does not block candidate admission; "
                "report warnings remain authoritative"
            ),
        )
    passed = candidate_count == 1
    return AdmissionCriterionResult(
        name="multiple_testing_gate",
        status="pass" if passed else "fail",
        observed=candidate_count,
        threshold=1,
        reason=(
            "single-candidate requirement satisfied"
            if passed
            else "policy requires exactly one candidate"
        ),
    )


def _positive_window_fraction(candidate: CandidateOOSStatistics) -> Decimal:
    count = candidate.observed_evaluation_count
    if count == 0:
        return Decimal("0")
    positive = sum(
        observation.mark_to_market_pnl_usd > 0
        for observation in candidate.observations
    )
    return Decimal(positive) / Decimal(count)


def _governance_warnings(
    candidate_count: int,
    policy: MultipleTestingPolicy,
) -> tuple[str, ...]:
    warnings = [
        (
            "Holdout independence and policy pre-registration timing are not "
            "verified by the Phase 6 OOS report."
        )
    ]
    if (
        policy.mode == "warn_only"
        and candidate_count > policy.maximum_candidates_without_warning
    ):
        warnings.append(
            f"Candidate count {candidate_count} exceeds the unadjusted warning "
            f"threshold {policy.maximum_candidates_without_warning}; no "
            "multiple-testing adjustment or significance claim is made."
        )
    if policy.mode == "require_single_candidate" and candidate_count != 1:
        warnings.append(
            f"Policy requires exactly one candidate, but the report contains "
            f"{candidate_count}; all candidates are blocked."
        )
    return tuple(warnings)


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
    for value in config_hashes:
        _validate_digest(value, "candidate_config_sha256")
    for candidate in report.candidates:
        if not candidate.candidate_id or "\x00" in candidate.candidate_id:
            raise ValueError("candidate_id must be a non-empty NUL-free string")
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
        for name, value in (
            (
                "candidate OOS PnL slope",
                candidate.oos_pnl_slope_bps_per_window,
            ),
            (
                "candidate alpha decay",
                candidate.alpha_decay_bps_per_window,
            ),
        ):
            if value is not None and not value.is_finite():
                raise ValueError(f"{name} must be finite")
        if candidate.expected_evaluation_count < 1:
            raise ValueError("candidate expected evaluation count must be positive")
        if (
            candidate.expected_evaluation_count
            != candidate.observed_evaluation_count
        ):
            raise ValueError("candidate OOS evidence is not complete")
        for observation in candidate.observations:
            if not observation.mark_to_market_pnl_usd.is_finite():
                raise ValueError("candidate observation PnL must be finite")


def _required_mapping(
    payload: Mapping[str, Any],
    key: str,
) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"selection policy {key} must be a mapping")
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


def _required_boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _required_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _optional_decimal_string(value: object, name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a decimal string or null")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a decimal string or null") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


def _optional_float_decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


def _validate_optional_range(
    value: Decimal | None,
    name: str,
    *,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
) -> None:
    if value is None:
        return
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {canonical_decimal(minimum)}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {canonical_decimal(maximum)}")


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
