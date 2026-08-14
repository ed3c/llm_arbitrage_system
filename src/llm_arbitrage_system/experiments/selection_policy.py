from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_SELECTION_POLICY_SCHEMA_VERSION = 1
_DECISION_MODE = "human_review_only"
_PRIMARY_METRIC = "total_mark_to_market_pnl_usd"
_PRIMARY_DIRECTION = "maximize"
_MULTIPLE_TESTING_METHOD = "holm_sign_test"
_TIE_BREAKER_METRICS = {
    "alpha_decay_bps_per_window",
    "annualized_sharpe_ratio",
    "maximum_drawdown_pct",
    "positive_window_fraction",
    "worst_window_pnl_usd",
}


@dataclass(frozen=True, slots=True)
class SelectionObjective:
    metric: str = _PRIMARY_METRIC
    direction: str = _PRIMARY_DIRECTION
    tie_breakers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.metric != _PRIMARY_METRIC:
            raise ValueError(
                f"selection objective metric must be {_PRIMARY_METRIC} for schema v1"
            )
        if self.direction != _PRIMARY_DIRECTION:
            raise ValueError(
                f"selection objective direction must be {_PRIMARY_DIRECTION}"
            )
        if len(set(self.tie_breakers)) != len(self.tie_breakers):
            raise ValueError("selection objective tie_breakers cannot contain duplicates")
        unknown = sorted(set(self.tie_breakers) - _TIE_BREAKER_METRICS)
        if unknown:
            raise ValueError(
                "selection objective contains unsupported tie_breakers: "
                + ", ".join(unknown)
            )


@dataclass(frozen=True, slots=True)
class SelectionAdmissionPolicy:
    minimum_candidates: int = 2
    minimum_windows_per_candidate: int = 3
    require_complete_coverage: bool = True
    require_equal_window_indexes: bool = True
    require_equal_test_intervals: bool = True
    require_equal_mark_lag: bool = True
    maximum_drawdown_pct: Decimal = Decimal("25")
    minimum_positive_window_fraction: Decimal = Decimal("0.5")
    maximum_alpha_decay_bps_per_window: Decimal | None = None

    def __post_init__(self) -> None:
        if not 2 <= self.minimum_candidates <= 4096:
            raise ValueError("minimum_candidates must be in [2, 4096]")
        if not 3 <= self.minimum_windows_per_candidate <= 4096:
            raise ValueError("minimum_windows_per_candidate must be in [3, 4096]")
        if not Decimal("0") <= self.maximum_drawdown_pct <= Decimal("100"):
            raise ValueError("maximum_drawdown_pct must be in [0, 100]")
        if not Decimal("0") <= self.minimum_positive_window_fraction <= Decimal("1"):
            raise ValueError("minimum_positive_window_fraction must be in [0, 1]")
        maximum_decay = self.maximum_alpha_decay_bps_per_window
        if maximum_decay is not None and maximum_decay < Decimal("0"):
            raise ValueError("maximum_alpha_decay_bps_per_window cannot be negative")


@dataclass(frozen=True, slots=True)
class MultipleTestingPolicy:
    method: str = _MULTIPLE_TESTING_METHOD
    family_alpha: Decimal = Decimal("0.05")
    minimum_non_tied_pairwise_windows: int = 3
    require_adjusted_pairwise_evidence: bool = False

    def __post_init__(self) -> None:
        if self.method != _MULTIPLE_TESTING_METHOD:
            raise ValueError(
                f"multiple_testing.method must be {_MULTIPLE_TESTING_METHOD}"
            )
        if not Decimal("0") < self.family_alpha < Decimal("1"):
            raise ValueError("multiple_testing.family_alpha must be in (0, 1)")
        if not 3 <= self.minimum_non_tied_pairwise_windows <= 4096:
            raise ValueError(
                "minimum_non_tied_pairwise_windows must be in [3, 4096]"
            )


@dataclass(frozen=True, slots=True)
class SelectionPolicy:
    matrix_sha256: str
    decision_mode: str = _DECISION_MODE
    objective: SelectionObjective = field(default_factory=SelectionObjective)
    admission: SelectionAdmissionPolicy = field(
        default_factory=SelectionAdmissionPolicy
    )
    multiple_testing: MultipleTestingPolicy = field(
        default_factory=MultipleTestingPolicy
    )

    def __post_init__(self) -> None:
        _validate_digest(self.matrix_sha256, "selection policy matrix_sha256")
        if self.decision_mode != _DECISION_MODE:
            raise ValueError(f"selection decision_mode must be {_DECISION_MODE}")


@dataclass(frozen=True, slots=True)
class SelectionPolicySnapshot:
    source_path: Path
    policy: SelectionPolicy
    policy_id: str
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "policy_id": self.policy_id,
            "policy": selection_policy_payload(self.policy),
        }


def load_selection_policy(path: Path) -> SelectionPolicySnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: selection policy is not valid UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid selection-policy YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("selection policy must be a mapping")
    policy = parse_selection_policy(cast(Mapping[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(selection_policy_payload(policy)) + b"\n"
    canonical_sha256 = sha256_hex(canonical_bytes)
    return SelectionPolicySnapshot(
        source_path=resolved,
        policy=policy,
        policy_id=f"selection-policy-{canonical_sha256[:40]}",
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=canonical_sha256,
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_selection_policy(payload: Mapping[str, Any]) -> SelectionPolicy:
    _reject_unknown(
        "selection policy",
        payload,
        {
            "schema_version",
            "matrix_sha256",
            "decision_mode",
            "objective",
            "admission",
            "multiple_testing",
        },
    )
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _SELECTION_POLICY_SCHEMA_VERSION:
        raise ValueError("selection policy schema_version must be 1")

    objective_payload = _section(payload, "objective")
    _reject_unknown(
        "selection policy objective",
        objective_payload,
        {"metric", "direction", "tie_breakers"},
    )
    objective = SelectionObjective(
        metric=_required_string(
            objective_payload.get("metric"),
            "selection policy objective.metric",
        ),
        direction=_required_string(
            objective_payload.get("direction"),
            "selection policy objective.direction",
        ),
        tie_breakers=_string_tuple(
            objective_payload.get("tie_breakers", ()),
            "selection policy objective.tie_breakers",
        ),
    )

    admission_payload = _section(payload, "admission")
    _reject_unknown(
        "selection policy admission",
        admission_payload,
        {
            "minimum_candidates",
            "minimum_windows_per_candidate",
            "require_complete_coverage",
            "require_equal_window_indexes",
            "require_equal_test_intervals",
            "require_equal_mark_lag",
            "maximum_drawdown_pct",
            "minimum_positive_window_fraction",
            "maximum_alpha_decay_bps_per_window",
        },
    )
    admission = SelectionAdmissionPolicy(
        minimum_candidates=_integer(
            admission_payload,
            "minimum_candidates",
            2,
        ),
        minimum_windows_per_candidate=_integer(
            admission_payload,
            "minimum_windows_per_candidate",
            3,
        ),
        require_complete_coverage=_boolean(
            admission_payload,
            "require_complete_coverage",
            True,
        ),
        require_equal_window_indexes=_boolean(
            admission_payload,
            "require_equal_window_indexes",
            True,
        ),
        require_equal_test_intervals=_boolean(
            admission_payload,
            "require_equal_test_intervals",
            True,
        ),
        require_equal_mark_lag=_boolean(
            admission_payload,
            "require_equal_mark_lag",
            True,
        ),
        maximum_drawdown_pct=_decimal_string(
            admission_payload,
            "maximum_drawdown_pct",
            Decimal("25"),
        ),
        minimum_positive_window_fraction=_decimal_string(
            admission_payload,
            "minimum_positive_window_fraction",
            Decimal("0.5"),
        ),
        maximum_alpha_decay_bps_per_window=_optional_decimal_string(
            admission_payload,
            "maximum_alpha_decay_bps_per_window",
        ),
    )

    testing_payload = _section(payload, "multiple_testing")
    _reject_unknown(
        "selection policy multiple_testing",
        testing_payload,
        {
            "method",
            "family_alpha",
            "minimum_non_tied_pairwise_windows",
            "require_adjusted_pairwise_evidence",
        },
    )
    multiple_testing = MultipleTestingPolicy(
        method=_required_string(
            testing_payload.get("method"),
            "selection policy multiple_testing.method",
        ),
        family_alpha=_decimal_string(
            testing_payload,
            "family_alpha",
            Decimal("0.05"),
        ),
        minimum_non_tied_pairwise_windows=_integer(
            testing_payload,
            "minimum_non_tied_pairwise_windows",
            3,
        ),
        require_adjusted_pairwise_evidence=_boolean(
            testing_payload,
            "require_adjusted_pairwise_evidence",
            False,
        ),
    )
    return SelectionPolicy(
        matrix_sha256=_required_string(
            payload.get("matrix_sha256"),
            "selection policy matrix_sha256",
        ),
        decision_mode=_required_string(
            payload.get("decision_mode"),
            "selection policy decision_mode",
        ),
        objective=objective,
        admission=admission,
        multiple_testing=multiple_testing,
    )


def selection_policy_payload(policy: SelectionPolicy) -> dict[str, Any]:
    return {
        "schema_version": _SELECTION_POLICY_SCHEMA_VERSION,
        "matrix_sha256": policy.matrix_sha256,
        "decision_mode": policy.decision_mode,
        "objective": {
            "metric": policy.objective.metric,
            "direction": policy.objective.direction,
            "tie_breakers": list(policy.objective.tie_breakers),
        },
        "admission": {
            "minimum_candidates": policy.admission.minimum_candidates,
            "minimum_windows_per_candidate": (
                policy.admission.minimum_windows_per_candidate
            ),
            "require_complete_coverage": (
                policy.admission.require_complete_coverage
            ),
            "require_equal_window_indexes": (
                policy.admission.require_equal_window_indexes
            ),
            "require_equal_test_intervals": (
                policy.admission.require_equal_test_intervals
            ),
            "require_equal_mark_lag": policy.admission.require_equal_mark_lag,
            "maximum_drawdown_pct": _decimal_text(
                policy.admission.maximum_drawdown_pct
            ),
            "minimum_positive_window_fraction": _decimal_text(
                policy.admission.minimum_positive_window_fraction
            ),
            "maximum_alpha_decay_bps_per_window": (
                None
                if policy.admission.maximum_alpha_decay_bps_per_window is None
                else _decimal_text(
                    policy.admission.maximum_alpha_decay_bps_per_window
                )
            ),
        },
        "multiple_testing": {
            "method": policy.multiple_testing.method,
            "family_alpha": _decimal_text(policy.multiple_testing.family_alpha),
            "minimum_non_tied_pairwise_windows": (
                policy.multiple_testing.minimum_non_tied_pairwise_windows
            ),
            "require_adjusted_pairwise_evidence": (
                policy.multiple_testing.require_adjusted_pairwise_evidence
            ),
        },
    }


def _section(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"selection policy {key} must be a mapping")
    return cast(Mapping[str, Any], value)


def _reject_unknown(
    name: str,
    payload: Mapping[str, Any],
    allowed: set[str],
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of strings")
    result: list[str] = []
    for item in value:
        result.append(_required_string(item, name))
    return tuple(result)


def _integer(payload: Mapping[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"selection policy {key} must be an integer")
    return int(value)


def _boolean(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"selection policy {key} must be a boolean")
    return value


def _decimal_string(
    payload: Mapping[str, Any],
    key: str,
    default: Decimal,
) -> Decimal:
    value = payload.get(key, _decimal_text(default))
    if not isinstance(value, str):
        raise ValueError(f"selection policy {key} must be a decimal string")
    return _parse_decimal(value, f"selection policy {key}")


def _optional_decimal_string(
    payload: Mapping[str, Any],
    key: str,
) -> Decimal | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"selection policy {key} must be a decimal string or null")
    return _parse_decimal(value, f"selection policy {key}")


def _parse_decimal(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} is not a valid decimal string") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _validate_digest(value: str, name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
