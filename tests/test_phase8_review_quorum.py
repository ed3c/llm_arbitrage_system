from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import llm_arbitrage_system.experiments.review_quorum as quorum_module
from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.review_quorum import (
    QuorumReviewEvidence,
    ReviewInput,
    ReviewQuorumEnvelope,
    ReviewQuorumInputSnapshot,
    ReviewQuorumSpec,
    SignedInput,
    build_review_quorum,
    load_review_quorum_envelope,
    load_review_quorum_inputs,
)
from llm_arbitrage_system.experiments.review_quorum_signing import (
    sign_review_quorum_envelope,
    verify_review_quorum_attestation,
)
from llm_arbitrage_system.experiments.signing import generate_signing_keypair

_REQUEST_ID = "decision-request-" + "a" * 40
_REQUEST_SHA = "b" * 64
_DOSSIER_ID = "selection-dossier-" + "c" * 40
_DOSSIER_SHA = "d" * 64


def _keypair(tmp_path: Path, name: str) -> tuple[Path, Path, str]:
    private_key = tmp_path / name / "private.pem"
    public_key = tmp_path / name / "public.pem"
    identity = generate_signing_keypair(private_key, public_key)
    return private_key, public_key, identity.key_id


def _review(
    record_character: str,
    reviewer_key_id: str,
    subject: str,
    decision: str,
    reviewed_at: str,
) -> QuorumReviewEvidence:
    return QuorumReviewEvidence(
        record_id="review-record-" + record_character * 40,
        record_sha256=record_character * 64,
        reviewer_subject=subject,
        reviewer_key_id=reviewer_key_id,
        decision=decision,
        reviewed_at=reviewed_at,
    )


def _envelope(
    tmp_path: Path,
    decisions: tuple[str, ...] = (
        "approve_research_only",
        "approve_research_only",
    ),
    minimum: int = 2,
) -> tuple[Path, dict[str, tuple[Path, Path, str]]]:
    keys = {
        "requester": _keypair(tmp_path, "requester"),
        "dossier": _keypair(tmp_path, "dossier"),
        "reviewer-a": _keypair(tmp_path, "reviewer-a"),
        "reviewer-b": _keypair(tmp_path, "reviewer-b"),
        "quorum": _keypair(tmp_path, "quorum"),
        "wrong": _keypair(tmp_path, "wrong"),
    }
    review_keys = (keys["reviewer-a"][2], keys["reviewer-b"][2])
    reviews = tuple(
        sorted(
            (
                _review(
                    chr(ord("e") + index),
                    review_keys[index],
                    f"reviewer-{index}",
                    decision,
                    f"2026-08-{15 + index:02d}T00:00:00.000000Z",
                )
                for index, decision in enumerate(decisions)
            ),
            key=lambda item: (item.reviewer_key_id, item.record_id),
        )
    )
    if "reject" in decisions:
        status = "rejected"
    elif "defer" in decisions:
        status = "deferred"
    elif len(reviews) >= minimum:
        status = "approved_for_research_only"
    else:
        status = "blocked"
    envelope = ReviewQuorumEnvelope(
        envelope_id="review-quorum-placeholder",
        request_id=_REQUEST_ID,
        request_sha256=_REQUEST_SHA,
        requester_key_id=keys["requester"][2],
        dossier_id=_DOSSIER_ID,
        dossier_sha256=_DOSSIER_SHA,
        dossier_key_id=keys["dossier"][2],
        requested_candidate_id="candidate-example",
        minimum_distinct_reviewers=minimum,
        status=status,
        reviews=reviews,
    )
    identity = {
        "schema_version": 1,
        "scope": "research_review_only",
        "request": {
            "request_id": envelope.request_id,
            "canonical_sha256": envelope.request_sha256,
            "requester_key_id": envelope.requester_key_id,
        },
        "dossier": {
            "dossier_id": envelope.dossier_id,
            "sha256": envelope.dossier_sha256,
            "dossier_key_id": envelope.dossier_key_id,
        },
        "requested_candidate_id": envelope.requested_candidate_id,
        "minimum_distinct_reviewers": envelope.minimum_distinct_reviewers,
        "status": envelope.status,
        "reviews": [review.as_dict() for review in envelope.reviews],
        "deployment_authorized": False,
        "trading_authorized": False,
        "release_authorized": False,
    }
    from llm_arbitrage_system.experiments.canonical import (
        canonical_json_bytes,
        sha256_hex,
    )

    envelope = ReviewQuorumEnvelope(
        envelope_id="review-quorum-"
        + sha256_hex(canonical_json_bytes(identity))[:40],
        request_id=envelope.request_id,
        request_sha256=envelope.request_sha256,
        requester_key_id=envelope.requester_key_id,
        dossier_id=envelope.dossier_id,
        dossier_sha256=envelope.dossier_sha256,
        dossier_key_id=envelope.dossier_key_id,
        requested_candidate_id=envelope.requested_candidate_id,
        minimum_distinct_reviewers=envelope.minimum_distinct_reviewers,
        status=envelope.status,
        reviews=envelope.reviews,
    )
    path = tmp_path / "quorum.json"
    write_json(path, envelope.as_dict())
    return path, keys


def _touch(path: Path, value: str = "fixture") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def test_review_quorum_input_contract_is_strict_and_non_authorizing(
    tmp_path: Path,
) -> None:
    request = _touch(tmp_path / "request.yaml")
    request_attestation = _touch(tmp_path / "request.attestation.json")
    requester_key = _touch(tmp_path / "requester.pub.pem")
    dossier = _touch(tmp_path / "dossier.json")
    dossier_attestation = _touch(tmp_path / "dossier.attestation.json")
    dossier_key = _touch(tmp_path / "dossier.pub.pem")
    review = _touch(tmp_path / "review.yaml")
    review_attestation = _touch(tmp_path / "review.attestation.json")
    review_key = _touch(tmp_path / "reviewer.pub.pem")
    inputs = tmp_path / "inputs.yaml"
    inputs.write_text(
        f"""schema_version: 1
scope: research_review_only
minimum_distinct_reviewers: 2
request:
  path: {request.name}
  attestation: {request_attestation.name}
  trusted_public_key: {requester_key.name}
dossier:
  path: {dossier.name}
  attestation: {dossier_attestation.name}
  trusted_public_key: {dossier_key.name}
reviews:
  - record: {review.name}
    attestation: {review_attestation.name}
    trusted_public_key: {review_key.name}
deployment_authorized: false
trading_authorized: false
release_authorized: false
""",
        encoding="utf-8",
    )
    snapshot = load_review_quorum_inputs(inputs)
    assert snapshot.spec.minimum_distinct_reviewers == 2
    assert len(snapshot.spec.reviews) == 1
    summary = snapshot.summary()
    assert summary["deployment_authorized"] is False
    assert summary["trading_authorized"] is False
    assert summary["release_authorized"] is False

    unsafe = inputs.read_text(encoding="utf-8").replace(
        "deployment_authorized: false",
        "deployment_authorized: true",
    )
    inputs.write_text(unsafe, encoding="utf-8")
    with pytest.raises(ValueError, match="cannot authorize deployment"):
        load_review_quorum_inputs(inputs)


def test_review_quorum_input_rejects_duplicate_and_unknown_fields(
    tmp_path: Path,
) -> None:
    for name in (
        "request.yaml",
        "request.attestation.json",
        "requester.pub.pem",
        "dossier.json",
        "dossier.attestation.json",
        "dossier.pub.pem",
        "review.yaml",
        "review.attestation.json",
        "reviewer.pub.pem",
    ):
        _touch(tmp_path / name)
    base = """schema_version: 1
scope: research_review_only
minimum_distinct_reviewers: 2
request:
  path: request.yaml
  attestation: request.attestation.json
  trusted_public_key: requester.pub.pem
dossier:
  path: dossier.json
  attestation: dossier.attestation.json
  trusted_public_key: dossier.pub.pem
reviews:
  - record: review.yaml
    attestation: review.attestation.json
    trusted_public_key: reviewer.pub.pem
deployment_authorized: false
trading_authorized: false
release_authorized: false
"""
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(base + "scope: research_review_only\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid review-quorum YAML"):
        load_review_quorum_inputs(duplicate)
    unknown = tmp_path / "unknown.yaml"
    unknown.write_text(base + "production: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fields"):
        load_review_quorum_inputs(unknown)


@pytest.mark.parametrize(
    ("decisions", "minimum", "expected"),
    [
        (
            ("approve_research_only", "approve_research_only"),
            2,
            "approved_for_research_only",
        ),
        (("approve_research_only", "defer"), 2, "deferred"),
        (("approve_research_only", "reject"), 2, "rejected"),
        (("approve_research_only",), 2, "blocked"),
    ],
)
def test_quorum_status_is_deterministic_and_non_deployable(
    tmp_path: Path,
    decisions: tuple[str, ...],
    minimum: int,
    expected: str,
) -> None:
    path, _ = _envelope(tmp_path, decisions, minimum)
    snapshot = load_review_quorum_envelope(path)
    assert snapshot.envelope.status == expected
    payload = snapshot.envelope.as_dict()
    assert payload["deployment_authorized"] is False
    assert payload["trading_authorized"] is False
    assert payload["release_authorized"] is False
    assert "selected_candidate_id" not in payload
    assert "promotion" not in payload


def test_quorum_signing_requires_independent_key_and_rejects_tamper(
    tmp_path: Path,
) -> None:
    path, keys = _envelope(tmp_path)
    attestation = tmp_path / "quorum.attestation.json"
    sign_review_quorum_envelope(
        path,
        keys["quorum"][0],
        attestation,
    )
    verified = verify_review_quorum_attestation(
        path,
        attestation,
        trusted_public_key_path=keys["quorum"][1],
    )
    assert verified.status == "approved_for_research_only"
    assert verified.as_dict()["deployment_authorized"] is False

    with pytest.raises(ValueError, match="must differ from requester"):
        sign_review_quorum_envelope(
            path,
            keys["requester"][0],
            tmp_path / "invalid.attestation.json",
        )
    with pytest.raises(ValueError, match="trusted public key"):
        verify_review_quorum_attestation(
            path,
            attestation,
            trusted_public_key_path=keys["wrong"][1],
        )

    payload = path.read_text(encoding="utf-8").replace(
        '"status":"approved_for_research_only"',
        '"status":"deferred"',
    )
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(ValueError):
        verify_review_quorum_attestation(
            path,
            attestation,
            trusted_public_key_path=keys["quorum"][1],
        )


def test_build_review_quorum_binds_verified_review_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_file = _touch(tmp_path / "request.yaml")
    request_attestation_file = _touch(tmp_path / "request.attestation.json")
    requester_public = _touch(tmp_path / "requester.pub.pem")
    dossier_file = _touch(tmp_path / "dossier.json")
    dossier_attestation_file = _touch(tmp_path / "dossier.attestation.json")
    dossier_public = _touch(tmp_path / "dossier.pub.pem")
    review_files = tuple(_touch(tmp_path / f"review-{index}.yaml") for index in range(2))
    review_attestations = tuple(
        _touch(tmp_path / f"review-{index}.attestation.json")
        for index in range(2)
    )
    review_keys = tuple(
        _touch(tmp_path / f"reviewer-{index}.pub.pem") for index in range(2)
    )
    spec = ReviewQuorumSpec(
        minimum_distinct_reviewers=2,
        request=SignedInput(
            path=request_file,
            attestation=request_attestation_file,
            trusted_public_key=requester_public,
        ),
        dossier=SignedInput(
            path=dossier_file,
            attestation=dossier_attestation_file,
            trusted_public_key=dossier_public,
        ),
        reviews=tuple(
            ReviewInput(
                record=review_files[index],
                attestation=review_attestations[index],
                trusted_public_key=review_keys[index],
            )
            for index in range(2)
        ),
    )
    snapshot = ReviewQuorumInputSnapshot(
        source_path=tmp_path / "inputs.yaml",
        spec=spec,
        source_sha256="1" * 64,
        canonical_sha256="2" * 64,
        canonical_bytes=b"{}\n",
        source_bytes=b"fixture",
    )
    requester_key = "ed25519-" + "1" * 32
    dossier_key = "ed25519-" + "2" * 32
    reviewer_key_ids = (
        "ed25519-" + "3" * 32,
        "ed25519-" + "4" * 32,
    )
    request = SimpleNamespace(
        request_id=_REQUEST_ID,
        canonical_sha256=_REQUEST_SHA,
        request=SimpleNamespace(
            dossier=SimpleNamespace(dossier_id=_DOSSIER_ID, sha256=_DOSSIER_SHA),
            requested_candidate_id="candidate-example",
        ),
    )
    dossier = SimpleNamespace(
        source_sha256=_DOSSIER_SHA,
        dossier=SimpleNamespace(
            dossier_id=_DOSSIER_ID,
            eligible_candidate_ids=("candidate-example",),
            blocked_candidate_ids=(),
        ),
    )
    monkeypatch.setattr(quorum_module, "load_review_quorum_inputs", lambda path: snapshot)
    monkeypatch.setattr(quorum_module, "load_decision_request", lambda path: request)
    monkeypatch.setattr(
        quorum_module,
        "verify_decision_request_attestation",
        lambda *args, **kwargs: SimpleNamespace(key_id=requester_key),
    )
    monkeypatch.setattr(quorum_module, "load_selection_dossier", lambda path: dossier)
    monkeypatch.setattr(
        quorum_module,
        "verify_selection_dossier_attestation",
        lambda *args, **kwargs: SimpleNamespace(key_id=dossier_key),
    )

    records = {
        review_files[index]: SimpleNamespace(
            record_id="review-record-" + str(index + 5) * 40,
            canonical_sha256=str(index + 5) * 64,
            record=SimpleNamespace(
                reviewer=SimpleNamespace(subject=f"reviewer-{index}"),
                reviewed_at=SimpleNamespace(
                    isoformat=lambda timespec, stamp=f"2026-08-{15 + index:02d}T00:00:00+00:00": stamp
                ),
            ),
        )
        for index in range(2)
    }
    monkeypatch.setattr(quorum_module, "load_review_record", lambda path: records[path])

    def _verify_review(**kwargs: Any) -> SimpleNamespace:
        index = review_files.index(kwargs["record_path"])
        return SimpleNamespace(
            record_id=records[review_files[index]].record_id,
            record_sha256=records[review_files[index]].canonical_sha256,
            reviewer_key_id=reviewer_key_ids[index],
            decision="approve_research_only",
        )

    monkeypatch.setattr(
        quorum_module,
        "verify_review_record_attestation",
        _verify_review,
    )
    envelope = build_review_quorum(tmp_path / "inputs.yaml")
    assert envelope.status == "approved_for_research_only"
    assert envelope.request_id == _REQUEST_ID
    assert envelope.dossier_id == _DOSSIER_ID
    assert [review.reviewer_subject for review in envelope.reviews] == sorted(
        ["reviewer-0", "reviewer-1"],
        key=lambda subject: reviewer_key_ids[int(subject[-1])],
    )
