from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.decision_request import (
    load_decision_request,
    required_risk_acknowledgements,
)
from llm_arbitrage_system.experiments.decision_request_signing import (
    sign_decision_request,
    verify_decision_request_attestation,
)
from llm_arbitrage_system.experiments.review_evidence import (
    load_review_record,
    required_review_acknowledgements,
    sign_review_record,
    verify_review_record_attestation,
)
from llm_arbitrage_system.experiments.selection_diagnostics import (
    build_selection_diagnostics,
)
from llm_arbitrage_system.experiments.selection_dossier import (
    build_selection_dossier,
    load_selection_dossier,
)
from llm_arbitrage_system.experiments.selection_signing import (
    sign_selection_dossier,
)
from llm_arbitrage_system.experiments.signing import generate_signing_keypair

_MATRIX_SHA = "b82cadbc214144710becc3f9cf3d3791d504687124308ed964704b2b07e40232"
_REQUEST_ACKS = required_risk_acknowledgements()
_REVIEW_ACKS = required_review_acknowledgements()


def _policy(path: Path) -> Path:
    path.write_text(
        f"""schema_version: 1
matrix_sha256: {_MATRIX_SHA}
decision_mode: human_review_only
objective:
  metric: total_mark_to_market_pnl_usd
  direction: maximize
  tie_breakers:
    - maximum_drawdown_pct
admission:
  minimum_candidates: 2
  minimum_windows_per_candidate: 3
  require_complete_coverage: true
  require_equal_window_indexes: true
  require_equal_test_intervals: true
  require_equal_mark_lag: true
  maximum_drawdown_pct: "25"
  minimum_positive_window_fraction: "0.5"
  maximum_alpha_decay_bps_per_window: "100"
multiple_testing:
  method: holm_sign_test
  family_alpha: "0.05"
  minimum_non_tied_pairwise_windows: 3
  require_adjusted_pairwise_evidence: false
""",
        encoding="utf-8",
    )
    return path


def _observation(
    candidate_id: str,
    config_sha: str,
    index: int,
    pnl: int,
    ending_equity: int,
) -> dict[str, Any]:
    return {
        "evaluation_id": f"evaluation-{candidate_id}-{index}",
        "experiment_id": f"experiment-{candidate_id}-{index}",
        "valuation_id": f"valuation-{candidate_id}-{index}",
        "candidate_id": candidate_id,
        "candidate_config_sha256": config_sha,
        "window_index": index,
        "test_start": index * 10,
        "test_end": index * 10 + 5,
        "test_semantic_sha256": f"{index + 1:064x}",
        "mark_lag_microseconds": 60_000_000,
        "mark_to_market_pnl_usd": str(pnl),
        "ending_equity_usd": str(ending_equity),
        "period_return": pnl / 100000.0,
    }


def _candidate(
    candidate_id: str,
    config_character: str,
    pnl_values: tuple[int, ...],
) -> dict[str, Any]:
    config_sha = config_character * 64
    equity = 100000
    observations: list[dict[str, Any]] = []
    for index, pnl in enumerate(pnl_values):
        equity += pnl
        observations.append(
            _observation(candidate_id, config_sha, index, pnl, equity)
        )
    total = sum(pnl_values)
    return {
        "candidate_id": candidate_id,
        "candidate_config_sha256": config_sha,
        "coverage": "complete",
        "expected_evaluation_count": len(pnl_values),
        "observed_evaluation_count": len(pnl_values),
        "initial_equity_usd": "100000",
        "ending_equity_usd": str(100000 + total),
        "total_mark_to_market_pnl_usd": str(total),
        "maximum_drawdown_pct": 5.0,
        "annualized_sharpe_ratio": 1.25,
        "alpha_decay_method": "ols_terminal_pnl_bps_per_window",
        "oos_pnl_slope_bps_per_window": "-1",
        "alpha_decay_bps_per_window": "10",
        "mark_lag_microseconds": 60_000_000,
        "observations": observations,
    }


def _statistics(path: Path) -> Path:
    write_json(
        path,
        {
            "schema_version": 1,
            "report_id": "oos-report-" + "c" * 40,
            "matrix_sha256": _MATRIX_SHA,
            "code_revision": "phase8-review-fixture",
            "package_version": "0.1.0",
            "periods_per_year": 252,
            "candidates": [
                _candidate("candidate-b", "b", (1, 2, 3)),
                _candidate("candidate-a", "a", (10, 8, 6)),
            ],
            "selection": None,
            "assumptions": ["Synthetic Phase 8 reviewer fixture."],
            "evidence_boundary": "Synthetic offline paper fixture only.",
        },
    )
    return path


def _request_yaml(
    path: Path,
    *,
    dossier_id: str,
    dossier_sha: str,
    candidate_id: str = "candidate-a",
    requester_subject: str = "research-proposer-one",
    expires_at: str = "2026-08-21T00:00:00Z",
) -> Path:
    acknowledgement_lines = "\n".join(
        f"  - {value}" for value in _REQUEST_ACKS
    )
    path.write_text(
        f"""schema_version: 1
dossier:
  dossier_id: {dossier_id}
  sha256: {dossier_sha}
requested_candidate_id: {candidate_id}
requested_scope: research_review_only
requester:
  subject: {requester_subject}
  role: research_proposer
rationale: Request an independent research-only review of captured evidence.
requested_at: "2026-08-14T00:00:00Z"
expires_at: "{expires_at}"
risk_acknowledgements:
{acknowledgement_lines}
decision: null
deployment_authorized: false
trading_authorized: false
""",
        encoding="utf-8",
    )
    return path


def _review_yaml(
    path: Path,
    *,
    request_id: str,
    request_sha: str,
    dossier_id: str,
    dossier_sha: str,
    candidate_id: str = "candidate-a",
    decision: str = "defer",
    reviewer_subject: str = "independent-reviewer-one",
    reviewed_at: str = "2026-08-15T00:00:00Z",
    deployment_authorized: str = "false",
    trading_authorized: str = "false",
) -> Path:
    acknowledgement_lines = "\n".join(
        f"  - {value}" for value in _REVIEW_ACKS
    )
    path.write_text(
        f"""schema_version: 1
request:
  request_id: {request_id}
  canonical_sha256: {request_sha}
dossier:
  dossier_id: {dossier_id}
  sha256: {dossier_sha}
requested_candidate_id: {candidate_id}
decision: {decision}
reviewer:
  subject: {reviewer_subject}
  role: independent_reviewer
rationale: Defer pending additional independently sourced terminal-mark evidence.
reviewed_at: "{reviewed_at}"
risk_acknowledgements:
{acknowledgement_lines}
deployment_authorized: {deployment_authorized}
trading_authorized: {trading_authorized}
""",
        encoding="utf-8",
    )
    return path


def _fixture(tmp_path: Path) -> dict[str, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    policy = _policy(tmp_path / "policy.yaml")
    statistics = _statistics(tmp_path / "statistics.json")
    diagnostics_path = tmp_path / "diagnostics.json"
    diagnostics = build_selection_diagnostics(
        policy_path=policy,
        statistics_report_path=statistics,
        code_revision="phase8-review-diagnostics",
        package_version="0.1.0",
    )
    write_json(diagnostics_path, diagnostics.as_dict())
    dossier_path = tmp_path / "dossier.json"
    dossier = build_selection_dossier(
        policy_path=policy,
        statistics_report_path=statistics,
        diagnostics_path=diagnostics_path,
        code_revision="phase8-review-dossier",
        package_version="0.1.0",
    )
    write_json(dossier_path, dossier.as_dict())
    dossier_snapshot = load_selection_dossier(dossier_path)

    dossier_private = tmp_path / "dossier-key/private.pem"
    dossier_public = tmp_path / "dossier-key/public.pem"
    requester_private = tmp_path / "requester-key/private.pem"
    requester_public = tmp_path / "requester-key/public.pem"
    reviewer_private = tmp_path / "reviewer-key/private.pem"
    reviewer_public = tmp_path / "reviewer-key/public.pem"
    generate_signing_keypair(dossier_private, dossier_public)
    generate_signing_keypair(requester_private, requester_public)
    generate_signing_keypair(reviewer_private, reviewer_public)

    dossier_attestation = tmp_path / "dossier.attestation.json"
    sign_selection_dossier(
        dossier_path,
        dossier_private,
        dossier_attestation,
    )
    request_path = _request_yaml(
        tmp_path / "request.yaml",
        dossier_id=dossier_snapshot.dossier.dossier_id,
        dossier_sha=dossier_snapshot.source_sha256,
    )
    request_snapshot = load_decision_request(request_path)
    request_attestation = tmp_path / "request.attestation.json"
    sign_decision_request(
        request_path,
        requester_private,
        request_attestation,
    )
    review_path = _review_yaml(
        tmp_path / "review.yaml",
        request_id=request_snapshot.request_id,
        request_sha=request_snapshot.canonical_sha256,
        dossier_id=dossier_snapshot.dossier.dossier_id,
        dossier_sha=dossier_snapshot.source_sha256,
    )
    return {
        "dossier": dossier_path,
        "dossier_attestation": dossier_attestation,
        "dossier_private": dossier_private,
        "dossier_public": dossier_public,
        "request": request_path,
        "request_attestation": request_attestation,
        "requester_private": requester_private,
        "requester_public": requester_public,
        "review": review_path,
        "reviewer_private": reviewer_private,
        "reviewer_public": reviewer_public,
    }


def _sign_review(paths: dict[str, Path], output: Path) -> None:
    sign_review_record(
        record_path=paths["review"],
        request_path=paths["request"],
        request_attestation_path=paths["request_attestation"],
        trusted_requester_public_key_path=paths["requester_public"],
        dossier_path=paths["dossier"],
        dossier_attestation_path=paths["dossier_attestation"],
        trusted_dossier_public_key_path=paths["dossier_public"],
        reviewer_private_key_path=paths["reviewer_private"],
        output_path=output,
    )


def test_independent_review_evidence_round_trip(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    review_snapshot = load_review_record(paths["review"])
    request_snapshot = load_decision_request(paths["request"])
    verify_decision_request_attestation(
        paths["request"],
        paths["request_attestation"],
        trusted_public_key_path=paths["requester_public"],
    )
    attestation = tmp_path / "review.attestation.json"
    _sign_review(paths, attestation)
    verified = verify_review_record_attestation(
        record_path=paths["review"],
        attestation_path=attestation,
        trusted_reviewer_public_key_path=paths["reviewer_public"],
        request_path=paths["request"],
        request_attestation_path=paths["request_attestation"],
        trusted_requester_public_key_path=paths["requester_public"],
        dossier_path=paths["dossier"],
        dossier_attestation_path=paths["dossier_attestation"],
        trusted_dossier_public_key_path=paths["dossier_public"],
    )

    assert verified.record_id == review_snapshot.record_id
    assert verified.request_id == request_snapshot.request_id
    assert verified.requested_candidate_id == "candidate-a"
    assert verified.decision == "defer"
    assert verified.trusted_key_matched is True
    payload = verified.as_dict()
    assert payload["deployment_authorized"] is False
    assert payload["trading_authorized"] is False


def test_review_signer_must_be_independent(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(ValueError, match="reviewer key must differ from requester key"):
        sign_review_record(
            record_path=paths["review"],
            request_path=paths["request"],
            request_attestation_path=paths["request_attestation"],
            trusted_requester_public_key_path=paths["requester_public"],
            dossier_path=paths["dossier"],
            dossier_attestation_path=paths["dossier_attestation"],
            trusted_dossier_public_key_path=paths["dossier_public"],
            reviewer_private_key_path=paths["requester_private"],
            output_path=tmp_path / "invalid.attestation.json",
        )

    paths["reviewer_private"] = paths["dossier_private"]
    with pytest.raises(
        ValueError,
        match="reviewer key must differ from dossier provenance key",
    ):
        _sign_review(paths, tmp_path / "invalid-dossier-key.attestation.json")


def test_review_context_requires_eligible_candidate_and_unexpired_request(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    request_snapshot = load_decision_request(paths["request"])
    dossier_snapshot = load_selection_dossier(paths["dossier"])

    ineligible_request = _request_yaml(
        tmp_path / "ineligible-request.yaml",
        dossier_id=dossier_snapshot.dossier.dossier_id,
        dossier_sha=dossier_snapshot.source_sha256,
        candidate_id="candidate-missing",
    )
    ineligible_attestation = tmp_path / "ineligible-request.attestation.json"
    sign_decision_request(
        ineligible_request,
        paths["requester_private"],
        ineligible_attestation,
    )
    ineligible_snapshot = load_decision_request(ineligible_request)
    ineligible_review = _review_yaml(
        tmp_path / "ineligible-review.yaml",
        request_id=ineligible_snapshot.request_id,
        request_sha=ineligible_snapshot.canonical_sha256,
        dossier_id=dossier_snapshot.dossier.dossier_id,
        dossier_sha=dossier_snapshot.source_sha256,
        candidate_id="candidate-missing",
    )
    with pytest.raises(ValueError, match="not eligible for human review"):
        sign_review_record(
            record_path=ineligible_review,
            request_path=ineligible_request,
            request_attestation_path=ineligible_attestation,
            trusted_requester_public_key_path=paths["requester_public"],
            dossier_path=paths["dossier"],
            dossier_attestation_path=paths["dossier_attestation"],
            trusted_dossier_public_key_path=paths["dossier_public"],
            reviewer_private_key_path=paths["reviewer_private"],
            output_path=tmp_path / "ineligible.attestation.json",
        )

    expired_review = _review_yaml(
        tmp_path / "expired-review.yaml",
        request_id=request_snapshot.request_id,
        request_sha=request_snapshot.canonical_sha256,
        dossier_id=dossier_snapshot.dossier.dossier_id,
        dossier_sha=dossier_snapshot.source_sha256,
        reviewed_at="2026-08-22T00:00:00Z",
    )
    paths["review"] = expired_review
    with pytest.raises(ValueError, match="after request expiry"):
        _sign_review(paths, tmp_path / "expired.attestation.json")


def test_review_record_rejects_authorization_and_subject_collision(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    request_snapshot = load_decision_request(paths["request"])
    dossier_snapshot = load_selection_dossier(paths["dossier"])
    authorized = _review_yaml(
        tmp_path / "authorized.yaml",
        request_id=request_snapshot.request_id,
        request_sha=request_snapshot.canonical_sha256,
        dossier_id=dossier_snapshot.dossier.dossier_id,
        dossier_sha=dossier_snapshot.source_sha256,
        deployment_authorized="true",
    )
    with pytest.raises(ValueError, match="cannot authorize deployment"):
        load_review_record(authorized)

    same_subject = _review_yaml(
        tmp_path / "same-subject.yaml",
        request_id=request_snapshot.request_id,
        request_sha=request_snapshot.canonical_sha256,
        dossier_id=dossier_snapshot.dossier.dossier_id,
        dossier_sha=dossier_snapshot.source_sha256,
        reviewer_subject="research-proposer-one",
    )
    paths["review"] = same_subject
    with pytest.raises(ValueError, match="reviewer subject must differ"):
        _sign_review(paths, tmp_path / "same-subject.attestation.json")


def test_review_attestation_rejects_wrong_key_and_record_tampering(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    attestation = tmp_path / "review.attestation.json"
    _sign_review(paths, attestation)
    wrong_private = tmp_path / "wrong/private.pem"
    wrong_public = tmp_path / "wrong/public.pem"
    generate_signing_keypair(wrong_private, wrong_public)
    with pytest.raises(ValueError, match="trusted public key"):
        verify_review_record_attestation(
            record_path=paths["review"],
            attestation_path=attestation,
            trusted_reviewer_public_key_path=wrong_public,
            request_path=paths["request"],
            request_attestation_path=paths["request_attestation"],
            trusted_requester_public_key_path=paths["requester_public"],
            dossier_path=paths["dossier"],
            dossier_attestation_path=paths["dossier_attestation"],
            trusted_dossier_public_key_path=paths["dossier_public"],
        )

    record = paths["review"]
    record.write_text(
        record.read_text(encoding="utf-8").replace("decision: defer", "decision: reject"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match current review evidence"):
        verify_review_record_attestation(
            record_path=record,
            attestation_path=attestation,
            trusted_reviewer_public_key_path=paths["reviewer_public"],
            request_path=paths["request"],
            request_attestation_path=paths["request_attestation"],
            trusted_requester_public_key_path=paths["requester_public"],
            dossier_path=paths["dossier"],
            dossier_attestation_path=paths["dossier_attestation"],
            trusted_dossier_public_key_path=paths["dossier_public"],
        )


def test_review_record_rejects_duplicate_and_missing_fields(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    duplicate = paths["review"]
    duplicate.write_text(
        duplicate.read_text(encoding="utf-8") + "decision: defer\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid review-record YAML"):
        load_review_record(duplicate)

    clean_paths = _fixture(tmp_path / "second")
    missing = clean_paths["review"]
    missing.write_text(
        missing.read_text(encoding="utf-8").replace(
            "trading_authorized: false\n",
            "",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing fields"):
        load_review_record(missing)
