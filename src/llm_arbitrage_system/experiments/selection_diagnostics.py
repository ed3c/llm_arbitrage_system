from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import combinations
from math import comb
from pathlib import Path
from typing import Any, cast

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.manifest import installed_package_version
from llm_arbitrage_system.experiments.selection_policy import (
    SelectionPolicy,
    SelectionPolicySnapshot,
    load_selection_policy,
)
from llm_arbitrage_system.experiments.statistics_signing import (
    StatisticsReportSnapshot,
    load_statistics_report,
)

_DIAGNOSTICS_SCHEMA_VERSION = 1
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
class CandidateWindowEvidence:
    window_index: int
    test_start: int
    test_end: int
    mark_lag_microseconds: int
    mark_to_market_pnl_usd: Decimal

    def identity_tuple(self) -> tuple[int, int, int]:
        return (self.window_index, self.test_start, self.test_end)


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    candidate_id: str
    candidate_config_sha256: str
    coverage: str
    expected_evaluation_count: int
    observed_evaluation_count: int
    initial_equity_usd: Decimal
    ending_equity_usd: Decimal
    total_mark_to_market_pnl_usd: Decimal
    maximum_drawdown_pct: Decimal
    annualized_sharpe_ratio: Decimal | None
    alpha_decay_bps_per_window: Decimal | None
    mark_lag_microseconds: int
    windows: tuple[CandidateWindowEvidence, ...]


@dataclass(frozen=True, slots=True)
class CandidateSelectionDiagnostic:
    candidate_id: str
    candidate_config_sha256: str
    status: str
    blockers: tuple[str, ...]
    window_count: int
    total_mark_to_market_pnl_usd: Decimal
    positive_window_fraction: Decimal
    worst_window_pnl_usd: Decimal
    median_window_pnl_usd: Decimal
    leave_one_out_total_pnl_min_usd: Decimal
    leave_one_out_total_pnl_max_usd: Decimal
    maximum_drawdown_pct: Decimal
    annualized_sharpe_ratio: Decimal | None
    alpha_decay_bps_per_window: Decimal | None
    mark_lag_microseconds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "status": self.status,
            "blockers": list(self.blockers),
            "window_count": self.window_count,
            "total_mark_to_market_pnl_usd": _decimal_text(
                self.total_mark_to_market_pnl_usd
            ),
            "positive_window_fraction": _decimal_text(
                self.positive_window_fraction
            ),
            "worst_window_pnl_usd": _decimal_text(self.worst_window_pnl_usd),
            "median_window_pnl_usd": _decimal_text(self.median_window_pnl_usd),
            "leave_one_out_total_pnl_min_usd": _decimal_text(
                self.leave_one_out_total_pnl_min_usd
            ),
            "leave_one_out_total_pnl_max_usd": _decimal_text(
                self.leave_one_out_total_pnl_max_usd
            ),
            "maximum_drawdown_pct": _decimal_text(self.maximum_drawdown_pct),
            "annualized_sharpe_ratio": _optional_decimal_text(
                self.annualized_sharpe_ratio
            ),
            "alpha_decay_bps_per_window": _optional_decimal_text(
                self.alpha_decay_bps_per_window
            ),
            "mark_lag_microseconds": self.mark_lag_microseconds,
        }


@dataclass(frozen=True, slots=True)
class PairwiseSelectionDiagnostic:
    left_candidate_id: str
    right_candidate_id: str
    compared_window_count: int
    non_tied_window_count: int
    left_wins: int
    right_wins: int
    ties: int
    raw_two_sided_sign_p_value: Decimal
    holm_adjusted_p_value: Decimal
    adjusted_significant: bool
    minimum_evidence_satisfied: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "left_candidate_id": self.left_candidate_id,
            "right_candidate_id": self.right_candidate_id,
            "compared_window_count": self.compared_window_count,
            "non_tied_window_count": self.non_tied_window_count,
            "left_wins": self.left_wins,
            "right_wins": self.right_wins,
            "ties": self.ties,
            "raw_two_sided_sign_p_value": _decimal_text(
                self.raw_two_sided_sign_p_value
            ),
            "holm_adjusted_p_value": _decimal_text(
                self.holm_adjusted_p_value
            ),
            "adjusted_significant": self.adjusted_significant,
            "minimum_evidence_satisfied": self.minimum_evidence_satisfied,
        }


@dataclass(frozen=True, slots=True)
class SelectionDiagnosticsReport:
    diagnostics_id: str
    policy_id: str
    policy_sha256: str
    statistics_report_id: str
    statistics_report_sha256: str
    matrix_sha256: str
    code_revision: str
    package_version: str
    family_state: str
    global_blockers: tuple[str, ...]
    family_alpha: Decimal
    candidates: tuple[CandidateSelectionDiagnostic, ...]
    pairwise: tuple[PairwiseSelectionDiagnostic, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _DIAGNOSTICS_SCHEMA_VERSION,
            "diagnostics_id": self.diagnostics_id,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "statistics_report_id": self.statistics_report_id,
            "statistics_report_sha256": self.statistics_report_sha256,
            "matrix_sha256": self.matrix_sha256,
            "code_revision": self.code_revision,
            "package_version": self.package_version,
            "family_state": self.family_state,
            "global_blockers": list(self.global_blockers),
            "family": {
                "candidate_count": len(self.candidates),
                "pairwise_comparison_count": len(self.pairwise),
                "multiple_testing_method": "holm_sign_test",
                "family_alpha": _decimal_text(self.family_alpha),
            },
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "pairwise": [comparison.as_dict() for comparison in self.pairwise],
            "selection": None,
            "ranking": None,
            "promotion": None,
            "assumptions": [
                (
                    "Candidate order is lexical by candidate_id and never performance-"
                    "ranked."
                ),
                (
                    "Pairwise p-values use an exact two-sided sign test over matching "
                    "terminal OOS windows and ignore tied differences."
                ),
                (
                    "Holm adjustment controls the declared family alpha only for the "
                    "captured candidate family; it does not prove causal alpha."
                ),
                (
                    "Eligibility means evidence is structurally admissible for human "
                    "review, not that a candidate should be selected or deployed."
                ),
            ],
            "evidence_boundary": (
                "This report is conditional on one preregistered policy and one canonical "
                "Phase 6 OOS report derived from trusted paper evidence and caller-"
                "supplied terminal marks. It does not establish source-market truth, "
                "live realized profit, causal alpha, future returns, approval, release, "
                "or production readiness."
            ),
        }


def build_selection_diagnostics(
    *,
    policy_path: Path,
    statistics_report_path: Path,
    code_revision: str,
    package_version: str | None = None,
) -> SelectionDiagnosticsReport:
    normalized_revision = _normalized_revision(code_revision)
    policy_snapshot = load_selection_policy(policy_path)
    statistics_snapshot = load_statistics_report(statistics_report_path)
    if statistics_snapshot.matrix_sha256 != policy_snapshot.policy.matrix_sha256:
        raise ValueError("selection policy matrix does not match statistics report")

    evidence = _candidate_evidence(statistics_snapshot)
    global_blockers = _global_blockers(policy_snapshot.policy, evidence)
    pairwise = _pairwise_diagnostics(policy_snapshot.policy, evidence, global_blockers)
    candidate_diagnostics = _candidate_diagnostics(
        policy_snapshot.policy,
        evidence,
        pairwise,
    )
    family_state = (
        "eligible_for_human_review"
        if not global_blockers
        and any(item.status == "eligible_for_human_review" for item in candidate_diagnostics)
        else "blocked"
    )
    resolved_version = package_version or installed_package_version()
    identity = {
        "schema_version": _DIAGNOSTICS_SCHEMA_VERSION,
        "policy_id": policy_snapshot.policy_id,
        "policy_sha256": policy_snapshot.canonical_sha256,
        "statistics_report_id": statistics_snapshot.report_id,
        "statistics_report_sha256": statistics_snapshot.source_sha256,
        "matrix_sha256": statistics_snapshot.matrix_sha256,
        "code_revision": normalized_revision,
        "package_version": resolved_version,
        "family_state": family_state,
        "global_blockers": list(global_blockers),
        "family_alpha": _decimal_text(
            policy_snapshot.policy.multiple_testing.family_alpha
        ),
        "candidates": [item.as_dict() for item in candidate_diagnostics],
        "pairwise": [item.as_dict() for item in pairwise],
    }
    diagnostics_id = (
        "selection-diagnostics-"
        + sha256_hex(canonical_json_bytes(identity))[:40]
    )
    return SelectionDiagnosticsReport(
        diagnostics_id=diagnostics_id,
        policy_id=policy_snapshot.policy_id,
        policy_sha256=policy_snapshot.canonical_sha256,
        statistics_report_id=statistics_snapshot.report_id,
        statistics_report_sha256=statistics_snapshot.source_sha256,
        matrix_sha256=statistics_snapshot.matrix_sha256,
        code_revision=normalized_revision,
        package_version=resolved_version,
        family_state=family_state,
        global_blockers=global_blockers,
        family_alpha=policy_snapshot.policy.multiple_testing.family_alpha,
        candidates=candidate_diagnostics,
        pairwise=pairwise,
    )


def _candidate_evidence(
    report: StatisticsReportSnapshot,
) -> tuple[CandidateEvidence, ...]:
    raw_candidates = report.payload.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError("statistics report candidates must be a non-empty list")
    result: list[CandidateEvidence] = []
    seen: set[str] = set()
    for index, raw_candidate in enumerate(raw_candidates):
        candidate = _mapping(raw_candidate, f"candidate {index}")
        if set(candidate) != _CANDIDATE_FIELDS:
            raise ValueError(f"candidate {index} contains unknown or missing fields")
        candidate_id = _required_string(
            candidate.get("candidate_id"),
            f"candidate {index}.candidate_id",
        )
        if candidate_id in seen:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        config_sha = _required_digest(
            candidate.get("candidate_config_sha256"),
            f"candidate {candidate_id}.candidate_config_sha256",
        )
        expected_count = _integer(
            candidate.get("expected_evaluation_count"),
            f"candidate {candidate_id}.expected_evaluation_count",
            minimum=1,
        )
        observed_count = _integer(
            candidate.get("observed_evaluation_count"),
            f"candidate {candidate_id}.observed_evaluation_count",
            minimum=1,
        )
        windows = _window_evidence(candidate_id, config_sha, candidate)
        if observed_count != len(windows):
            raise ValueError(
                f"candidate {candidate_id} observed count does not match observations"
            )
        initial_equity = _decimal_text_value(
            candidate.get("initial_equity_usd"),
            f"candidate {candidate_id}.initial_equity_usd",
        )
        ending_equity = _decimal_text_value(
            candidate.get("ending_equity_usd"),
            f"candidate {candidate_id}.ending_equity_usd",
        )
        total_pnl = _decimal_text_value(
            candidate.get("total_mark_to_market_pnl_usd"),
            f"candidate {candidate_id}.total_mark_to_market_pnl_usd",
        )
        observed_total = sum(
            (window.mark_to_market_pnl_usd for window in windows),
            Decimal("0"),
        )
        if observed_total != total_pnl:
            raise ValueError(f"candidate {candidate_id} total PnL does not match windows")
        if initial_equity + total_pnl != ending_equity:
            raise ValueError(
                f"candidate {candidate_id} ending equity does not match initial equity and PnL"
            )
        mark_lag = _integer(
            candidate.get("mark_lag_microseconds"),
            f"candidate {candidate_id}.mark_lag_microseconds",
            minimum=0,
        )
        if any(window.mark_lag_microseconds != mark_lag for window in windows):
            raise ValueError(f"candidate {candidate_id} contains inconsistent mark lags")
        result.append(
            CandidateEvidence(
                candidate_id=candidate_id,
                candidate_config_sha256=config_sha,
                coverage=_required_string(
                    candidate.get("coverage"),
                    f"candidate {candidate_id}.coverage",
                ),
                expected_evaluation_count=expected_count,
                observed_evaluation_count=observed_count,
                initial_equity_usd=initial_equity,
                ending_equity_usd=ending_equity,
                total_mark_to_market_pnl_usd=total_pnl,
                maximum_drawdown_pct=_number_decimal(
                    candidate.get("maximum_drawdown_pct"),
                    f"candidate {candidate_id}.maximum_drawdown_pct",
                ),
                annualized_sharpe_ratio=_optional_number_decimal(
                    candidate.get("annualized_sharpe_ratio"),
                    f"candidate {candidate_id}.annualized_sharpe_ratio",
                ),
                alpha_decay_bps_per_window=_optional_decimal_text_value(
                    candidate.get("alpha_decay_bps_per_window"),
                    f"candidate {candidate_id}.alpha_decay_bps_per_window",
                ),
                mark_lag_microseconds=mark_lag,
                windows=windows,
            )
        )
    return tuple(sorted(result, key=lambda item: item.candidate_id))


def _window_evidence(
    candidate_id: str,
    config_sha: str,
    candidate: Mapping[str, Any],
) -> tuple[CandidateWindowEvidence, ...]:
    raw_observations = candidate.get("observations")
    if not isinstance(raw_observations, list) or not raw_observations:
        raise ValueError(f"candidate {candidate_id} observations must be non-empty")
    result: list[CandidateWindowEvidence] = []
    seen_indexes: set[int] = set()
    previous_index = -1
    for index, raw_observation in enumerate(raw_observations):
        observation = _mapping(raw_observation, f"candidate {candidate_id} observation")
        if set(observation) != _OBSERVATION_FIELDS:
            raise ValueError(
                f"candidate {candidate_id} observation {index} has unknown or missing fields"
            )
        if observation.get("candidate_id") != candidate_id:
            raise ValueError(f"candidate {candidate_id} observation candidate_id drift")
        if observation.get("candidate_config_sha256") != config_sha:
            raise ValueError(f"candidate {candidate_id} observation config hash drift")
        window_index = _integer(
            observation.get("window_index"),
            f"candidate {candidate_id} observation.window_index",
            minimum=0,
        )
        if window_index in seen_indexes or window_index <= previous_index:
            raise ValueError(
                f"candidate {candidate_id} window indexes must be unique and increasing"
            )
        seen_indexes.add(window_index)
        previous_index = window_index
        test_start = _integer(
            observation.get("test_start"),
            f"candidate {candidate_id} observation.test_start",
            minimum=0,
        )
        test_end = _integer(
            observation.get("test_end"),
            f"candidate {candidate_id} observation.test_end",
            minimum=1,
        )
        if test_end <= test_start:
            raise ValueError(f"candidate {candidate_id} test interval is invalid")
        _required_digest(
            observation.get("test_semantic_sha256"),
            f"candidate {candidate_id} observation.test_semantic_sha256",
        )
        _required_string(
            observation.get("evaluation_id"),
            f"candidate {candidate_id} observation.evaluation_id",
        )
        _required_string(
            observation.get("experiment_id"),
            f"candidate {candidate_id} observation.experiment_id",
        )
        _required_string(
            observation.get("valuation_id"),
            f"candidate {candidate_id} observation.valuation_id",
        )
        _decimal_text_value(
            observation.get("ending_equity_usd"),
            f"candidate {candidate_id} observation.ending_equity_usd",
        )
        _optional_number_decimal(
            observation.get("period_return"),
            f"candidate {candidate_id} observation.period_return",
        )
        result.append(
            CandidateWindowEvidence(
                window_index=window_index,
                test_start=test_start,
                test_end=test_end,
                mark_lag_microseconds=_integer(
                    observation.get("mark_lag_microseconds"),
                    f"candidate {candidate_id} observation.mark_lag_microseconds",
                    minimum=0,
                ),
                mark_to_market_pnl_usd=_decimal_text_value(
                    observation.get("mark_to_market_pnl_usd"),
                    f"candidate {candidate_id} observation.mark_to_market_pnl_usd",
                ),
            )
        )
    return tuple(result)


def _global_blockers(
    policy: SelectionPolicy,
    evidence: Sequence[CandidateEvidence],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if len(evidence) < policy.admission.minimum_candidates:
        blockers.append("insufficient_candidate_count")
    if not evidence:
        return tuple(blockers)
    reference = evidence[0]
    reference_indexes = tuple(window.window_index for window in reference.windows)
    reference_intervals = tuple(window.identity_tuple() for window in reference.windows)
    reference_lag = reference.mark_lag_microseconds
    if policy.admission.require_equal_window_indexes and any(
        tuple(window.window_index for window in candidate.windows) != reference_indexes
        for candidate in evidence[1:]
    ):
        blockers.append("unequal_window_indexes")
    if policy.admission.require_equal_test_intervals and any(
        tuple(window.identity_tuple() for window in candidate.windows)
        != reference_intervals
        for candidate in evidence[1:]
    ):
        blockers.append("unequal_test_intervals")
    if policy.admission.require_equal_mark_lag and any(
        candidate.mark_lag_microseconds != reference_lag
        for candidate in evidence[1:]
    ):
        blockers.append("unequal_mark_lag")
    return tuple(blockers)


def _candidate_diagnostics(
    policy: SelectionPolicy,
    evidence: Sequence[CandidateEvidence],
    pairwise: Sequence[PairwiseSelectionDiagnostic],
) -> tuple[CandidateSelectionDiagnostic, ...]:
    adjusted_evidence = _adjusted_evidence_candidates(pairwise)
    result: list[CandidateSelectionDiagnostic] = []
    for candidate in evidence:
        pnl_values = tuple(
            window.mark_to_market_pnl_usd for window in candidate.windows
        )
        positive_fraction = Decimal(
            sum(value > 0 for value in pnl_values)
        ) / Decimal(len(pnl_values))
        blockers: list[str] = []
        if (
            policy.admission.require_complete_coverage
            and candidate.coverage != "complete"
        ):
            blockers.append("incomplete_coverage")
        if (
            policy.admission.require_complete_coverage
            and candidate.expected_evaluation_count
            != candidate.observed_evaluation_count
        ):
            blockers.append("evaluation_count_mismatch")
        if len(pnl_values) < policy.admission.minimum_windows_per_candidate:
            blockers.append("insufficient_window_count")
        if candidate.maximum_drawdown_pct > policy.admission.maximum_drawdown_pct:
            blockers.append("maximum_drawdown_exceeded")
        if positive_fraction < policy.admission.minimum_positive_window_fraction:
            blockers.append("positive_window_fraction_below_policy")
        maximum_decay = policy.admission.maximum_alpha_decay_bps_per_window
        if maximum_decay is not None:
            if candidate.alpha_decay_bps_per_window is None:
                blockers.append("alpha_decay_unavailable")
            elif candidate.alpha_decay_bps_per_window > maximum_decay:
                blockers.append("maximum_alpha_decay_exceeded")
        if (
            policy.multiple_testing.require_adjusted_pairwise_evidence
            and candidate.candidate_id not in adjusted_evidence
        ):
            blockers.append("adjusted_pairwise_evidence_unavailable")
        leave_one_out = tuple(
            candidate.total_mark_to_market_pnl_usd - value
            for value in pnl_values
        )
        result.append(
            CandidateSelectionDiagnostic(
                candidate_id=candidate.candidate_id,
                candidate_config_sha256=candidate.candidate_config_sha256,
                status=(
                    "eligible_for_human_review" if not blockers else "blocked"
                ),
                blockers=tuple(blockers),
                window_count=len(pnl_values),
                total_mark_to_market_pnl_usd=(
                    candidate.total_mark_to_market_pnl_usd
                ),
                positive_window_fraction=positive_fraction,
                worst_window_pnl_usd=min(pnl_values),
                median_window_pnl_usd=_median_decimal(pnl_values),
                leave_one_out_total_pnl_min_usd=min(leave_one_out),
                leave_one_out_total_pnl_max_usd=max(leave_one_out),
                maximum_drawdown_pct=candidate.maximum_drawdown_pct,
                annualized_sharpe_ratio=candidate.annualized_sharpe_ratio,
                alpha_decay_bps_per_window=(
                    candidate.alpha_decay_bps_per_window
                ),
                mark_lag_microseconds=candidate.mark_lag_microseconds,
            )
        )
    return tuple(result)


def _pairwise_diagnostics(
    policy: SelectionPolicy,
    evidence: Sequence[CandidateEvidence],
    global_blockers: Sequence[str],
) -> tuple[PairwiseSelectionDiagnostic, ...]:
    if any(
        blocker in global_blockers
        for blocker in (
            "unequal_window_indexes",
            "unequal_test_intervals",
            "unequal_mark_lag",
        )
    ):
        return ()
    drafts: list[tuple[str, str, int, int, int, int, Decimal]] = []
    for left, right in combinations(evidence, 2):
        if len(left.windows) != len(right.windows):
            raise ValueError("pairwise candidates contain different window counts")
        differences = tuple(
            left_window.mark_to_market_pnl_usd
            - right_window.mark_to_market_pnl_usd
            for left_window, right_window in zip(
                left.windows,
                right.windows,
                strict=True,
            )
        )
        left_wins = sum(value > 0 for value in differences)
        right_wins = sum(value < 0 for value in differences)
        ties = len(differences) - left_wins - right_wins
        raw_p_value = _exact_two_sided_sign_p_value(left_wins, right_wins)
        drafts.append(
            (
                left.candidate_id,
                right.candidate_id,
                len(differences),
                left_wins + right_wins,
                left_wins,
                right_wins,
                raw_p_value,
            )
        )
    adjusted = _holm_adjust(tuple(item[6] for item in drafts))
    result: list[PairwiseSelectionDiagnostic] = []
    for draft, adjusted_p_value in zip(drafts, adjusted, strict=True):
        left_id, right_id, window_count, non_tied, left_wins, right_wins, raw = draft
        minimum_satisfied = (
            non_tied
            >= policy.multiple_testing.minimum_non_tied_pairwise_windows
        )
        result.append(
            PairwiseSelectionDiagnostic(
                left_candidate_id=left_id,
                right_candidate_id=right_id,
                compared_window_count=window_count,
                non_tied_window_count=non_tied,
                left_wins=left_wins,
                right_wins=right_wins,
                ties=window_count - non_tied,
                raw_two_sided_sign_p_value=raw,
                holm_adjusted_p_value=adjusted_p_value,
                adjusted_significant=(
                    minimum_satisfied
                    and adjusted_p_value
                    <= policy.multiple_testing.family_alpha
                ),
                minimum_evidence_satisfied=minimum_satisfied,
            )
        )
    return tuple(result)


def _adjusted_evidence_candidates(
    pairwise: Sequence[PairwiseSelectionDiagnostic],
) -> set[str]:
    result: set[str] = set()
    for comparison in pairwise:
        if not comparison.adjusted_significant:
            continue
        if comparison.left_wins > comparison.right_wins:
            result.add(comparison.left_candidate_id)
        elif comparison.right_wins > comparison.left_wins:
            result.add(comparison.right_candidate_id)
    return result


def _exact_two_sided_sign_p_value(wins: int, losses: int) -> Decimal:
    non_tied = wins + losses
    if non_tied == 0:
        return Decimal("1")
    tail = sum(comb(non_tied, index) for index in range(min(wins, losses) + 1))
    value = Decimal(2 * tail) / Decimal(2**non_tied)
    return min(Decimal("1"), value)


def _holm_adjust(values: Sequence[Decimal]) -> tuple[Decimal, ...]:
    if not values:
        return ()
    indexed = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    adjusted: list[Decimal] = [Decimal("1")] * len(values)
    running = Decimal("0")
    count = len(values)
    for rank, (original_index, value) in enumerate(indexed):
        candidate = min(Decimal("1"), value * Decimal(count - rank))
        running = max(running, candidate)
        adjusted[original_index] = running
    return tuple(adjusted)


def _median_decimal(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return cast(Mapping[str, Any], value)


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _required_digest(value: Any, name: str) -> str:
    result = _required_string(value, name)
    if len(result) != 64 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
    return result


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer greater than or equal to {minimum}")
    return int(value)


def _decimal_text_value(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a decimal string")
    return _parse_decimal(value, name)


def _optional_decimal_text_value(value: Any, name: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal_text_value(value, name)


def _number_decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite JSON number")
    return _parse_decimal(str(value), name)


def _optional_number_decimal(value: Any, name: str) -> Decimal | None:
    if value is None:
        return None
    return _number_decimal(value, name)


def _parse_decimal(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} is not a valid decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else _decimal_text(value)


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _normalized_revision(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("code_revision cannot be empty")
    if len(normalized) > 160:
        raise ValueError("code_revision is too long")
    return normalized
