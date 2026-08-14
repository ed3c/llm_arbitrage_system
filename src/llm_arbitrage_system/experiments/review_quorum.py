from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.decision_request import load_decision_request
from llm_arbitrage_system.experiments.decision_request_signing import (
    verify_decision_request_attestation,
)
from llm_arbitrage_system.experiments.review_evidence import (
    load_review_record,
    verify_review_record_attestation,
)
from llm_arbitrage_system.experiments.selection_dossier import load_selection_dossier
from llm_arbitrage_system.experiments.selection_signing import (
    verify_selection_dossier_attestation,
)
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_INPUT_SCHEMA_VERSION = 1
_ENVELOPE_SCHEMA_VERSION = 1
_SCOPE = "research_review_only"
_STATUSES = {
    "approved_for_research_only",
    "blocked",
    "deferred",
    "rejected",
}
_ENVELOPE_FIELDS = {
    "schema_version",
    "envelope_id",
    "scope",
    "request",
    "dossier",
    "requested_candidate_id",
    "minimum_distinct_reviewers",
    "review_count",
    "distinct_reviewer_count",
    "decision_counts",
    "status",
    "reviews",
    "deployment_authorized",
    "trading_authorized",
    "release_authorized",
    "assumptions",
    "evidence_boundary",
}
_REVIEW_FIELDS = {
    "record_id",
    "record_sha256",
    "reviewer_subject",
    "reviewer_key_id",
    "decision",
    "reviewed_at",
}


class _DuplicateJsonKey(ValueError):
    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class SignedInput:
    path: Path
    attestation: Path
    trusted_public_key: Path


@dataclass(frozen=True, slots=True)
class ReviewInput:
    record: Path
    attestation: Path
    trusted_public_key: Path


@dataclass(frozen=True, slots=True)
class ReviewQuorumSpec:
    minimum_distinct_reviewers: int
    request: SignedInput
    dossier: SignedInput
    reviews: tuple[ReviewInput, ...]
    scope: str = _SCOPE
    deployment_authorized: bool = False
    trading_authorized: bool = False
    release_authorized: bool = False

    def __post_init__(self) -> None:
        if not 2 <= self.minimum_distinct_reviewers <= 64:
            raise ValueError("minimum_distinct_reviewers must be in [2, 64]")
        if not 1 <= len(self.reviews) <= 64:
            raise ValueError("reviews must contain between 1 and 64 entries")
        if self.scope != _SCOPE:
            raise ValueError(f"review quorum scope must be {_SCOPE}")
        if self.deployment_authorized:
            raise ValueError("review quorum input cannot authorize deployment")
        if self.trading_authorized:
            raise ValueError("review quorum input cannot authorize trading")
        if self.release_authorized:
            raise ValueError("review quorum input cannot authorize release")


@dataclass(frozen=True, slots=True)
class ReviewQuorumInputSnapshot:
    source_path: Path
    spec: ReviewQuorumSpec
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "scope": self.spec.scope,
            "minimum_distinct_reviewers": self.spec.minimum_distinct_reviewers,
            "review_count": len(self.spec.reviews),
            "deployment_authorized": False,
            "trading_authorized": False,
            "release_authorized": False,
        }


@dataclass(frozen=True, slots=True)
class QuorumReviewEvidence:
    record_id: str
    record_sha256: str
    reviewer_subject: str
    reviewer_key_id: str
    decision: str
    reviewed_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "record_sha256": self.record_sha256,
            "reviewer_subject": self.reviewer_subject,
            "reviewer_key_id": self.reviewer_key_id,
            "decision": self.decision,
            "reviewed_at": self.reviewed_at,
        }


@dataclass(frozen=True, slots=True)
class ReviewQuorumEnvelope:
    envelope_id: str
    request_id: str
    request_sha256: str
    requester_key_id: str
    dossier_id: str
    dossier_sha256: str
    dossier_key_id: str
    requested_candidate_id: str
    minimum_distinct_reviewers: int
    status: str
    reviews: tuple[QuorumReviewEvidence, ...]
    scope: str = _SCOPE

    @property
    def participant_key_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    self.requester_key_id,
                    self.dossier_key_id,
                    *(review.reviewer_key_id for review in self.reviews),
                }
            )
        )

    def as_dict(self) -> dict[str, Any]:
        counts = _decision_counts(self.reviews)
        return {
            "schema_version": _ENVELOPE_SCHEMA_VERSION,
            "envelope_id": self.envelope_id,
            "scope": self.scope,
            "request": {
                "request_id": self.request_id,
                "canonical_sha256": self.request_sha256,
                "requester_key_id": self.requester_key_id,
            },
            "dossier": {
                "dossier_id": self.dossier_id,
                "sha256": self.dossier_sha256,
                "dossier_key_id": self.dossier_key_id,
            },
            "requested_candidate_id": self.requested_candidate_id,
            "minimum_distinct_reviewers": self.minimum_distinct_reviewers,
            "review_count": len(self.reviews),
            "distinct_reviewer_count": len(
                {review.reviewer_key_id for review in self.reviews}
            ),
            "decision_counts": counts,
            "status": self.status,
            "reviews": [review.as_dict() for review in self.reviews],
            "deployment_authorized": False,
            "trading_authorized": False,
            "release_authorized": False,
            "assumptions": [
                (
                    "Reject is a veto; otherwise defer is a hold; only an all-approve "
                    "set meeting the declared distinct-reviewer minimum can become "
                    "approved_for_research_only."
                ),
                (
                    "Approved_for_research_only authorizes only further offline human-"
                    "supervised research and never release, deployment, or trading."
                ),
                (
                    "Cryptographic key separation does not prove legal identity or "
                    "organizational independence."
                ),
            ],
            "evidence_boundary": (
                "This envelope binds independently signed research-review records to "
                "one signed request and one signed offline dossier. It does not prove "
                "source-market truth, causal alpha, future profitability, legal approval, "
                "release readiness, deployment authority, or live-trading authority."
            ),
        }


@dataclass(frozen=True, slots=True)
class ReviewQuorumEnvelopeSnapshot:
    source_path: Path
    envelope: ReviewQuorumEnvelope
    source_sha256: str

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "envelope_id": self.envelope.envelope_id,
            "status": self.envelope.status,
            "requested_candidate_id": self.envelope.requested_candidate_id,
            "review_count": len(self.envelope.reviews),
            "minimum_distinct_reviewers": (
                self.envelope.minimum_distinct_reviewers
            ),
            "deployment_authorized": False,
            "trading_authorized": False,
            "release_authorized": False,
        }


def load_review_quorum_inputs(path: Path) -> ReviewQuorumInputSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: review quorum inputs are not valid UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid review-quorum YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("review quorum inputs must be a mapping")
    payload = cast(dict[str, Any], parsed)
    _require_fields(
        "review quorum inputs",
        payload,
        {
            "schema_version",
            "scope",
            "minimum_distinct_reviewers",
            "request",
            "dossier",
            "reviews",
            "deployment_authorized",
            "trading_authorized",
            "release_authorized",
        },
    )
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _INPUT_SCHEMA_VERSION:
        raise ValueError("review quorum inputs schema_version must be 1")
    root = resolved.parent
    request = _signed_input(root, payload.get("request"), "request")
    dossier = _signed_input(root, payload.get("dossier"), "dossier")
    raw_reviews = payload.get("reviews")
    if not isinstance(raw_reviews, list):
        raise ValueError("review quorum inputs reviews must be a list")
    reviews = tuple(
        _review_input(root, value, index)
        for index, value in enumerate(raw_reviews)
    )
    spec = ReviewQuorumSpec(
        minimum_distinct_reviewers=_integer(
            payload.get("minimum_distinct_reviewers"),
            "review quorum minimum_distinct_reviewers",
            minimum=2,
        ),
        request=request,
        dossier=dossier,
        reviews=reviews,
        scope=_string(payload.get("scope"), "review quorum scope"),
        deployment_authorized=_boolean(
            payload.get("deployment_authorized"),
            "review quorum deployment_authorized",
        ),
        trading_authorized=_boolean(
            payload.get("trading_authorized"),
            "review quorum trading_authorized",
        ),
        release_authorized=_boolean(
            payload.get("release_authorized"),
            "review quorum release_authorized",
        ),
    )
    canonical_payload = {
        "schema_version": _INPUT_SCHEMA_VERSION,
        "scope": spec.scope,
        "minimum_distinct_reviewers": spec.minimum_distinct_reviewers,
        "request": _signed_input_payload(spec.request),
        "dossier": _signed_input_payload(spec.dossier),
        "reviews": [_review_input_payload(review) for review in spec.reviews],
        "deployment_authorized": False,
        "trading_authorized": False,
        "release_authorized": False,
    }
    canonical_bytes = canonical_json_bytes(canonical_payload) + b"\n"
    return ReviewQuorumInputSnapshot(
        source_path=resolved,
        spec=spec,
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=sha256_hex(canonical_bytes),
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def build_review_quorum(inputs_path: Path) -> ReviewQuorumEnvelope:
    inputs = load_review_quorum_inputs(inputs_path)
    spec = inputs.spec
    request = load_decision_request(spec.request.path)
    request_attestation = verify_decision_request_attestation(
        spec.request.path,
        spec.request.attestation,
        trusted_public_key_path=spec.request.trusted_public_key,
    )
    dossier = load_selection_dossier(spec.dossier.path)
    dossier_attestation = verify_selection_dossier_attestation(
        spec.dossier.path,
        spec.dossier.attestation,
        trusted_public_key_path=spec.dossier.trusted_public_key,
    )
    request_value = request.request
    dossier_value = dossier.dossier
    if request_value.dossier.dossier_id != dossier_value.dossier_id:
        raise ValueError("review quorum request dossier_id does not match dossier")
    if request_value.dossier.sha256 != dossier.source_sha256:
        raise ValueError("review quorum request dossier hash does not match dossier")
    candidate_id = request_value.requested_candidate_id
    if candidate_id not in dossier_value.eligible_candidate_ids:
        raise ValueError("review quorum candidate is not eligible for human review")
    if candidate_id in dossier_value.blocked_candidate_ids:
        raise ValueError("review quorum candidate is blocked by the dossier")
    if request_attestation.key_id == dossier_attestation.key_id:
        raise ValueError("requester and dossier provenance keys must differ")

    evidence: list[QuorumReviewEvidence] = []
    record_ids: set[str] = set()
    reviewer_keys: set[str] = set()
    reviewer_subjects: set[str] = set()
    for review_input in spec.reviews:
        verified = verify_review_record_attestation(
            record_path=review_input.record,
            attestation_path=review_input.attestation,
            trusted_reviewer_public_key_path=review_input.trusted_public_key,
            request_path=spec.request.path,
            request_attestation_path=spec.request.attestation,
            trusted_requester_public_key_path=spec.request.trusted_public_key,
            dossier_path=spec.dossier.path,
            dossier_attestation_path=spec.dossier.attestation,
            trusted_dossier_public_key_path=spec.dossier.trusted_public_key,
        )
        record = load_review_record(review_input.record)
        record_value = record.record
        if verified.record_id in record_ids:
            raise ValueError(f"duplicate review record: {verified.record_id}")
        if verified.reviewer_key_id in reviewer_keys:
            raise ValueError(f"duplicate reviewer key: {verified.reviewer_key_id}")
        if record_value.reviewer.subject in reviewer_subjects:
            raise ValueError(
                f"duplicate reviewer subject: {record_value.reviewer.subject}"
            )
        record_ids.add(verified.record_id)
        reviewer_keys.add(verified.reviewer_key_id)
        reviewer_subjects.add(record_value.reviewer.subject)
        reviewed_at = record_value.reviewed_at.isoformat(timespec="microseconds").replace(
            "+00:00",
            "Z",
        )
        evidence.append(
            QuorumReviewEvidence(
                record_id=verified.record_id,
                record_sha256=verified.record_sha256,
                reviewer_subject=record_value.reviewer.subject,
                reviewer_key_id=verified.reviewer_key_id,
                decision=verified.decision,
                reviewed_at=reviewed_at,
            )
        )
    reviews = tuple(sorted(evidence, key=lambda item: (item.reviewer_key_id, item.record_id)))
    status = _quorum_status(reviews, spec.minimum_distinct_reviewers)
    identity = {
        "schema_version": _ENVELOPE_SCHEMA_VERSION,
        "scope": _SCOPE,
        "request": {
            "request_id": request.request_id,
            "canonical_sha256": request.canonical_sha256,
            "requester_key_id": request_attestation.key_id,
        },
        "dossier": {
            "dossier_id": dossier_value.dossier_id,
            "sha256": dossier.source_sha256,
            "dossier_key_id": dossier_attestation.key_id,
        },
        "requested_candidate_id": candidate_id,
        "minimum_distinct_reviewers": spec.minimum_distinct_reviewers,
        "status": status,
        "reviews": [review.as_dict() for review in reviews],
        "deployment_authorized": False,
        "trading_authorized": False,
        "release_authorized": False,
    }
    envelope_id = "review-quorum-" + sha256_hex(canonical_json_bytes(identity))[:40]
    return ReviewQuorumEnvelope(
        envelope_id=envelope_id,
        request_id=request.request_id,
        request_sha256=request.canonical_sha256,
        requester_key_id=request_attestation.key_id,
        dossier_id=dossier_value.dossier_id,
        dossier_sha256=dossier.source_sha256,
        dossier_key_id=dossier_attestation.key_id,
        requested_candidate_id=candidate_id,
        minimum_distinct_reviewers=spec.minimum_distinct_reviewers,
        status=status,
        reviews=reviews,
    )


def load_review_quorum_envelope(path: Path) -> ReviewQuorumEnvelopeSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    payload = _json_object(source_bytes, "review quorum envelope")
    if set(payload) != _ENVELOPE_FIELDS:
        raise ValueError("review quorum envelope contains unknown or missing fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _ENVELOPE_SCHEMA_VERSION:
        raise ValueError("review quorum envelope schema_version must be 1")
    envelope_id = _identifier(
        payload.get("envelope_id"),
        "review-quorum-",
        "review quorum envelope_id",
    )
    scope = _string(payload.get("scope"), "review quorum scope")
    if scope != _SCOPE:
        raise ValueError(f"review quorum scope must be {_SCOPE}")
    request = _object(payload.get("request"), "review quorum request")
    dossier = _object(payload.get("dossier"), "review quorum dossier")
    _require_fields(
        "review quorum request",
        request,
        {"request_id", "canonical_sha256", "requester_key_id"},
    )
    _require_fields(
        "review quorum dossier",
        dossier,
        {"dossier_id", "sha256", "dossier_key_id"},
    )
    request_id = _identifier(
        request.get("request_id"),
        "decision-request-",
        "review quorum request_id",
    )
    request_sha = _digest_value(
        request.get("canonical_sha256"),
        "review quorum request canonical_sha256",
    )
    requester_key = _key_id(request.get("requester_key_id"), "requester_key_id")
    dossier_id = _identifier(
        dossier.get("dossier_id"),
        "selection-dossier-",
        "review quorum dossier_id",
    )
    dossier_sha = _digest_value(dossier.get("sha256"), "review quorum dossier sha256")
    dossier_key = _key_id(dossier.get("dossier_key_id"), "dossier_key_id")
    candidate_id = _candidate_id(
        _string(payload.get("requested_candidate_id"), "requested_candidate_id")
    )
    minimum = _integer(
        payload.get("minimum_distinct_reviewers"),
        "review quorum minimum_distinct_reviewers",
        minimum=2,
    )
    status = _string(payload.get("status"), "review quorum status")
    if status not in _STATUSES:
        raise ValueError("review quorum status is invalid")
    raw_reviews = payload.get("reviews")
    if not isinstance(raw_reviews, list) or not raw_reviews:
        raise ValueError("review quorum reviews must be a non-empty list")
    reviews = tuple(_review_evidence(value, index) for index, value in enumerate(raw_reviews))
    expected_order = tuple(sorted(reviews, key=lambda item: (item.reviewer_key_id, item.record_id)))
    if reviews != expected_order:
        raise ValueError("review quorum reviews must use lexical reviewer-key order")
    if len({item.record_id for item in reviews}) != len(reviews):
        raise ValueError("review quorum contains duplicate review records")
    if len({item.reviewer_key_id for item in reviews}) != len(reviews):
        raise ValueError("review quorum contains duplicate reviewer keys")
    if len({item.reviewer_subject for item in reviews}) != len(reviews):
        raise ValueError("review quorum contains duplicate reviewer subjects")
    if requester_key == dossier_key:
        raise ValueError("requester and dossier provenance keys must differ")
    if any(item.reviewer_key_id in {requester_key, dossier_key} for item in reviews):
        raise ValueError("reviewer keys must differ from requester and dossier keys")
    if _integer(payload.get("review_count"), "review_count", minimum=1) != len(reviews):
        raise ValueError("review quorum review_count does not match reviews")
    distinct = _integer(
        payload.get("distinct_reviewer_count"),
        "distinct_reviewer_count",
        minimum=1,
    )
    if distinct != len({item.reviewer_key_id for item in reviews}):
        raise ValueError("review quorum distinct reviewer count is invalid")
    if payload.get("decision_counts") != _decision_counts(reviews):
        raise ValueError("review quorum decision counts do not match reviews")
    if status != _quorum_status(reviews, minimum):
        raise ValueError("review quorum status does not match review evidence")
    for key in (
        "deployment_authorized",
        "trading_authorized",
        "release_authorized",
    ):
        if payload.get(key) is not False:
            raise ValueError(f"review quorum {key} must remain false")
    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, list) or not all(
        isinstance(item, str) and item for item in assumptions
    ):
        raise ValueError("review quorum assumptions are invalid")
    _string(payload.get("evidence_boundary"), "review quorum evidence_boundary")

    identity = {
        "schema_version": _ENVELOPE_SCHEMA_VERSION,
        "scope": scope,
        "request": {
            "request_id": request_id,
            "canonical_sha256": request_sha,
            "requester_key_id": requester_key,
        },
        "dossier": {
            "dossier_id": dossier_id,
            "sha256": dossier_sha,
            "dossier_key_id": dossier_key,
        },
        "requested_candidate_id": candidate_id,
        "minimum_distinct_reviewers": minimum,
        "status": status,
        "reviews": [review.as_dict() for review in reviews],
        "deployment_authorized": False,
        "trading_authorized": False,
        "release_authorized": False,
    }
    expected_id = "review-quorum-" + sha256_hex(canonical_json_bytes(identity))[:40]
    if envelope_id != expected_id:
        raise ValueError("review quorum envelope_id does not match evidence")
    envelope = ReviewQuorumEnvelope(
        envelope_id=envelope_id,
        request_id=request_id,
        request_sha256=request_sha,
        requester_key_id=requester_key,
        dossier_id=dossier_id,
        dossier_sha256=dossier_sha,
        dossier_key_id=dossier_key,
        requested_candidate_id=candidate_id,
        minimum_distinct_reviewers=minimum,
        status=status,
        reviews=reviews,
    )
    if payload != envelope.as_dict():
        raise ValueError("review quorum envelope is not canonical schema-v1 evidence")
    canonical = canonical_json_bytes(payload) + b"\n"
    if source_bytes != canonical:
        raise ValueError("review quorum envelope must use canonical JSON encoding")
    return ReviewQuorumEnvelopeSnapshot(
        source_path=resolved,
        envelope=envelope,
        source_sha256=sha256_hex(source_bytes),
    )


def _quorum_status(
    reviews: tuple[QuorumReviewEvidence, ...],
    minimum_distinct_reviewers: int,
) -> str:
    decisions = {review.decision for review in reviews}
    if "reject" in decisions:
        return "rejected"
    if "defer" in decisions:
        return "deferred"
    distinct = len({review.reviewer_key_id for review in reviews})
    if (
        reviews
        and decisions == {"approve_research_only"}
        and distinct >= minimum_distinct_reviewers
    ):
        return "approved_for_research_only"
    return "blocked"


def _decision_counts(reviews: tuple[QuorumReviewEvidence, ...]) -> dict[str, int]:
    return {
        "approve_research_only": sum(
            review.decision == "approve_research_only" for review in reviews
        ),
        "defer": sum(review.decision == "defer" for review in reviews),
        "reject": sum(review.decision == "reject" for review in reviews),
    }


def _signed_input(root: Path, value: Any, name: str) -> SignedInput:
    payload = _object(value, f"review quorum {name}")
    _require_fields(
        f"review quorum {name}",
        payload,
        {"path", "attestation", "trusted_public_key"},
    )
    result = SignedInput(
        path=_existing_file(root, payload.get("path"), f"{name} path"),
        attestation=_existing_file(
            root,
            payload.get("attestation"),
            f"{name} attestation",
        ),
        trusted_public_key=_existing_file(
            root,
            payload.get("trusted_public_key"),
            f"{name} trusted_public_key",
        ),
    )
    return result


def _review_input(root: Path, value: Any, index: int) -> ReviewInput:
    payload = _object(value, f"review quorum review {index}")
    _require_fields(
        f"review quorum review {index}",
        payload,
        {"record", "attestation", "trusted_public_key"},
    )
    return ReviewInput(
        record=_existing_file(root, payload.get("record"), f"review {index} record"),
        attestation=_existing_file(
            root,
            payload.get("attestation"),
            f"review {index} attestation",
        ),
        trusted_public_key=_existing_file(
            root,
            payload.get("trusted_public_key"),
            f"review {index} trusted_public_key",
        ),
    )


def _signed_input_payload(value: SignedInput) -> dict[str, str]:
    return {
        "path": str(value.path),
        "attestation": str(value.attestation),
        "trusted_public_key": str(value.trusted_public_key),
    }


def _review_input_payload(value: ReviewInput) -> dict[str, str]:
    return {
        "record": str(value.record),
        "attestation": str(value.attestation),
        "trusted_public_key": str(value.trusted_public_key),
    }


def _review_evidence(value: Any, index: int) -> QuorumReviewEvidence:
    payload = _object(value, f"review quorum evidence {index}")
    if set(payload) != _REVIEW_FIELDS:
        raise ValueError(f"review quorum evidence {index} contains invalid fields")
    decision = _string(payload.get("decision"), "review decision")
    if decision not in {"approve_research_only", "defer", "reject"}:
        raise ValueError("review quorum contains an invalid decision")
    return QuorumReviewEvidence(
        record_id=_identifier(
            payload.get("record_id"),
            "review-record-",
            "review record_id",
        ),
        record_sha256=_digest_value(
            payload.get("record_sha256"),
            "review record_sha256",
        ),
        reviewer_subject=_string(payload.get("reviewer_subject"), "reviewer_subject"),
        reviewer_key_id=_key_id(payload.get("reviewer_key_id"), "reviewer_key_id"),
        decision=decision,
        reviewed_at=_string(payload.get("reviewed_at"), "reviewed_at"),
    )


def _existing_file(root: Path, value: Any, name: str) -> Path:
    text = _string(value, name)
    path = Path(text)
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_file():
        raise ValueError(f"review quorum {name} is not a file: {resolved}")
    return resolved


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return cast(dict[str, Any], value)


def _require_fields(name: str, payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    missing = sorted(allowed - set(payload))
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"{name} is missing fields: {', '.join(missing)}")


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _identifier(value: Any, prefix: str, name: str) -> str:
    text = _string(value, name)
    suffix = text.removeprefix(prefix)
    if (
        not text.startswith(prefix)
        or len(suffix) != 40
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError(f"{name} must use {prefix}<40 lowercase hex>")
    return text


def _digest_value(value: Any, name: str) -> str:
    text = _string(value, name)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
    return text


def _key_id(value: Any, name: str) -> str:
    text = _string(value, name)
    suffix = text.removeprefix("ed25519-")
    if (
        not text.startswith("ed25519-")
        or len(suffix) != 32
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError(f"{name} must use ed25519-<32 lowercase hex>")
    return text


def _candidate_id(value: str) -> str:
    if (
        not value.startswith("candidate-")
        or len(value) <= len("candidate-")
        or len(value) > 160
        or value != value.strip()
    ):
        raise ValueError("requested_candidate_id must use a non-empty candidate-* value")
    return value


def _json_object(value: bytes, name: str) -> dict[str, Any]:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{name} is not valid UTF-8") from error
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_json_object,
            parse_constant=lambda constant: _raise_non_finite(name, constant),
        )
    except _DuplicateJsonKey as error:
        raise ValueError(f"duplicate {name} JSON key: {error.key}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid {name} JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return cast(dict[str, Any], parsed)


def _raise_non_finite(name: str, value: str) -> None:
    raise ValueError(f"{name} contains a non-finite number: {value}")
