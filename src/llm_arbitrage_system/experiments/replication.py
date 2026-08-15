from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.replication_inputs import (
    ReplicationCohortInput,
    load_replication_inputs,
)
from llm_arbitrage_system.experiments.replication_plan import (
    ReplicationPlanSnapshot,
    load_replication_plan,
)
from llm_arbitrage_system.experiments.review_quorum import (
    load_review_quorum_envelope,
)
from llm_arbitrage_system.experiments.review_quorum_signing import (
    verify_review_quorum_attestation,
)
from llm_arbitrage_system.experiments.selection_dossier import (
    load_selection_dossier,
)
from llm_arbitrage_system.experiments.selection_signing import (
    verify_selection_dossier_attestation,
)
from llm_arbitrage_system.experiments.statistics_signing import (
    load_statistics_report,
    verify_statistics_attestation,
)

_REPLICATION_REPORT_SCHEMA_VERSION = 1
_APPROVED_QUORUM_STATUS = "approved_for_research_only"
_REPLICATION_STATES = {
    "replication_insufficient",
    "replication_failed",
    "replication_consistent",
}
_CANDIDATE_FIELDS = {
    "candidate_id",
    "candidate_config_sha256",
    "coverage",
    "expected_evaluation_count",
    "observed_evaluation_count",
    "initial_equity_usd",
    "ending_equity_usd",
    "total_mark_to_market_pnl_usd",
    "maximum_drawdown_pct",
    "annualized_sharpe_ratio",
    "alpha_decay_method",
    "oos_pnl_slope_bps_per_window",
    "alpha_decay_bps_per_window",
    "mark_lag_microseconds",
    "observations",
}
_OBSERVATION_FIELDS = {
    "evaluation_id",
    "experiment_id",
    "valuation_id",
    "candidate_id",
    "candidate_config_sha256",
    "window_index",
    "test_start",
    "test_end",
    "test_semantic_sha256",
    "mark_lag_microseconds",
    "mark_to_market_pnl_usd",
    "ending_equity_usd",
    "period_return",
}


@dataclass(frozen=True, slots=True)
class ReplicationCohortEvidence:
    cohort_id: str
    statistics_report_id: str
    statistics_report_sha256: str
    statistics_signer_key_id: str
    dossier_id: str
    dossier_sha256: str
    dossier_signer_key_id: str
    quorum_envelope_id: str
    quorum_envelope_sha256: str
    quorum_signer_key_id: str
    quorum_status: str
    matrix_sha256: str
    code_revision: str
    package_version: str
    periods_per_year: int
    mark_lag_microseconds: int
    window_count: int
    test_semantic_sha256: tuple[str, ...]
    total_mark_to_market_pnl_usd: Decimal
    state: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state not in _REPLICATION_STATES:
            raise ValueError(f"invalid replication cohort state: {self.state}")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "statistics_report_id": self.statistics_report_id,
            "statistics_report_sha256": self.statistics_report_sha256,
            "statistics_signer_key_id": self.statistics_signer_key_id,
            "dossier_id": self.dossier_id,
            "dossier_sha256": self.dossier_sha256,
            "dossier_signer_key_id": self.dossier_signer_key_id,
            "quorum_envelope_id": self.quorum_envelope_id,
            "quorum_envelope_sha256": self.quorum_envelope_sha256,
            "quorum_signer_key_id": self.quorum_signer_key_id,
            "quorum_status": self.quorum_status,
            "matrix_sha256": self.matrix_sha256,
            "code_revision": self.code_revision,
            "package_version": self.package_version,
            "periods_per_year": self.periods_per_year,
            "mark_lag_microseconds": self.mark_lag_microseconds,
            "window_count": self.window_count,
            "test_semantic_sha256": list(self.test_semantic_sha256),
            "total_mark_to_market_pnl_usd": _decimal_text(
                self.total_mark_to_market_pnl_usd
            ),
            "state": self.state,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class ReplicationReport:
    report_id: str
    plan_id: str
    plan_sha256: str
    candidate_id: str
    candidate_config_sha256: str
    status: str
    cohort_count: int
    research_approved_count: int
    positive_replication_count: int
    failed_replication_count: int
    insufficient_replication_count: int
    research_approved_fraction: Decimal
    positive_replication_fraction: Decimal
    worst_case_total_pnl_usd: Decimal
    median_total_pnl_usd: Decimal
    independence_checks: tuple[tuple[str, bool], ...]
    comparability_checks: tuple[tuple[str, bool], ...]
    acceptance_checks: tuple[tuple[str, bool], ...]
    cohorts: tuple[ReplicationCohortEvidence, ...]

    def __post_init__(self) -> None:
        if self.status not in _REPLICATION_STATES:
            raise ValueError(f"invalid replication report status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _REPLICATION_REPORT_SCHEMA_VERSION,
            "report_id": self.report_id,
            "plan_id": self.plan_id,
            "plan_sha256": self.plan_sha256,
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "status": self.status,
            "cohort_count": self.cohort_count,
            "research_approved_count": self.research_approved_count,
            "positive_replication_count": self.positive_replication_count,
            "failed_replication_count": self.failed_replication_count,
            "insufficient_replication_count": self.insufficient_replication_count,
            "research_approved_fraction": _decimal_text(
                self.research_approved_fraction
            ),
            "positive_replication_fraction": _decimal_text(
                self.positive_replication_fraction
            ),
            "worst_case_total_pnl_usd": _decimal_text(
                self.worst_case_total_pnl_usd
            ),
            "median_total_pnl_usd": _decimal_text(self.median_total_pnl_usd),
            "independence_checks": dict(self.independence_checks),
            "comparability_checks": dict(self.comparability_checks),
            "acceptance_checks": dict(self.acceptance_checks),
            "cohorts": [cohort.identity_payload() for cohort in self.cohorts],
            "selection": None,
            "promotion": None,
            "human_admit_required": True,
            "automatic_promotion": False,
            "release_authorized": False,
            "deployment_authorized": False,
            "trading_authorized": False,
            "assumptions": [
                (
                    "Replication independence is bounded to checked signed identifiers, "
                    "signer diversity, and disjoint test-slice semantic hashes."
                ),
                (
                    "Caller-supplied terminal marks remain unproven as source-market "
                    "truth even when their signed reports verify."
                ),
                (
                    "replication_consistent is an offline evidence state and is not a "
                    "winner, promotion, release, deployment, or trading authorization."
                ),
            ],
            "evidence_boundary": (
                "This report describes authenticated offline cohort consistency under "
                "one preregistered contract. It does not prove sampling independence, "
                "source-market truth, causal alpha, live realized profit, future "
                "returns, legal suitability, release readiness, deployment authority, "
                "or live-trading authority."
            ),
        }


def build_replication_report(
    *,
    plan_path: Path,
    inputs_path: Path,
) -> ReplicationReport:
    plan_snapshot = load_replication_plan(plan_path)
    inputs = load_replication_inputs(inputs_path)
    cohorts = tuple(
        _evaluate_cohort(plan_snapshot, cohort)
        for cohort in inputs.cohorts
    )
    independence_checks = _independence_checks(plan_snapshot, cohorts)
    comparability_checks = _comparability_checks(cohorts)

    cohort_count = len(cohorts)
    research_approved_count = sum(
        cohort.quorum_status == _APPROVED_QUORUM_STATUS for cohort in cohorts
    )
    positive_replication_count = sum(
        cohort.state == "replication_consistent" for cohort in cohorts
    )
    failed_replication_count = sum(
        cohort.state == "replication_failed" for cohort in cohorts
    )
    insufficient_replication_count = sum(
        cohort.state == "replication_insufficient" for cohort in cohorts
    )
    approved_fraction = _fraction(research_approved_count, cohort_count)
    positive_fraction = _fraction(positive_replication_count, cohort_count)
    totals = tuple(cohort.total_mark_to_market_pnl_usd for cohort in cohorts)
    worst = min(totals)
    median = _median_decimal(totals)

    acceptance = plan_snapshot.plan.acceptance
    acceptance_checks = _sorted_checks(
        {
            "minimum_research_approved_fraction": (
                approved_fraction >= acceptance.minimum_research_approved_fraction
            ),
            "minimum_positive_replication_fraction": (
                positive_fraction >= acceptance.minimum_positive_replication_fraction
            ),
            "maximum_failed_replications": (
                failed_replication_count <= acceptance.maximum_failed_replications
            ),
            "maximum_insufficient_replications": (
                insufficient_replication_count
                <= acceptance.maximum_insufficient_replications
            ),
            "minimum_worst_case_total_pnl_usd": (
                worst >= acceptance.minimum_worst_case_total_pnl_usd
            ),
            "minimum_median_total_pnl_usd": (
                median >= acceptance.minimum_median_total_pnl_usd
            ),
        }
    )
    if not _checks_pass(independence_checks) or not _checks_pass(
        comparability_checks
    ):
        status = "replication_insufficient"
    elif _checks_pass(acceptance_checks):
        status = "replication_consistent"
    else:
        status = "replication_failed"

    identity = {
        "schema_version": _REPLICATION_REPORT_SCHEMA_VERSION,
        "plan_id": plan_snapshot.plan_id,
        "plan_sha256": plan_snapshot.canonical_sha256,
        "candidate_id": plan_snapshot.plan.candidate.candidate_id,
        "candidate_config_sha256": (
            plan_snapshot.plan.candidate.candidate_config_sha256
        ),
        "status": status,
        "cohort_count": cohort_count,
        "research_approved_count": research_approved_count,
        "positive_replication_count": positive_replication_count,
        "failed_replication_count": failed_replication_count,
        "insufficient_replication_count": insufficient_replication_count,
        "research_approved_fraction": _decimal_text(approved_fraction),
        "positive_replication_fraction": _decimal_text(positive_fraction),
        "worst_case_total_pnl_usd": _decimal_text(worst),
        "median_total_pnl_usd": _decimal_text(median),
        "independence_checks": dict(independence_checks),
        "comparability_checks": dict(comparability_checks),
        "acceptance_checks": dict(acceptance_checks),
        "cohorts": [cohort.identity_payload() for cohort in cohorts],
    }
    report_id = "replication-report-" + sha256_hex(
        canonical_json_bytes(identity)
    )[:40]
    return ReplicationReport(
        report_id=report_id,
        plan_id=plan_snapshot.plan_id,
        plan_sha256=plan_snapshot.canonical_sha256,
        candidate_id=plan_snapshot.plan.candidate.candidate_id,
        candidate_config_sha256=(
            plan_snapshot.plan.candidate.candidate_config_sha256
        ),
        status=status,
        cohort_count=cohort_count,
        research_approved_count=research_approved_count,
        positive_replication_count=positive_replication_count,
        failed_replication_count=failed_replication_count,
        insufficient_replication_count=insufficient_replication_count,
        research_approved_fraction=approved_fraction,
        positive_replication_fraction=positive_fraction,
        worst_case_total_pnl_usd=worst,
        median_total_pnl_usd=median,
        independence_checks=independence_checks,
        comparability_checks=comparability_checks,
        acceptance_checks=acceptance_checks,
        cohorts=cohorts,
    )


def _evaluate_cohort(
    plan_snapshot: ReplicationPlanSnapshot,
    cohort: ReplicationCohortInput,
) -> ReplicationCohortEvidence:
    statistics_verification = verify_statistics_attestation(
        cohort.statistics.evidence_path,
        cohort.statistics.attestation_path,
        trusted_public_key_path=cohort.statistics.trusted_public_key_path,
    )
    dossier_verification = verify_selection_dossier_attestation(
        cohort.dossier.evidence_path,
        cohort.dossier.attestation_path,
        trusted_public_key_path=cohort.dossier.trusted_public_key_path,
    )
    quorum_verification = verify_review_quorum_attestation(
        cohort.quorum.evidence_path,
        cohort.quorum.attestation_path,
        trusted_public_key_path=cohort.quorum.trusted_public_key_path,
    )
    if not all(
        (
            statistics_verification.trusted_key_matched,
            dossier_verification.trusted_key_matched,
            quorum_verification.trusted_key_matched,
        )
    ):
        raise ValueError(f"cohort {cohort.cohort_id} did not match every trusted key")

    statistics = load_statistics_report(cohort.statistics.evidence_path)
    dossier = load_selection_dossier(cohort.dossier.evidence_path)
    quorum = load_review_quorum_envelope(cohort.quorum.evidence_path)
    _verify_attestation_snapshots(
        cohort.cohort_id,
        statistics_verification=statistics_verification,
        statistics=statistics,
        dossier_verification=dossier_verification,
        dossier=dossier,
        quorum_verification=quorum_verification,
        quorum=quorum,
    )
    _verify_evidence_chain(
        plan_snapshot,
        cohort.cohort_id,
        statistics=statistics,
        dossier=dossier,
        quorum=quorum,
    )

    candidate = _statistics_candidate(
        statistics.payload,
        plan_snapshot.plan.candidate.candidate_id,
        plan_snapshot.plan.candidate.candidate_config_sha256,
    )
    total_pnl = _decimal_string(
        candidate.get("total_mark_to_market_pnl_usd"),
        f"cohort {cohort.cohort_id} total_mark_to_market_pnl_usd",
    )
    mark_lag = _integer(
        candidate.get("mark_lag_microseconds"),
        f"cohort {cohort.cohort_id} mark_lag_microseconds",
        minimum=0,
    )
    test_hashes = _candidate_observations(
        candidate,
        candidate_id=plan_snapshot.plan.candidate.candidate_id,
        candidate_config_sha256=(
            plan_snapshot.plan.candidate.candidate_config_sha256
        ),
        mark_lag_microseconds=mark_lag,
        cohort_id=cohort.cohort_id,
    )
    window_count = len(test_hashes)
    reasons: list[str] = []
    quorum_status = quorum.envelope.status
    if quorum_status != _APPROVED_QUORUM_STATUS:
        reasons.append(f"quorum_status:{quorum_status}")
    if window_count < plan_snapshot.plan.acceptance.minimum_windows_per_replication:
        reasons.append("minimum_windows_per_replication_not_met")
    if reasons:
        state = "replication_insufficient"
    elif total_pnl > Decimal("0"):
        state = "replication_consistent"
    else:
        state = "replication_failed"
        reasons.append("non_positive_total_mark_to_market_pnl")

    payload = statistics.payload
    return ReplicationCohortEvidence(
        cohort_id=cohort.cohort_id,
        statistics_report_id=statistics.report_id,
        statistics_report_sha256=statistics.source_sha256,
        statistics_signer_key_id=statistics_verification.key_id,
        dossier_id=dossier.dossier.dossier_id,
        dossier_sha256=dossier.source_sha256,
        dossier_signer_key_id=dossier_verification.key_id,
        quorum_envelope_id=quorum.envelope.envelope_id,
        quorum_envelope_sha256=quorum.source_sha256,
        quorum_signer_key_id=quorum_verification.key_id,
        quorum_status=quorum_status,
        matrix_sha256=statistics.matrix_sha256,
        code_revision=_required_string(
            payload,
            "code_revision",
            f"cohort {cohort.cohort_id} statistics report",
        ),
        package_version=_required_string(
            payload,
            "package_version",
            f"cohort {cohort.cohort_id} statistics report",
        ),
        periods_per_year=_integer(
            payload.get("periods_per_year"),
            f"cohort {cohort.cohort_id} periods_per_year",
            minimum=1,
        ),
        mark_lag_microseconds=mark_lag,
        window_count=window_count,
        test_semantic_sha256=test_hashes,
        total_mark_to_market_pnl_usd=total_pnl,
        state=state,
        reasons=tuple(reasons),
    )


def _verify_attestation_snapshots(
    cohort_id: str,
    *,
    statistics_verification: Any,
    statistics: Any,
    dossier_verification: Any,
    dossier: Any,
    quorum_verification: Any,
    quorum: Any,
) -> None:
    if (
        statistics_verification.report_id != statistics.report_id
        or statistics_verification.report_sha256 != statistics.source_sha256
        or statistics_verification.matrix_sha256 != statistics.matrix_sha256
    ):
        raise ValueError(f"cohort {cohort_id} statistics attestation drift")
    if (
        dossier_verification.dossier_id != dossier.dossier.dossier_id
        or dossier_verification.dossier_sha256 != dossier.source_sha256
        or dossier_verification.matrix_sha256 != dossier.dossier.matrix_sha256
    ):
        raise ValueError(f"cohort {cohort_id} dossier attestation drift")
    if (
        quorum_verification.envelope_id != quorum.envelope.envelope_id
        or quorum_verification.envelope_sha256 != quorum.source_sha256
        or quorum_verification.dossier_id != quorum.envelope.dossier_id
        or quorum_verification.requested_candidate_id
        != quorum.envelope.requested_candidate_id
        or quorum_verification.status != quorum.envelope.status
    ):
        raise ValueError(f"cohort {cohort_id} quorum attestation drift")


def _verify_evidence_chain(
    plan_snapshot: ReplicationPlanSnapshot,
    cohort_id: str,
    *,
    statistics: Any,
    dossier: Any,
    quorum: Any,
) -> None:
    dossier_value = dossier.dossier
    quorum_value = quorum.envelope
    statistics_payload = statistics.payload
    if dossier_value.statistics["report_id"] != statistics.report_id:
        raise ValueError(f"cohort {cohort_id} dossier statistics report_id drift")
    if dossier_value.statistics["sha256"] != statistics.source_sha256:
        raise ValueError(f"cohort {cohort_id} dossier statistics SHA-256 drift")
    if dossier_value.matrix_sha256 != statistics.matrix_sha256:
        raise ValueError(f"cohort {cohort_id} dossier matrix drift")
    if dossier_value.code_revision != _required_string(
        statistics_payload,
        "code_revision",
        f"cohort {cohort_id} statistics report",
    ):
        raise ValueError(f"cohort {cohort_id} code revision drift")
    if dossier_value.package_version != _required_string(
        statistics_payload,
        "package_version",
        f"cohort {cohort_id} statistics report",
    ):
        raise ValueError(f"cohort {cohort_id} package version drift")
    candidate_id = plan_snapshot.plan.candidate.candidate_id
    if (
        candidate_id not in dossier_value.eligible_candidate_ids
        or candidate_id in dossier_value.blocked_candidate_ids
    ):
        raise ValueError(f"cohort {cohort_id} candidate is not dossier-eligible")
    if quorum_value.dossier_id != dossier_value.dossier_id:
        raise ValueError(f"cohort {cohort_id} quorum dossier_id drift")
    if quorum_value.dossier_sha256 != dossier.source_sha256:
        raise ValueError(f"cohort {cohort_id} quorum dossier SHA-256 drift")
    if quorum_value.requested_candidate_id != candidate_id:
        raise ValueError(f"cohort {cohort_id} quorum candidate drift")


def _statistics_candidate(
    payload: Mapping[str, Any],
    candidate_id: str,
    candidate_config_sha256: str,
) -> dict[str, Any]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("statistics report candidates must be a list")
    matches: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError("statistics report candidate must be an object")
        candidate = cast(dict[str, Any], item)
        if candidate.get("candidate_id") == candidate_id:
            matches.append(candidate)
    if len(matches) != 1:
        raise ValueError(
            f"statistics report must contain exactly one candidate {candidate_id}"
        )
    candidate = matches[0]
    if set(candidate) != _CANDIDATE_FIELDS:
        raise ValueError("statistics report candidate contains unknown or missing fields")
    if candidate.get("candidate_config_sha256") != candidate_config_sha256:
        raise ValueError("statistics report candidate configuration SHA-256 drift")
    if candidate.get("coverage") != "complete":
        raise ValueError("statistics report candidate coverage must be complete")
    return candidate


def _candidate_observations(
    candidate: Mapping[str, Any],
    *,
    candidate_id: str,
    candidate_config_sha256: str,
    mark_lag_microseconds: int,
    cohort_id: str,
) -> tuple[str, ...]:
    observations = candidate.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError(f"cohort {cohort_id} observations must be non-empty")
    expected = _integer(
        candidate.get("expected_evaluation_count"),
        f"cohort {cohort_id} expected_evaluation_count",
        minimum=1,
    )
    observed = _integer(
        candidate.get("observed_evaluation_count"),
        f"cohort {cohort_id} observed_evaluation_count",
        minimum=1,
    )
    if expected != observed or observed != len(observations):
        raise ValueError(f"cohort {cohort_id} candidate coverage counts drift")

    hashes: list[str] = []
    previous_window = -1
    for index, item in enumerate(observations):
        if not isinstance(item, dict):
            raise ValueError(f"cohort {cohort_id} observation {index} must be an object")
        observation = cast(dict[str, Any], item)
        if set(observation) != _OBSERVATION_FIELDS:
            raise ValueError(
                f"cohort {cohort_id} observation {index} has unknown or missing fields"
            )
        if observation.get("candidate_id") != candidate_id:
            raise ValueError(f"cohort {cohort_id} observation candidate drift")
        if observation.get("candidate_config_sha256") != candidate_config_sha256:
            raise ValueError(f"cohort {cohort_id} observation configuration drift")
        if _integer(
            observation.get("mark_lag_microseconds"),
            f"cohort {cohort_id} observation mark lag",
            minimum=0,
        ) != mark_lag_microseconds:
            raise ValueError(f"cohort {cohort_id} observation mark-lag drift")
        window_index = _integer(
            observation.get("window_index"),
            f"cohort {cohort_id} observation window_index",
            minimum=0,
        )
        if window_index <= previous_window:
            raise ValueError(f"cohort {cohort_id} observations must be chronological")
        previous_window = window_index
        digest = _required_digest(
            observation,
            "test_semantic_sha256",
            f"cohort {cohort_id} observation",
        )
        if digest in hashes:
            raise ValueError(f"cohort {cohort_id} repeats a test semantic hash")
        hashes.append(digest)
    return tuple(hashes)


def _independence_checks(
    plan_snapshot: ReplicationPlanSnapshot,
    cohorts: tuple[ReplicationCohortEvidence, ...],
) -> tuple[tuple[str, bool], ...]:
    policy = plan_snapshot.plan.independence
    all_test_hashes = [set(cohort.test_semantic_sha256) for cohort in cohorts]
    disjoint = True
    seen: set[str] = set()
    for hashes in all_test_hashes:
        if seen & hashes:
            disjoint = False
        seen.update(hashes)
    checks = {
        "minimum_replications": len(cohorts) >= policy.minimum_replications,
        "minimum_distinct_quorum_signers": (
            len({cohort.quorum_signer_key_id for cohort in cohorts})
            >= policy.minimum_distinct_quorum_signers
        ),
        "minimum_distinct_dossier_signers": (
            len({cohort.dossier_signer_key_id for cohort in cohorts})
            >= policy.minimum_distinct_dossier_signers
        ),
        "minimum_distinct_statistics_signers": (
            len({cohort.statistics_signer_key_id for cohort in cohorts})
            >= policy.minimum_distinct_statistics_signers
        ),
        "disjoint_test_semantic_sha256": disjoint,
        "distinct_matrix_sha256": (
            len({cohort.matrix_sha256 for cohort in cohorts}) == len(cohorts)
        ),
        "distinct_dossier_sha256": (
            len({cohort.dossier_sha256 for cohort in cohorts}) == len(cohorts)
        ),
        "distinct_quorum_envelope_sha256": (
            len({cohort.quorum_envelope_sha256 for cohort in cohorts})
            == len(cohorts)
        ),
        "statistics_report_reuse_prohibited": (
            len({cohort.statistics_report_sha256 for cohort in cohorts})
            == len(cohorts)
        ),
    }
    return _sorted_checks(checks)


def _comparability_checks(
    cohorts: tuple[ReplicationCohortEvidence, ...],
) -> tuple[tuple[str, bool], ...]:
    return _sorted_checks(
        {
            "equal_code_revision": (
                len({cohort.code_revision for cohort in cohorts}) == 1
            ),
            "equal_package_version": (
                len({cohort.package_version for cohort in cohorts}) == 1
            ),
            "equal_periods_per_year": (
                len({cohort.periods_per_year for cohort in cohorts}) == 1
            ),
            "equal_terminal_mark_lag": (
                len({cohort.mark_lag_microseconds for cohort in cohorts}) == 1
            ),
        }
    )


def _sorted_checks(values: Mapping[str, bool]) -> tuple[tuple[str, bool], ...]:
    return tuple(sorted(values.items()))


def _checks_pass(values: tuple[tuple[str, bool], ...]) -> bool:
    return all(value for _, value in values)


def _fraction(numerator: int, denominator: int) -> Decimal:
    if denominator < 1:
        raise ValueError("replication fraction denominator must be positive")
    return Decimal(numerator) / Decimal(denominator)


def _median_decimal(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise ValueError("replication median requires at least one value")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _required_string(payload: Mapping[str, Any], key: str, name: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name}.{key} must be a non-empty string")
    return value


def _required_digest(payload: Mapping[str, Any], key: str, name: str) -> str:
    value = _required_string(payload, key, name)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name}.{key} must be 64 lowercase hex characters")
    return value


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return int(value)


def _decimal_string(value: object, name: str) -> Decimal:
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
