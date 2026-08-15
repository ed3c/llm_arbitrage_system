from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_REPLICATION_PLAN_SCHEMA_VERSION = 1
_REPLICATION_SCOPE = "independent_offline_replication"
_CANDIDATE_PREFIX = "candidate-"


@dataclass(frozen=True, slots=True)
class ReplicationCandidate:
    candidate_id: str
    candidate_config_sha256: str

    def __post_init__(self) -> None:
        _validate_candidate_id(self.candidate_id)
        _validate_digest(
            self.candidate_config_sha256,
            "replication candidate candidate_config_sha256",
        )


@dataclass(frozen=True, slots=True)
class ReplicationIndependencePolicy:
    minimum_replications: int = 3
    minimum_distinct_quorum_signers: int = 2
    minimum_distinct_dossier_signers: int = 2
    minimum_distinct_statistics_signers: int = 2
    require_disjoint_test_semantic_sha256: bool = True
    require_distinct_matrix_sha256: bool = True
    require_distinct_dossier_sha256: bool = True
    require_distinct_quorum_envelope_sha256: bool = True
    prohibit_statistics_report_reuse: bool = True

    def __post_init__(self) -> None:
        if not 2 <= self.minimum_replications <= 64:
            raise ValueError("minimum_replications must be in [2, 64]")
        signer_minima = {
            "minimum_distinct_quorum_signers": self.minimum_distinct_quorum_signers,
            "minimum_distinct_dossier_signers": self.minimum_distinct_dossier_signers,
            "minimum_distinct_statistics_signers": (
                self.minimum_distinct_statistics_signers
            ),
        }
        for name, value in signer_minima.items():
            if not 1 <= value <= 64:
                raise ValueError(f"{name} must be in [1, 64]")
            if value > self.minimum_replications:
                raise ValueError(f"{name} cannot exceed minimum_replications")
        required_true = {
            "require_disjoint_test_semantic_sha256": (
                self.require_disjoint_test_semantic_sha256
            ),
            "require_distinct_matrix_sha256": self.require_distinct_matrix_sha256,
            "require_distinct_dossier_sha256": self.require_distinct_dossier_sha256,
            "require_distinct_quorum_envelope_sha256": (
                self.require_distinct_quorum_envelope_sha256
            ),
            "prohibit_statistics_report_reuse": (
                self.prohibit_statistics_report_reuse
            ),
        }
        disabled = sorted(name for name, enabled in required_true.items() if not enabled)
        if disabled:
            raise ValueError(
                "replication independence controls must remain enabled: "
                + ", ".join(disabled)
            )


@dataclass(frozen=True, slots=True)
class ReplicationComparabilityPolicy:
    require_equal_code_revision: bool = True
    require_equal_package_version: bool = True
    require_equal_periods_per_year: bool = True
    require_equal_terminal_mark_lag: bool = True

    def __post_init__(self) -> None:
        required_true = {
            "require_equal_code_revision": self.require_equal_code_revision,
            "require_equal_package_version": self.require_equal_package_version,
            "require_equal_periods_per_year": self.require_equal_periods_per_year,
            "require_equal_terminal_mark_lag": self.require_equal_terminal_mark_lag,
        }
        disabled = sorted(name for name, enabled in required_true.items() if not enabled)
        if disabled:
            raise ValueError(
                "replication comparability controls must remain enabled: "
                + ", ".join(disabled)
            )


@dataclass(frozen=True, slots=True)
class ReplicationAcceptancePolicy:
    minimum_research_approved_fraction: Decimal = Decimal("0.67")
    minimum_positive_replication_fraction: Decimal = Decimal("0.67")
    minimum_windows_per_replication: int = 3
    maximum_failed_replications: int = 1
    maximum_insufficient_replications: int = 0
    minimum_worst_case_total_pnl_usd: Decimal = Decimal("0")
    minimum_median_total_pnl_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not Decimal("0") < self.minimum_research_approved_fraction <= Decimal("1"):
            raise ValueError("minimum_research_approved_fraction must be in (0, 1]")
        if not Decimal("0") < self.minimum_positive_replication_fraction <= Decimal("1"):
            raise ValueError("minimum_positive_replication_fraction must be in (0, 1]")
        if not 1 <= self.minimum_windows_per_replication <= 4096:
            raise ValueError("minimum_windows_per_replication must be in [1, 4096]")
        if not 0 <= self.maximum_failed_replications <= 63:
            raise ValueError("maximum_failed_replications must be in [0, 63]")
        if not 0 <= self.maximum_insufficient_replications <= 63:
            raise ValueError("maximum_insufficient_replications must be in [0, 63]")
        if not self.minimum_worst_case_total_pnl_usd.is_finite():
            raise ValueError("minimum_worst_case_total_pnl_usd must be finite")
        if not self.minimum_median_total_pnl_usd.is_finite():
            raise ValueError("minimum_median_total_pnl_usd must be finite")


@dataclass(frozen=True, slots=True)
class ReplicationAuthorityPolicy:
    human_admit_required: bool = True
    automatic_promotion: bool = False
    release_authorized: bool = False
    deployment_authorized: bool = False
    trading_authorized: bool = False

    def __post_init__(self) -> None:
        if not self.human_admit_required:
            raise ValueError("human_admit_required must remain true")
        if self.automatic_promotion:
            raise ValueError("automatic_promotion must remain false")
        if self.release_authorized:
            raise ValueError("release_authorized must remain false")
        if self.deployment_authorized:
            raise ValueError("deployment_authorized must remain false")
        if self.trading_authorized:
            raise ValueError("trading_authorized must remain false")


@dataclass(frozen=True, slots=True)
class ReplicationPlan:
    candidate: ReplicationCandidate
    independence: ReplicationIndependencePolicy = field(
        default_factory=ReplicationIndependencePolicy
    )
    comparability: ReplicationComparabilityPolicy = field(
        default_factory=ReplicationComparabilityPolicy
    )
    acceptance: ReplicationAcceptancePolicy = field(
        default_factory=ReplicationAcceptancePolicy
    )
    authority: ReplicationAuthorityPolicy = field(
        default_factory=ReplicationAuthorityPolicy
    )
    scope: str = _REPLICATION_SCOPE

    def __post_init__(self) -> None:
        if self.scope != _REPLICATION_SCOPE:
            raise ValueError(f"replication scope must be {_REPLICATION_SCOPE}")
        non_consistent_budget = (
            self.acceptance.maximum_failed_replications
            + self.acceptance.maximum_insufficient_replications
        )
        if non_consistent_budget >= self.independence.minimum_replications:
            raise ValueError(
                "failed plus insufficient replication budgets must leave at least "
                "one consistent replication"
            )


@dataclass(frozen=True, slots=True)
class ReplicationPlanSnapshot:
    source_path: Path
    plan: ReplicationPlan
    plan_id: str
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "plan_id": self.plan_id,
            "plan": replication_plan_payload(self.plan),
        }


def load_replication_plan(path: Path) -> ReplicationPlanSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: replication plan is not valid UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid replication-plan YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("replication plan must be a mapping")
    plan = parse_replication_plan(cast(Mapping[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(replication_plan_payload(plan)) + b"\n"
    canonical_sha256 = sha256_hex(canonical_bytes)
    return ReplicationPlanSnapshot(
        source_path=resolved,
        plan=plan,
        plan_id=f"replication-plan-{canonical_sha256[:40]}",
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=canonical_sha256,
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_replication_plan(payload: Mapping[str, Any]) -> ReplicationPlan:
    _require_fields(
        "replication plan",
        payload,
        {
            "schema_version",
            "scope",
            "candidate",
            "independence",
            "comparability",
            "acceptance",
            "authority",
        },
    )
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or schema_version != _REPLICATION_PLAN_SCHEMA_VERSION
    ):
        raise ValueError("replication plan schema_version must be 1")

    candidate_payload = _section(payload, "candidate")
    _require_fields(
        "replication candidate",
        candidate_payload,
        {"candidate_id", "candidate_config_sha256"},
    )
    candidate = ReplicationCandidate(
        candidate_id=_string(
            candidate_payload.get("candidate_id"),
            "replication candidate candidate_id",
        ),
        candidate_config_sha256=_string(
            candidate_payload.get("candidate_config_sha256"),
            "replication candidate candidate_config_sha256",
        ),
    )

    independence_payload = _section(payload, "independence")
    _require_fields(
        "replication independence",
        independence_payload,
        {
            "minimum_replications",
            "minimum_distinct_quorum_signers",
            "minimum_distinct_dossier_signers",
            "minimum_distinct_statistics_signers",
            "require_disjoint_test_semantic_sha256",
            "require_distinct_matrix_sha256",
            "require_distinct_dossier_sha256",
            "require_distinct_quorum_envelope_sha256",
            "prohibit_statistics_report_reuse",
        },
    )
    independence = ReplicationIndependencePolicy(
        minimum_replications=_integer(
            independence_payload.get("minimum_replications"),
            "replication independence minimum_replications",
            minimum=2,
            maximum=64,
        ),
        minimum_distinct_quorum_signers=_integer(
            independence_payload.get("minimum_distinct_quorum_signers"),
            "replication independence minimum_distinct_quorum_signers",
            minimum=1,
            maximum=64,
        ),
        minimum_distinct_dossier_signers=_integer(
            independence_payload.get("minimum_distinct_dossier_signers"),
            "replication independence minimum_distinct_dossier_signers",
            minimum=1,
            maximum=64,
        ),
        minimum_distinct_statistics_signers=_integer(
            independence_payload.get("minimum_distinct_statistics_signers"),
            "replication independence minimum_distinct_statistics_signers",
            minimum=1,
            maximum=64,
        ),
        require_disjoint_test_semantic_sha256=_boolean(
            independence_payload.get("require_disjoint_test_semantic_sha256"),
            "replication independence require_disjoint_test_semantic_sha256",
        ),
        require_distinct_matrix_sha256=_boolean(
            independence_payload.get("require_distinct_matrix_sha256"),
            "replication independence require_distinct_matrix_sha256",
        ),
        require_distinct_dossier_sha256=_boolean(
            independence_payload.get("require_distinct_dossier_sha256"),
            "replication independence require_distinct_dossier_sha256",
        ),
        require_distinct_quorum_envelope_sha256=_boolean(
            independence_payload.get("require_distinct_quorum_envelope_sha256"),
            "replication independence require_distinct_quorum_envelope_sha256",
        ),
        prohibit_statistics_report_reuse=_boolean(
            independence_payload.get("prohibit_statistics_report_reuse"),
            "replication independence prohibit_statistics_report_reuse",
        ),
    )

    comparability_payload = _section(payload, "comparability")
    _require_fields(
        "replication comparability",
        comparability_payload,
        {
            "require_equal_code_revision",
            "require_equal_package_version",
            "require_equal_periods_per_year",
            "require_equal_terminal_mark_lag",
        },
    )
    comparability = ReplicationComparabilityPolicy(
        require_equal_code_revision=_boolean(
            comparability_payload.get("require_equal_code_revision"),
            "replication comparability require_equal_code_revision",
        ),
        require_equal_package_version=_boolean(
            comparability_payload.get("require_equal_package_version"),
            "replication comparability require_equal_package_version",
        ),
        require_equal_periods_per_year=_boolean(
            comparability_payload.get("require_equal_periods_per_year"),
            "replication comparability require_equal_periods_per_year",
        ),
        require_equal_terminal_mark_lag=_boolean(
            comparability_payload.get("require_equal_terminal_mark_lag"),
            "replication comparability require_equal_terminal_mark_lag",
        ),
    )

    acceptance_payload = _section(payload, "acceptance")
    _require_fields(
        "replication acceptance",
        acceptance_payload,
        {
            "minimum_research_approved_fraction",
            "minimum_positive_replication_fraction",
            "minimum_windows_per_replication",
            "maximum_failed_replications",
            "maximum_insufficient_replications",
            "minimum_worst_case_total_pnl_usd",
            "minimum_median_total_pnl_usd",
        },
    )
    acceptance = ReplicationAcceptancePolicy(
        minimum_research_approved_fraction=_decimal_string(
            acceptance_payload.get("minimum_research_approved_fraction"),
            "replication acceptance minimum_research_approved_fraction",
        ),
        minimum_positive_replication_fraction=_decimal_string(
            acceptance_payload.get("minimum_positive_replication_fraction"),
            "replication acceptance minimum_positive_replication_fraction",
        ),
        minimum_windows_per_replication=_integer(
            acceptance_payload.get("minimum_windows_per_replication"),
            "replication acceptance minimum_windows_per_replication",
            minimum=1,
            maximum=4096,
        ),
        maximum_failed_replications=_integer(
            acceptance_payload.get("maximum_failed_replications"),
            "replication acceptance maximum_failed_replications",
            minimum=0,
            maximum=63,
        ),
        maximum_insufficient_replications=_integer(
            acceptance_payload.get("maximum_insufficient_replications"),
            "replication acceptance maximum_insufficient_replications",
            minimum=0,
            maximum=63,
        ),
        minimum_worst_case_total_pnl_usd=_decimal_string(
            acceptance_payload.get("minimum_worst_case_total_pnl_usd"),
            "replication acceptance minimum_worst_case_total_pnl_usd",
        ),
        minimum_median_total_pnl_usd=_decimal_string(
            acceptance_payload.get("minimum_median_total_pnl_usd"),
            "replication acceptance minimum_median_total_pnl_usd",
        ),
    )

    authority_payload = _section(payload, "authority")
    _require_fields(
        "replication authority",
        authority_payload,
        {
            "human_admit_required",
            "automatic_promotion",
            "release_authorized",
            "deployment_authorized",
            "trading_authorized",
        },
    )
    authority = ReplicationAuthorityPolicy(
        human_admit_required=_boolean(
            authority_payload.get("human_admit_required"),
            "replication authority human_admit_required",
        ),
        automatic_promotion=_boolean(
            authority_payload.get("automatic_promotion"),
            "replication authority automatic_promotion",
        ),
        release_authorized=_boolean(
            authority_payload.get("release_authorized"),
            "replication authority release_authorized",
        ),
        deployment_authorized=_boolean(
            authority_payload.get("deployment_authorized"),
            "replication authority deployment_authorized",
        ),
        trading_authorized=_boolean(
            authority_payload.get("trading_authorized"),
            "replication authority trading_authorized",
        ),
    )

    return ReplicationPlan(
        candidate=candidate,
        independence=independence,
        comparability=comparability,
        acceptance=acceptance,
        authority=authority,
        scope=_string(payload.get("scope"), "replication scope"),
    )


def replication_plan_payload(plan: ReplicationPlan) -> dict[str, Any]:
    return {
        "schema_version": _REPLICATION_PLAN_SCHEMA_VERSION,
        "scope": plan.scope,
        "candidate": {
            "candidate_id": plan.candidate.candidate_id,
            "candidate_config_sha256": plan.candidate.candidate_config_sha256,
        },
        "independence": {
            "minimum_replications": plan.independence.minimum_replications,
            "minimum_distinct_quorum_signers": (
                plan.independence.minimum_distinct_quorum_signers
            ),
            "minimum_distinct_dossier_signers": (
                plan.independence.minimum_distinct_dossier_signers
            ),
            "minimum_distinct_statistics_signers": (
                plan.independence.minimum_distinct_statistics_signers
            ),
            "require_disjoint_test_semantic_sha256": (
                plan.independence.require_disjoint_test_semantic_sha256
            ),
            "require_distinct_matrix_sha256": (
                plan.independence.require_distinct_matrix_sha256
            ),
            "require_distinct_dossier_sha256": (
                plan.independence.require_distinct_dossier_sha256
            ),
            "require_distinct_quorum_envelope_sha256": (
                plan.independence.require_distinct_quorum_envelope_sha256
            ),
            "prohibit_statistics_report_reuse": (
                plan.independence.prohibit_statistics_report_reuse
            ),
        },
        "comparability": {
            "require_equal_code_revision": (
                plan.comparability.require_equal_code_revision
            ),
            "require_equal_package_version": (
                plan.comparability.require_equal_package_version
            ),
            "require_equal_periods_per_year": (
                plan.comparability.require_equal_periods_per_year
            ),
            "require_equal_terminal_mark_lag": (
                plan.comparability.require_equal_terminal_mark_lag
            ),
        },
        "acceptance": {
            "minimum_research_approved_fraction": _decimal_text(
                plan.acceptance.minimum_research_approved_fraction
            ),
            "minimum_positive_replication_fraction": _decimal_text(
                plan.acceptance.minimum_positive_replication_fraction
            ),
            "minimum_windows_per_replication": (
                plan.acceptance.minimum_windows_per_replication
            ),
            "maximum_failed_replications": (
                plan.acceptance.maximum_failed_replications
            ),
            "maximum_insufficient_replications": (
                plan.acceptance.maximum_insufficient_replications
            ),
            "minimum_worst_case_total_pnl_usd": _decimal_text(
                plan.acceptance.minimum_worst_case_total_pnl_usd
            ),
            "minimum_median_total_pnl_usd": _decimal_text(
                plan.acceptance.minimum_median_total_pnl_usd
            ),
        },
        "authority": {
            "human_admit_required": plan.authority.human_admit_required,
            "automatic_promotion": plan.authority.automatic_promotion,
            "release_authorized": plan.authority.release_authorized,
            "deployment_authorized": plan.authority.deployment_authorized,
            "trading_authorized": plan.authority.trading_authorized,
        },
    }


def _section(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"replication plan {key} must be a mapping")
    return cast(Mapping[str, Any], value)


def _require_fields(
    name: str,
    payload: Mapping[str, Any],
    expected: set[str],
) -> None:
    actual = set(payload)
    missing = sorted(expected - actual)
    if missing:
        raise ValueError(f"{name} is missing fields: {', '.join(missing)}")
    unknown = sorted(actual - expected)
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return int(value)


def _decimal_string(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a decimal string")
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


def _validate_candidate_id(value: str) -> None:
    suffix = value.removeprefix(_CANDIDATE_PREFIX)
    if (
        not value.startswith(_CANDIDATE_PREFIX)
        or len(suffix) != 24
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError("candidate_id must use candidate-<24 lowercase hex>")


def _validate_digest(value: str, name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
