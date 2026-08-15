from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import llm_arbitrage_system.experiments.replication as replication_module
from llm_arbitrage_system.experiments.replication import build_replication_report
from llm_arbitrage_system.experiments.replication_inputs import (
    load_replication_inputs,
)

_CANDIDATE_ID = "candidate-a0c8f92d194d01b5ecaf5dbf"
_CANDIDATE_CONFIG_SHA = (
    "a0c8f92d194d01b5ecaf5dbfa089b2ce230fd3366918a3918943ce005e0c4adc"
)
_CODE_REVISION = "phase9-replication-test"
_PACKAGE_VERSION = "0.1.0"
_MARK_LAG = 60_000_000
_PERIODS_PER_YEAR = 252


def _write_plan(path: Path) -> Path:
    path.write_text(
        f"""schema_version: 1
scope: independent_offline_replication
candidate:
  candidate_id: {_CANDIDATE_ID}
  candidate_config_sha256: {_CANDIDATE_CONFIG_SHA}
independence:
  minimum_replications: 3
  minimum_distinct_quorum_signers: 2
  minimum_distinct_dossier_signers: 2
  minimum_distinct_statistics_signers: 2
  require_disjoint_test_semantic_sha256: true
  require_distinct_matrix_sha256: true
  require_distinct_dossier_sha256: true
  require_distinct_quorum_envelope_sha256: true
  prohibit_statistics_report_reuse: true
comparability:
  require_equal_code_revision: true
  require_equal_package_version: true
  require_equal_periods_per_year: true
  require_equal_terminal_mark_lag: true
acceptance:
  minimum_research_approved_fraction: "0.67"
  minimum_positive_replication_fraction: "0.67"
  minimum_windows_per_replication: 3
  maximum_failed_replications: 1
  maximum_insufficient_replications: 0
  minimum_worst_case_total_pnl_usd: "0"
  minimum_median_total_pnl_usd: "0"
authority:
  human_admit_required: true
  automatic_promotion: false
  release_authorized: false
  deployment_authorized: false
  trading_authorized: false
""",
        encoding="utf-8",
    )
    return path


def _artifact_payload(cohort_directory: str, role: str) -> dict[str, str]:
    return {
        "evidence": f"{cohort_directory}/{role}.json",
        "attestation": f"{cohort_directory}/{role}.attestation.json",
        "trusted_public_key": f"{cohort_directory}/{role}.public.json",
    }


def _create_artifact_files(root: Path, cohort_directory: str) -> None:
    directory = root / cohort_directory
    directory.mkdir(parents=True, exist_ok=True)
    for role in ("statistics", "dossier", "quorum"):
        (directory / f"{role}.json").write_text("{}\n", encoding="utf-8")
        (directory / f"{role}.attestation.json").write_text(
            "{}\n",
            encoding="utf-8",
        )
        (directory / f"{role}.public.json").write_text("{}\n", encoding="utf-8")


def _input_payload(order: tuple[int, ...] = (1, 2, 3)) -> dict[str, Any]:
    cohorts: list[dict[str, Any]] = []
    for index in order:
        cohort_directory = f"cohort-{index}"
        cohorts.append(
            {
                "cohort_id": f"cohort-{index:024x}",
                "statistics": _artifact_payload(cohort_directory, "statistics"),
                "dossier": _artifact_payload(cohort_directory, "dossier"),
                "quorum": _artifact_payload(cohort_directory, "quorum"),
            }
        )
    return {"schema_version": 1, "cohorts": cohorts}


def _write_inputs(
    path: Path,
    *,
    order: tuple[int, ...] = (1, 2, 3),
) -> Path:
    for index in {1, 2, 3}:
        _create_artifact_files(path.parent, f"cohort-{index}")
    path.write_text(
        json.dumps(_input_payload(order), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _cohort_index(path: Path) -> int:
    for part in path.parts:
        if part.startswith("cohort-") and part.removeprefix("cohort-").isdigit():
            return int(part.removeprefix("cohort-"))
    raise AssertionError(f"unable to resolve cohort index from {path}")


def _digest(value: int) -> str:
    return f"{value:064x}"


def _key_id(value: int) -> str:
    return f"ed25519-{value:032x}"


def _candidate_payload(
    index: int,
    *,
    pnl: str,
    duplicate_test_hash: bool = False,
    candidate_config_sha: str = _CANDIDATE_CONFIG_SHA,
    mark_lag: int = _MARK_LAG,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for window_index in range(3):
        hash_seed = window_index + 1 if duplicate_test_hash else index * 10 + window_index
        observations.append(
            {
                "evaluation_id": f"evaluation-{index:02x}{window_index:030x}",
                "experiment_id": f"exp-{index:02x}{window_index:038x}",
                "valuation_id": f"valuation-{index:02x}{window_index:038x}",
                "candidate_id": _CANDIDATE_ID,
                "candidate_config_sha256": candidate_config_sha,
                "window_index": window_index,
                "test_start": window_index * 5,
                "test_end": (window_index + 1) * 5,
                "test_semantic_sha256": _digest(hash_seed),
                "mark_lag_microseconds": mark_lag,
                "mark_to_market_pnl_usd": "1",
                "ending_equity_usd": str(100_001 + window_index),
                "period_return": 0.00001,
            }
        )
    return {
        "candidate_id": _CANDIDATE_ID,
        "candidate_config_sha256": candidate_config_sha,
        "coverage": "complete",
        "expected_evaluation_count": 3,
        "observed_evaluation_count": 3,
        "initial_equity_usd": "100000",
        "ending_equity_usd": str(100_000 + int(float(pnl))),
        "total_mark_to_market_pnl_usd": pnl,
        "maximum_drawdown_pct": 0.0,
        "annualized_sharpe_ratio": 1.0,
        "alpha_decay_method": "ols_terminal_pnl_bps_per_window",
        "oos_pnl_slope_bps_per_window": "0",
        "alpha_decay_bps_per_window": "0",
        "mark_lag_microseconds": mark_lag,
        "observations": observations,
    }


def _install_evidence_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pnls: tuple[str, str, str] = ("10", "20", "30"),
    duplicate_test_hash: bool = False,
    one_signer: bool = False,
    code_revision_drift: bool = False,
    dossier_statistics_sha_drift: bool = False,
    candidate_config_drift: bool = False,
    quorum_statuses: tuple[str, str, str] = (
        "approved_for_research_only",
        "approved_for_research_only",
        "approved_for_research_only",
    ),
) -> None:
    def signer_group(index: int) -> int:
        return 1 if one_signer else 1 + ((index - 1) % 2)

    def statistics_snapshot(path: Path) -> SimpleNamespace:
        index = _cohort_index(path)
        report_sha = _digest(200 + index)
        candidate_sha = (
            _digest(999)
            if candidate_config_drift and index == 2
            else _CANDIDATE_CONFIG_SHA
        )
        payload = {
            "code_revision": (
                "different-revision"
                if code_revision_drift and index == 3
                else _CODE_REVISION
            ),
            "package_version": _PACKAGE_VERSION,
            "periods_per_year": _PERIODS_PER_YEAR,
            "candidates": [
                _candidate_payload(
                    index,
                    pnl=pnls[index - 1],
                    duplicate_test_hash=duplicate_test_hash,
                    candidate_config_sha=candidate_sha,
                )
            ],
        }
        return SimpleNamespace(
            report_id=f"oos-report-{index:040x}",
            source_sha256=report_sha,
            matrix_sha256=_digest(100 + index),
            payload=payload,
        )

    def dossier_snapshot(path: Path) -> SimpleNamespace:
        index = _cohort_index(path)
        statistics = statistics_snapshot(
            path.parent / "statistics.json"
        )
        statistics_sha = (
            _digest(888)
            if dossier_statistics_sha_drift and index == 2
            else statistics.source_sha256
        )
        dossier_value = SimpleNamespace(
            dossier_id=f"selection-dossier-{index:040x}",
            matrix_sha256=statistics.matrix_sha256,
            statistics={
                "report_id": statistics.report_id,
                "sha256": statistics_sha,
            },
            code_revision=statistics.payload["code_revision"],
            package_version=_PACKAGE_VERSION,
            eligible_candidate_ids=(_CANDIDATE_ID,),
            blocked_candidate_ids=(),
        )
        return SimpleNamespace(
            source_sha256=_digest(300 + index),
            dossier=dossier_value,
        )

    def quorum_snapshot(path: Path) -> SimpleNamespace:
        index = _cohort_index(path)
        dossier = dossier_snapshot(path.parent / "dossier.json")
        envelope = SimpleNamespace(
            envelope_id=f"review-quorum-{index:040x}",
            dossier_id=dossier.dossier.dossier_id,
            dossier_sha256=dossier.source_sha256,
            requested_candidate_id=_CANDIDATE_ID,
            status=quorum_statuses[index - 1],
        )
        return SimpleNamespace(
            source_sha256=_digest(400 + index),
            envelope=envelope,
        )

    def verify_statistics(
        report_path: Path,
        _attestation_path: Path,
        *,
        trusted_public_key_path: Path | None = None,
    ) -> SimpleNamespace:
        assert trusted_public_key_path is not None
        index = _cohort_index(report_path)
        snapshot = statistics_snapshot(report_path)
        return SimpleNamespace(
            report_id=snapshot.report_id,
            report_sha256=snapshot.source_sha256,
            matrix_sha256=snapshot.matrix_sha256,
            key_id=_key_id(10 + signer_group(index)),
            trusted_key_matched=True,
        )

    def verify_dossier(
        dossier_path: Path,
        _attestation_path: Path,
        *,
        trusted_public_key_path: Path | None = None,
    ) -> SimpleNamespace:
        assert trusted_public_key_path is not None
        index = _cohort_index(dossier_path)
        snapshot = dossier_snapshot(dossier_path)
        return SimpleNamespace(
            dossier_id=snapshot.dossier.dossier_id,
            dossier_sha256=snapshot.source_sha256,
            matrix_sha256=snapshot.dossier.matrix_sha256,
            key_id=_key_id(20 + signer_group(index)),
            trusted_key_matched=True,
        )

    def verify_quorum(
        envelope_path: Path,
        _attestation_path: Path,
        *,
        trusted_public_key_path: Path | None = None,
    ) -> SimpleNamespace:
        assert trusted_public_key_path is not None
        index = _cohort_index(envelope_path)
        snapshot = quorum_snapshot(envelope_path)
        return SimpleNamespace(
            envelope_id=snapshot.envelope.envelope_id,
            envelope_sha256=snapshot.source_sha256,
            dossier_id=snapshot.envelope.dossier_id,
            requested_candidate_id=snapshot.envelope.requested_candidate_id,
            status=snapshot.envelope.status,
            key_id=_key_id(30 + signer_group(index)),
            trusted_key_matched=True,
        )

    monkeypatch.setattr(
        replication_module,
        "verify_statistics_attestation",
        verify_statistics,
    )
    monkeypatch.setattr(
        replication_module,
        "verify_selection_dossier_attestation",
        verify_dossier,
    )
    monkeypatch.setattr(
        replication_module,
        "verify_review_quorum_attestation",
        verify_quorum,
    )
    monkeypatch.setattr(
        replication_module,
        "load_statistics_report",
        statistics_snapshot,
    )
    monkeypatch.setattr(
        replication_module,
        "load_selection_dossier",
        dossier_snapshot,
    )
    monkeypatch.setattr(
        replication_module,
        "load_review_quorum_envelope",
        quorum_snapshot,
    )


def test_replication_inputs_are_strict_and_semantically_ordered(
    tmp_path: Path,
) -> None:
    first = load_replication_inputs(
        _write_inputs(tmp_path / "first.json", order=(3, 1, 2))
    )
    second = load_replication_inputs(
        _write_inputs(tmp_path / "second.json", order=(1, 2, 3))
    )

    assert first.canonical_sha256 == second.canonical_sha256
    assert first.source_sha256 != second.source_sha256
    assert [cohort.cohort_id for cohort in first.cohorts] == [
        f"cohort-{index:024x}" for index in (1, 2, 3)
    ]


@pytest.mark.parametrize("mutation", ["duplicate_id", "unsafe_path", "reused_path"])
def test_replication_inputs_reject_unsafe_or_reused_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    path = _write_inputs(tmp_path / "inputs.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "duplicate_id":
        payload["cohorts"][1]["cohort_id"] = payload["cohorts"][0]["cohort_id"]
    elif mutation == "unsafe_path":
        payload["cohorts"][0]["statistics"]["evidence"] = "/tmp/forbidden.json"
    else:
        payload["cohorts"][1]["statistics"]["evidence"] = payload["cohorts"][0][
            "statistics"
        ]["evidence"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_replication_inputs(path)


def test_replication_inputs_reject_missing_artifact(tmp_path: Path) -> None:
    path = _write_inputs(tmp_path / "inputs.json")
    (tmp_path / "cohort-2" / "quorum.attestation.json").unlink()

    with pytest.raises(ValueError, match="is not a file"):
        load_replication_inputs(path)


def test_replication_report_consistent_path_is_deterministic_and_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _write_plan(tmp_path / "plan.yaml")
    inputs = _write_inputs(tmp_path / "inputs.json")
    _install_evidence_mocks(monkeypatch)

    first = build_replication_report(plan_path=plan, inputs_path=inputs)
    second = build_replication_report(plan_path=plan, inputs_path=inputs)

    assert first.report_id == second.report_id
    assert first.status == "replication_consistent"
    assert first.cohort_count == 3
    assert first.research_approved_count == 3
    assert first.positive_replication_count == 3
    assert first.failed_replication_count == 0
    assert first.insufficient_replication_count == 0
    assert str(first.research_approved_fraction) == "1"
    assert str(first.positive_replication_fraction) == "1"
    assert str(first.worst_case_total_pnl_usd) == "10"
    assert str(first.median_total_pnl_usd) == "20"
    assert all(dict(first.independence_checks).values())
    assert all(dict(first.comparability_checks).values())
    assert all(dict(first.acceptance_checks).values())

    payload = first.as_dict()
    assert payload["selection"] is None
    assert payload["promotion"] is None
    assert payload["human_admit_required"] is True
    assert payload["automatic_promotion"] is False
    assert payload["release_authorized"] is False
    assert payload["deployment_authorized"] is False
    assert payload["trading_authorized"] is False
    assert "winner" not in payload
    assert "rank" not in payload
    assert "score" not in payload


def test_replication_report_failed_path_preserves_negative_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _write_plan(tmp_path / "plan.yaml")
    inputs = _write_inputs(tmp_path / "inputs.json")
    _install_evidence_mocks(monkeypatch, pnls=("10", "20", "-1"))

    report = build_replication_report(plan_path=plan, inputs_path=inputs)

    assert report.status == "replication_failed"
    assert report.positive_replication_count == 2
    assert report.failed_replication_count == 1
    assert report.insufficient_replication_count == 0
    assert report.worst_case_total_pnl_usd < 0
    assert not all(dict(report.acceptance_checks).values())


@pytest.mark.parametrize(
    "mode",
    ["duplicate_test_hash", "one_signer", "code_revision_drift", "quorum_defer"],
)
def test_replication_report_insufficient_paths_are_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    plan = _write_plan(tmp_path / "plan.yaml")
    inputs = _write_inputs(tmp_path / "inputs.json")
    _install_evidence_mocks(
        monkeypatch,
        duplicate_test_hash=mode == "duplicate_test_hash",
        one_signer=mode == "one_signer",
        code_revision_drift=mode == "code_revision_drift",
        quorum_statuses=(
            "approved_for_research_only",
            "approved_for_research_only",
            "deferred" if mode == "quorum_defer" else "approved_for_research_only",
        ),
    )

    report = build_replication_report(plan_path=plan, inputs_path=inputs)

    assert report.status == "replication_insufficient"
    assert (
        not all(dict(report.independence_checks).values())
        or not all(dict(report.comparability_checks).values())
        or report.insufficient_replication_count > 0
    )


@pytest.mark.parametrize(
    "mode",
    ["dossier_statistics_sha_drift", "candidate_config_drift"],
)
def test_replication_report_rejects_signed_chain_or_candidate_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    plan = _write_plan(tmp_path / "plan.yaml")
    inputs = _write_inputs(tmp_path / "inputs.json")
    _install_evidence_mocks(
        monkeypatch,
        dossier_statistics_sha_drift=mode == "dossier_statistics_sha_drift",
        candidate_config_drift=mode == "candidate_config_drift",
    )

    with pytest.raises(ValueError):
        build_replication_report(plan_path=plan, inputs_path=inputs)
