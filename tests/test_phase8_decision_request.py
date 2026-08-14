from __future__ import annotations

from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.decision_request import (
    load_decision_request,
    required_risk_acknowledgements,
)

_DOSSIER_ID = "selection-dossier-" + "a" * 40
_DOSSIER_SHA = "b" * 64
_ACKNOWLEDGEMENTS = required_risk_acknowledgements()


def _request_text(
    *,
    dossier_id: str = _DOSSIER_ID,
    dossier_sha: str = _DOSSIER_SHA,
    candidate_id: str = "candidate-example",
    requested_scope: str = "research_review_only",
    requester_role: str = "research_proposer",
    rationale: str = (
        "Request an independent human review of captured offline evidence only."
    ),
    requested_at: str = '"2026-08-14T00:00:00Z"',
    expires_at: str = '"2026-08-21T00:00:00Z"',
    acknowledgements: tuple[str, ...] = _ACKNOWLEDGEMENTS,
    decision: str = "null",
    deployment_authorized: str = "false",
    trading_authorized: str = "false",
    extra: str = "",
) -> str:
    acknowledgement_lines = "\n".join(
        f"  - {acknowledgement}" for acknowledgement in acknowledgements
    )
    return f"""schema_version: 1
dossier:
  dossier_id: {dossier_id}
  sha256: {dossier_sha}
requested_candidate_id: {candidate_id}
requested_scope: {requested_scope}
requester:
  subject: human-research-owner
  role: {requester_role}
rationale: {rationale}
requested_at: {requested_at}
expires_at: {expires_at}
risk_acknowledgements:
{acknowledgement_lines}
decision: {decision}
deployment_authorized: {deployment_authorized}
trading_authorized: {trading_authorized}
{extra}"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_decision_request_identity_is_semantic_and_non_authorizing(
    tmp_path: Path,
) -> None:
    first = load_decision_request(
        _write(tmp_path / "first.yaml", _request_text())
    )
    reversed_acknowledgements = tuple(reversed(_ACKNOWLEDGEMENTS))
    second_text = f"""requested_scope: research_review_only
schema_version: 1
requester:
  role: research_proposer
  subject: human-research-owner
dossier:
  sha256: {_DOSSIER_SHA}
  dossier_id: {_DOSSIER_ID}
requested_candidate_id: candidate-example
expires_at: "2026-08-21T08:00:00+08:00"
requested_at: "2026-08-14T08:00:00+08:00"
rationale: Request an independent human review of captured offline evidence only.
risk_acknowledgements:
""" + "\n".join(
        f"  - {acknowledgement}"
        for acknowledgement in reversed_acknowledgements
    ) + """
decision: null
trading_authorized: false
deployment_authorized: false
"""
    second = load_decision_request(
        _write(tmp_path / "second.yaml", second_text)
    )

    assert first.request_id == second.request_id
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.source_sha256 != second.source_sha256
    payload = first.summary()["request"]
    assert payload["requested_at"] == "2026-08-14T00:00:00.000000Z"
    assert payload["expires_at"] == "2026-08-21T00:00:00.000000Z"
    assert payload["risk_acknowledgements"] == list(_ACKNOWLEDGEMENTS)
    assert payload["decision"] is None
    assert payload["deployment_authorized"] is False
    assert payload["trading_authorized"] is False
    assert "winner" not in payload
    assert "deployment" not in payload


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (
            {"requested_scope": "automatic_promotion"},
            "scope must be research_review_only",
        ),
        (
            {"requester_role": "automated_selector"},
            "requester.role must be research_proposer",
        ),
        ({"decision": "approve"}, "decision must remain null"),
        ({"deployment_authorized": "true"}, "cannot authorize deployment"),
        ({"trading_authorized": "true"}, "cannot authorize trading"),
        (
            {"rationale": "too short"},
            "rationale length must be in",
        ),
        (
            {"candidate_id": "not-a-candidate"},
            "requested_candidate_id",
        ),
        (
            {"dossier_id": "selection-dossier-short"},
            "dossier_id",
        ),
        ({"dossier_sha": "not-a-digest"}, "dossier sha256"),
    ],
)
def test_decision_request_rejects_unsafe_or_malformed_values(
    tmp_path: Path,
    kwargs: dict[str, object],
    match: str,
) -> None:
    path = _write(
        tmp_path / "request.yaml",
        _request_text(**kwargs),  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match=match):
        load_decision_request(path)


def test_decision_request_requires_exact_risk_acknowledgements(
    tmp_path: Path,
) -> None:
    missing = _ACKNOWLEDGEMENTS[:-1]
    with pytest.raises(ValueError, match="missing risk acknowledgements"):
        load_decision_request(
            _write(
                tmp_path / "missing.yaml",
                _request_text(acknowledgements=missing),
            )
        )

    unknown = (*_ACKNOWLEDGEMENTS, "profitability_guaranteed")
    with pytest.raises(ValueError, match="unknown risk acknowledgements"):
        load_decision_request(
            _write(
                tmp_path / "unknown.yaml",
                _request_text(acknowledgements=unknown),
            )
        )

    duplicate = (*_ACKNOWLEDGEMENTS, _ACKNOWLEDGEMENTS[0])
    with pytest.raises(ValueError, match="cannot contain duplicates"):
        load_decision_request(
            _write(
                tmp_path / "duplicate.yaml",
                _request_text(acknowledgements=duplicate),
            )
        )


def test_decision_request_requires_bounded_aware_timestamps(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be a non-empty string"):
        load_decision_request(
            _write(
                tmp_path / "implicit.yaml",
                _request_text(requested_at="2026-08-14T00:00:00Z"),
            )
        )

    with pytest.raises(ValueError, match="must be after requested_at"):
        load_decision_request(
            _write(
                tmp_path / "reversed.yaml",
                _request_text(expires_at='"2026-08-13T00:00:00Z"'),
            )
        )

    with pytest.raises(ValueError, match="cannot exceed 30 days"):
        load_decision_request(
            _write(
                tmp_path / "too-long.yaml",
                _request_text(expires_at='"2026-09-14T00:00:01Z"'),
            )
        )

    with pytest.raises(ValueError, match="must include a timezone"):
        load_decision_request(
            _write(
                tmp_path / "naive.yaml",
                _request_text(requested_at='"2026-08-14T00:00:00"'),
            )
        )


def test_decision_request_rejects_unknown_missing_and_duplicate_fields(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="unknown fields"):
        load_decision_request(
            _write(
                tmp_path / "unknown.yaml",
                _request_text(extra="winner: candidate-forbidden\n"),
            )
        )

    missing = _request_text().replace("decision: null\n", "")
    with pytest.raises(ValueError, match="missing fields"):
        load_decision_request(_write(tmp_path / "missing.yaml", missing))

    duplicate = _request_text() + "requested_scope: research_review_only\n"
    with pytest.raises(ValueError, match="invalid decision-request YAML"):
        load_decision_request(_write(tmp_path / "duplicate.yaml", duplicate))
