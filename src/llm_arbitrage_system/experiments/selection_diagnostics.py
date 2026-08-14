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
    load_selection_policy,
)
from llm_arbitrage_system.experiments.statistics_signing import (
    StatisticsReportSnapshot,
    load_statistics_report,
)

_SCHEMA_VERSION = 1
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

    def identity(self) -> tuple[int, int, int]:
        return self.window_index, self.test_start, self.test_end


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    candidate_id: str
    candidate_config_sha256: str
    coverage: str
    expected_evaluation_count: int
    observed_evaluation_count: int
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
            "total_mark_to_market_pnl_usd": _text(
                self.total_mark_to_market_pnl_usd
            ),
            "positive_window_fraction": _text(self.positive_window_fraction),
            "worst_window_pnl_usd": _text(self.worst_window_pnl_usd),
            "median_window_pnl_usd": _text(self.median_window_pnl_usd),
            "leave_one_out_total_pnl_min_usd": _text(
                self.leave_one_out_total_pnl_min_usd
            ),
            "leave_one_out_total_pnl_max_usd": _text(
                self.leave_one_out_total_pnl_max_usd
            ),
            "maximum_drawdown_pct": _text(self.maximum_drawdown_pct),
            "annualized_sharpe_ratio": _optional_text(
                self.annualized_sharpe_ratio
            ),
            "alpha_decay_bps_per_window": _optional_text(
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
            "raw_two_sided_sign_p_value": _text(
                self.raw_two_sided_sign_p_value
            ),
            "holm_adjusted_p_value": _text(self.holm_adjusted_p_value),
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
            "schema_version": _SCHEMA_VERSION,
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
                "family_alpha": _text(self.family_alpha),
            },
            "candidates": [item.as_dict() for item in self.candidates],
            "pairwise": [item.as_dict() for item in self.pairwise],
            "selection": None,
            "ranking": None,
            "promotion": None,
            "assumptions": [
                "Candidate order is lexical by candidate_id, never performance-ranked.",
                (
                    "Pairwise p-values use exact two-sided sign tests over matching "
                    "terminal OOS windows and ignore tied differences."
                ),
                (
                    "Holm adjustment applies only to the captured candidate family and "
                    "does not prove causal alpha."
                ),
                (
                    "Eligibility means structurally admissible for human review, not "
                    "selected, approved, or deployable."
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
    revision = _revision(code_revision)
    policy_snapshot = load_selection_policy(policy_path)
    statistics = load_statistics_report(statistics_report_path)
    policy = policy_snapshot.policy
    if statistics.matrix_sha256 != policy.matrix_sha256:
        raise ValueError("selection policy matrix does not match statistics report")

    evidence = _read_candidates(statistics)
    global_blockers = _family_blockers(policy, evidence)
    pairwise = _pairwise(policy, evidence, global_blockers)
    candidates = _candidate_results(policy, evidence, pairwise)
    family_state = (
        "eligible_for_human_review"
        if not global_blockers
        and any(item.status == "eligible_for_human_review" for item in candidates)
        else "blocked"
    )
    version = package_version or installed_package_version()
    identity = {
        "schema_version": _SCHEMA_VERSION,
        "policy_id": policy_snapshot.policy_id,
        "policy_sha256": policy_snapshot.canonical_sha256,
        "statistics_report_id": statistics.report_id,
        "statistics_report_sha256": statistics.source_sha256,
        "matrix_sha256": statistics.matrix_sha256,
        "code_revision": revision,
        "package_version": version,
        "family_state": family_state,
        "global_blockers": list(global_blockers),
        "family_alpha": _text(policy.multiple_testing.family_alpha),
        "candidates": [item.as_dict() for item in candidates],
        "pairwise": [item.as_dict() for item in pairwise],
    }
    diagnostics_id = "selection-diagnostics-" + sha256_hex(
        canonical_json_bytes(identity)
    )[:40]
    return SelectionDiagnosticsReport(
        diagnostics_id=diagnostics_id,
        policy_id=policy_snapshot.policy_id,
        policy_sha256=policy_snapshot.canonical_sha256,
        statistics_report_id=statistics.report_id,
        statistics_report_sha256=statistics.source_sha256,
        matrix_sha256=statistics.matrix_sha256,
        code_revision=revision,
        package_version=version,
        family_state=family_state,
        global_blockers=global_blockers,
        family_alpha=policy.multiple_testing.family_alpha,
        candidates=candidates,
        pairwise=pairwise,
    )


def _read_candidates(
    statistics: StatisticsReportSnapshot,
) -> tuple[CandidateEvidence, ...]:
    raw = statistics.payload.get("candidates")
    if not isinstance(raw, list) or not raw:
        raise ValueError("statistics report candidates must be a non-empty list")
    result: list[CandidateEvidence] = []
    seen: set[str] = set()
    for position, value in enumerate(raw):
        payload = _object(value, f"candidate {position}")
        if set(payload) != _CANDIDATE_FIELDS:
            raise ValueError(f"candidate {position} contains unknown or missing fields")
        candidate_id = _string(payload.get("candidate_id"), "candidate_id")
        if candidate_id in seen:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        config_sha = _digest(
            payload.get("candidate_config_sha256"),
            f"candidate {candidate_id} config hash",
        )
        windows = _read_windows(candidate_id, config_sha, payload)
        expected = _integer(
            payload.get("expected_evaluation_count"),
            f"candidate {candidate_id} expected count",
            minimum=1,
        )
        observed = _integer(
            payload.get("observed_evaluation_count"),
            f"candidate {candidate_id} observed count",
            minimum=1,
        )
        if observed != len(windows):
            raise ValueError(
                f"candidate {candidate_id} observed count does not match observations"
            )
        initial = _decimal_string(
            payload.get("initial_equity_usd"),
            f"candidate {candidate_id} initial equity",
        )
        ending = _decimal_string(
            payload.get("ending_equity_usd"),
            f"candidate {candidate_id} ending equity",
        )
        total = _decimal_string(
            payload.get("total_mark_to_market_pnl_usd"),
            f"candidate {candidate_id} total PnL",
        )
        observed_total = sum(
            (item.mark_to_market_pnl_usd for item in windows),
            Decimal("0"),
        )
        if observed_total != total:
            raise ValueError(f"candidate {candidate_id} total PnL does not match windows")
        if initial + total != ending:
            raise ValueError(
                f"candidate {candidate_id} ending equity does not match accounting"
            )
        lag = _integer(
            payload.get("mark_lag_microseconds"),
            f"candidate {candidate_id} mark lag",
            minimum=0,
        )
        if any(item.mark_lag_microseconds != lag for item in windows):
            raise ValueError(f"candidate {candidate_id} contains inconsistent mark lags")
        result.append(
            CandidateEvidence(
                candidate_id=candidate_id,
                candidate_config_sha256=config_sha,
                coverage=_string(payload.get("coverage"), "coverage"),
                expected_evaluation_count=expected,
                observed_evaluation_count=observed,
                total_mark_to_market_pnl_usd=total,
                maximum_drawdown_pct=_number(
                    payload.get("maximum_drawdown_pct"),
                    f"candidate {candidate_id} maximum drawdown",
                ),
                annualized_sharpe_ratio=_optional_number(
                    payload.get("annualized_sharpe_ratio"),
                    f"candidate {candidate_id} Sharpe",
                ),
                alpha_decay_bps_per_window=_optional_decimal_string(
                    payload.get("alpha_decay_bps_per_window"),
                    f"candidate {candidate_id} alpha decay",
                ),
                mark_lag_microseconds=lag,
                windows=windows,
            )
        )
    return tuple(sorted(result, key=lambda item: item.candidate_id))


def _read_windows(
    candidate_id: str,
    config_sha: str,
    candidate: Mapping[str, Any],
) -> tuple[CandidateWindowEvidence, ...]:
    raw = candidate.get("observations")
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"candidate {candidate_id} observations must be non-empty")
    result: list[CandidateWindowEvidence] = []
    previous = -1
    for position, value in enumerate(raw):
        payload = _object(value, f"candidate {candidate_id} observation {position}")
        if set(payload) != _OBSERVATION_FIELDS:
            raise ValueError(
                f"candidate {candidate_id} observation {position} has invalid fields"
            )
        if payload.get("candidate_id") != candidate_id:
            raise ValueError(f"candidate {candidate_id} observation candidate drift")
        if payload.get("candidate_config_sha256") != config_sha:
            raise ValueError(f"candidate {candidate_id} observation config drift")
        index = _integer(
            payload.get("window_index"),
            f"candidate {candidate_id} window index",
            minimum=0,
        )
        if index <= previous:
            raise ValueError(
                f"candidate {candidate_id} window indexes must be increasing"
            )
        previous = index
        test_start = _integer(
            payload.get("test_start"),
            f"candidate {candidate_id} test_start",
            minimum=0,
        )
        test_end = _integer(
            payload.get("test_end"),
            f"candidate {candidate_id} test_end",
            minimum=1,
        )
        if test_end <= test_start:
            raise ValueError(f"candidate {candidate_id} test interval is invalid")
        _digest(payload.get("test_semantic_sha256"), "test semantic hash")
        _string(payload.get("evaluation_id"), "evaluation_id")
        _string(payload.get("experiment_id"), "experiment_id")
        _string(payload.get("valuation_id"), "valuation_id")
        _decimal_string(payload.get("ending_equity_usd"), "ending equity")
        _optional_number(payload.get("period_return"), "period return")
        result.append(
            CandidateWindowEvidence(
                window_index=index,
                test_start=test_start,
                test_end=test_end,
                mark_lag_microseconds=_integer(
                    payload.get("mark_lag_microseconds"),
                    "observation mark lag",
                    minimum=0,
                ),
                mark_to_market_pnl_usd=_decimal_string(
                    payload.get("mark_to_market_pnl_usd"),
                    "observation PnL",
                ),
            )
        )
    return tuple(result)


def _family_blockers(
    policy: SelectionPolicy,
    evidence: Sequence[CandidateEvidence],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if len(evidence) < policy.admission.minimum_candidates:
        blockers.append("insufficient_candidate_count")
    if not evidence:
        return tuple(blockers)
    reference = evidence[0]
    reference_indexes = tuple(item.window_index for item in reference.windows)
    reference_intervals = tuple(item.identity() for item in reference.windows)
    if policy.admission.require_equal_window_indexes and any(
        tuple(item.window_index for item in candidate.windows) != reference_indexes
        for candidate in evidence[1:]
    ):
        blockers.append("unequal_window_indexes")
    if policy.admission.require_equal_test_intervals and any(
        tuple(item.identity() for item in candidate.windows) != reference_intervals
        for candidate in evidence[1:]
    ):
        blockers.append("unequal_test_intervals")
    if policy.admission.require_equal_mark_lag and any(
        candidate.mark_lag_microseconds != reference.mark_lag_microseconds
        for candidate in evidence[1:]
    ):
        blockers.append("unequal_mark_lag")
    return tuple(blockers)


def _candidate_results(
    policy: SelectionPolicy,
    evidence: Sequence[CandidateEvidence],
    pairwise: Sequence[PairwiseSelectionDiagnostic],
) -> tuple[CandidateSelectionDiagnostic, ...]:
    admitted_by_pairwise = _significant_candidates(pairwise)
    result: list[CandidateSelectionDiagnostic] = []
    for candidate in evidence:
        values = tuple(item.mark_to_market_pnl_usd for item in candidate.windows)
        positive_fraction = Decimal(sum(value > 0 for value in values)) / Decimal(
            len(values)
        )
        blockers: list[str] = []
        if policy.admission.require_complete_coverage and candidate.coverage != "complete":
            blockers.append("incomplete_coverage")
        if (
            policy.admission.require_complete_coverage
            and candidate.expected_evaluation_count
            != candidate.observed_evaluation_count
        ):
            blockers.append("evaluation_count_mismatch")
        if len(values) < policy.admission.minimum_windows_per_candidate:
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
            and candidate.candidate_id not in admitted_by_pairwise
        ):
            blockers.append("adjusted_pairwise_evidence_unavailable")
        leave_one_out = tuple(
            candidate.total_mark_to_market_pnl_usd - value for value in values
        )
        result.append(
            CandidateSelectionDiagnostic(
                candidate_id=candidate.candidate_id,
                candidate_config_sha256=candidate.candidate_config_sha256,
                status="eligible_for_human_review" if not blockers else "blocked",
                blockers=tuple(blockers),
                window_count=len(values),
                total_mark_to_market_pnl_usd=(
                    candidate.total_mark_to_market_pnl_usd
                ),
                positive_window_fraction=positive_fraction,
                worst_window_pnl_usd=min(values),
                median_window_pnl_usd=_median(values),
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


def _pairwise(
    policy: SelectionPolicy,
    evidence: Sequence[CandidateEvidence],
    blockers: Sequence[str],
) -> tuple[PairwiseSelectionDiagnostic, ...]:
    if set(blockers) & {
        "unequal_window_indexes",
        "unequal_test_intervals",
        "unequal_mark_lag",
    }:
        return ()
    drafts: list[tuple[str, str, int, int, int, Decimal]] = []
    for left, right in combinations(evidence, 2):
        if len(left.windows) != len(right.windows):
            raise ValueError("pairwise candidates contain different window counts")
        differences = tuple(
            left_item.mark_to_market_pnl_usd
            - right_item.mark_to_market_pnl_usd
            for left_item, right_item in zip(
                left.windows,
                right.windows,
                strict=True,
            )
        )
        left_wins = sum(value > 0 for value in differences)
        right_wins = sum(value < 0 for value in differences)
        raw = _sign_p_value(left_wins, right_wins)
        drafts.append(
            (
                left.candidate_id,
                right.candidate_id,
                len(differences),
                left_wins,
                right_wins,
                raw,
            )
        )
    adjusted = _holm(tuple(item[5] for item in drafts))
    result: list[PairwiseSelectionDiagnostic] = []
    for draft, adjusted_value in zip(drafts, adjusted, strict=True):
        left_id, right_id, count, left_wins, right_wins, raw = draft
        non_tied = left_wins + right_wins
        minimum_satisfied = (
            non_tied
            >= policy.multiple_testing.minimum_non_tied_pairwise_windows
        )
        result.append(
            PairwiseSelectionDiagnostic(
                left_candidate_id=left_id,
                right_candidate_id=right_id,
                compared_window_count=count,
                non_tied_window_count=non_tied,
                left_wins=left_wins,
                right_wins=right_wins,
                ties=count - non_tied,
                raw_two_sided_sign_p_value=raw,
                holm_adjusted_p_value=adjusted_value,
                adjusted_significant=(
                    minimum_satisfied
                    and adjusted_value <= policy.multiple_testing.family_alpha
                ),
                minimum_evidence_satisfied=minimum_satisfied,
            )
        )
    return tuple(result)


def _significant_candidates(
    pairwise: Sequence[PairwiseSelectionDiagnostic],
) -> set[str]:
    result: set[str] = set()
    for item in pairwise:
        if not item.adjusted_significant:
            continue
        if item.left_wins > item.right_wins:
            result.add(item.left_candidate_id)
        elif item.right_wins > item.left_wins:
            result.add(item.right_candidate_id)
    return result


def _sign_p_value(wins: int, losses: int) -> Decimal:
    count = wins + losses
    if count == 0:
        return Decimal("1")
    tail = sum(comb(count, index) for index in range(min(wins, losses) + 1))
    return min(Decimal("1"), Decimal(2 * tail) / Decimal(2**count))


def _holm(values: Sequence[Decimal]) -> tuple[Decimal, ...]:
    if not values:
        return ()
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    result = [Decimal("1")] * len(values)
    running = Decimal("0")
    for rank, (original, value) in enumerate(ordered):
        adjusted = min(Decimal("1"), value * Decimal(len(values) - rank))
        running = max(running, adjusted)
        result[original] = running
    return tuple(result)


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / Decimal("2")


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return cast(Mapping[str, Any], value)


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _digest(value: Any, name: str) -> str:
    result = _string(value, name)
    if len(result) != 64 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
    return result


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _decimal_string(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a decimal string")
    return _parse_decimal(value, name)


def _optional_decimal_string(value: Any, name: str) -> Decimal | None:
    return None if value is None else _decimal_string(value, name)


def _number(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite JSON number")
    return _parse_decimal(str(value), name)


def _optional_number(value: Any, name: str) -> Decimal | None:
    return None if value is None else _number(value, name)


def _parse_decimal(value: str, name: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} is not a valid decimal") from error
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def _optional_text(value: Decimal | None) -> str | None:
    return None if value is None else _text(value)


def _text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _revision(value: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError("code_revision cannot be empty")
    if len(result) > 160:
        raise ValueError("code_revision is too long")
    return result
