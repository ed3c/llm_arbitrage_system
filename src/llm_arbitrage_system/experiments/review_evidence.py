from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import yaml
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.decision_request import (
    DecisionRequestSnapshot,
    load_decision_request,
)
from llm_arbitrage_system.experiments.decision_request_signing import (
    DecisionRequestAttestationResult,
    verify_decision_request_attestation,
)
from llm_arbitrage_system.experiments.selection_dossier import (
    SelectionDossierSnapshot,
    load_selection_dossier,
)
from llm_arbitrage_system.experiments.selection_signing import (
    SelectionDossierAttestationResult,
    verify_selection_dossier_attestation,
)
from llm_arbitrage_system.experiments.signing import (
    load_private_key,
    load_public_key,
    public_key_identity,
)
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_REVIEW_SCHEMA_VERSION = 1
_ATTESTATION_SCHEMA_VERSION = 1
_ALGORITHM = "Ed25519"
_REVIEWER_ROLE = "independent_reviewer"
_DECISIONS = frozenset({"approve_research_only", "defer", "reject"})
_REQUIRED_ACKNOWLEDGEMENTS = frozenset(
    {
        "decision_is_research_only",
        "deployment_not_authorized",
        "future_profitability_unproven",
        "human_accountability_retained",
        "live_trading_not_authorized",
        "source_market_truth_unverified",
    }
)


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
class ReviewReference:
    identifier: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ReviewerIdentity:
    subject: str
    role: str = _REVIEWER_ROLE

    def __post_init__(self) -> None:
        _bounded_text(
            self.subject,
            "review record reviewer.subject",
            minimum=1,
            maximum=256,
        )
        if self.role != _REVIEWER_ROLE:
            raise ValueError(f"review record reviewer.role must be {_REVIEWER_ROLE}")


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    request: ReviewReference
    dossier: ReviewReference
    requested_candidate_id: str
    decision: str
    reviewer: ReviewerIdentity
    rationale: str
    reviewed_at: datetime
    risk_acknowledgements: tuple[str, ...]
    deployment_authorized: bool = False
    trading_authorized: bool = False

    def __post_init__(self) -> None:
        _prefixed_identifier(
            self.request.identifier,
            "decision-request-",
            "review record request_id",
        )
        _digest(self.request.sha256, "review record request sha256")
        _prefixed_identifier(
            self.dossier.identifier,
            "selection-dossier-",
            "review record dossier_id",
        )
        _digest(self.dossier.sha256, "review record dossier sha256")
        _candidate_id(self.requested_candidate_id)
        if self.decision not in _DECISIONS:
            raise ValueError(
                "review record decision must be approve_research_only, reject, or defer"
            )
        _bounded_text(
            self.rationale,
            "review record rationale",
            minimum=20,
            maximum=4000,
        )
        _aware_utc(self.reviewed_at, "review record reviewed_at")
        acknowledgements = tuple(sorted(self.risk_acknowledgements))
        if len(set(acknowledgements)) != len(acknowledgements):
            raise ValueError("review record risk acknowledgements cannot contain duplicates")
        values = set(acknowledgements)
        missing = sorted(_REQUIRED_ACKNOWLEDGEMENTS - values)
        unknown = sorted(values - _REQUIRED_ACKNOWLEDGEMENTS)
        if missing:
            raise ValueError(
                "review record is missing risk acknowledgements: "
                + ", ".join(missing)
            )
        if unknown:
            raise ValueError(
                "review record contains unknown risk acknowledgements: "
                + ", ".join(unknown)
            )
        if self.deployment_authorized:
            raise ValueError("review record cannot authorize deployment")
        if self.trading_authorized:
            raise ValueError("review record cannot authorize trading")


@dataclass(frozen=True, slots=True)
class ReviewRecordSnapshot:
    source_path: Path
    record: ReviewRecord
    record_id: str
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "record_id": self.record_id,
            "record": review_record_payload(self.record),
        }


@dataclass(frozen=True, slots=True)
class ReviewEvidenceAttestationResult:
    attestation_path: Path
    record_path: Path
    record_id: str
    record_sha256: str
    request_id: str
    dossier_id: str
    requested_candidate_id: str
    decision: str
    reviewer_key_id: str
    requester_key_id: str
    dossier_key_id: str
    public_key_base64: str
    trusted_key_matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "attestation_path": str(self.attestation_path),
            "record_path": str(self.record_path),
            "record_id": self.record_id,
            "record_sha256": self.record_sha256,
            "request_id": self.request_id,
            "dossier_id": self.dossier_id,
            "requested_candidate_id": self.requested_candidate_id,
            "decision": self.decision,
            "reviewer_key_id": self.reviewer_key_id,
            "requester_key_id": self.requester_key_id,
            "dossier_key_id": self.dossier_key_id,
            "public_key_base64": self.public_key_base64,
            "trusted_key_matched": self.trusted_key_matched,
            "deployment_authorized": False,
            "trading_authorized": False,
        }


@dataclass(frozen=True, slots=True)
class _ReviewContext:
    record: ReviewRecordSnapshot
    request: DecisionRequestSnapshot
    request_attestation: DecisionRequestAttestationResult
    dossier: SelectionDossierSnapshot
    dossier_attestation: SelectionDossierAttestationResult


def load_review_record(path: Path) -> ReviewRecordSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: review record is not valid UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid review-record YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("review record must be a mapping")
    record = parse_review_record(cast(dict[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(review_record_payload(record)) + b"\n"
    canonical_sha256 = sha256_hex(canonical_bytes)
    return ReviewRecordSnapshot(
        source_path=resolved,
        record=record,
        record_id=f"review-record-{canonical_sha256[:40]}",
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=canonical_sha256,
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_review_record(payload: dict[str, Any]) -> ReviewRecord:
    _reject_exact_fields(
        "review record",
        payload,
        {
            "schema_version",
            "request",
            "dossier",
            "requested_candidate_id",
            "decision",
            "reviewer",
            "rationale",
            "reviewed_at",
            "risk_acknowledgements",
            "deployment_authorized",
            "trading_authorized",
        },
    )
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _REVIEW_SCHEMA_VERSION:
        raise ValueError("review record schema_version must be 1")
    request = _mapping(payload.get("request"), "review record request")
    dossier = _mapping(payload.get("dossier"), "review record dossier")
    reviewer = _mapping(payload.get("reviewer"), "review record reviewer")
    _reject_exact_fields(
        "review record request",
        request,
        {"request_id", "canonical_sha256"},
    )
    _reject_exact_fields(
        "review record dossier",
        dossier,
        {"dossier_id", "sha256"},
    )
    _reject_exact_fields(
        "review record reviewer",
        reviewer,
        {"subject", "role"},
    )
    return ReviewRecord(
        request=ReviewReference(
            identifier=_required_string(
                request.get("request_id"),
                "review record request_id",
            ),
            sha256=_required_string(
                request.get("canonical_sha256"),
                "review record request canonical_sha256",
            ),
        ),
        dossier=ReviewReference(
            identifier=_required_string(
                dossier.get("dossier_id"),
                "review record dossier_id",
            ),
            sha256=_required_string(
                dossier.get("sha256"),
                "review record dossier sha256",
            ),
        ),
        requested_candidate_id=_required_string(
            payload.get("requested_candidate_id"),
            "review record requested_candidate_id",
        ),
        decision=_required_string(
            payload.get("decision"),
            "review record decision",
        ),
        reviewer=ReviewerIdentity(
            subject=_required_string(
                reviewer.get("subject"),
                "review record reviewer.subject",
            ),
            role=_required_string(
                reviewer.get("role"),
                "review record reviewer.role",
            ),
        ),
        rationale=_bounded_text(
            payload.get("rationale"),
            "review record rationale",
            minimum=20,
            maximum=4000,
        ),
        reviewed_at=_timestamp(
            payload.get("reviewed_at"),
            "review record reviewed_at",
        ),
        risk_acknowledgements=_string_tuple(
            payload.get("risk_acknowledgements"),
            "review record risk_acknowledgements",
        ),
        deployment_authorized=_required_boolean(
            payload.get("deployment_authorized"),
            "review record deployment_authorized",
        ),
        trading_authorized=_required_boolean(
            payload.get("trading_authorized"),
            "review record trading_authorized",
        ),
    )


def review_record_payload(record: ReviewRecord) -> dict[str, Any]:
    return {
        "schema_version": _REVIEW_SCHEMA_VERSION,
        "request": {
            "request_id": record.request.identifier,
            "canonical_sha256": record.request.sha256,
        },
        "dossier": {
            "dossier_id": record.dossier.identifier,
            "sha256": record.dossier.sha256,
        },
        "requested_candidate_id": record.requested_candidate_id,
        "decision": record.decision,
        "reviewer": {
            "subject": record.reviewer.subject.strip(),
            "role": record.reviewer.role,
        },
        "rationale": record.rationale.strip(),
        "reviewed_at": _timestamp_text(record.reviewed_at),
        "risk_acknowledgements": sorted(record.risk_acknowledgements),
        "deployment_authorized": False,
        "trading_authorized": False,
    }


def sign_review_record(
    *,
    record_path: Path,
    request_path: Path,
    request_attestation_path: Path,
    trusted_requester_public_key_path: Path,
    dossier_path: Path,
    dossier_attestation_path: Path,
    trusted_dossier_public_key_path: Path,
    reviewer_private_key_path: Path,
    output_path: Path,
    force: bool = False,
) -> dict[str, Any]:
    context = _review_context(
        record_path=record_path,
        request_path=request_path,
        request_attestation_path=request_attestation_path,
        trusted_requester_public_key_path=trusted_requester_public_key_path,
        dossier_path=dossier_path,
        dossier_attestation_path=dossier_attestation_path,
        trusted_dossier_public_key_path=trusted_dossier_public_key_path,
    )
    private_path = reviewer_private_key_path.resolve()
    output = output_path.resolve()
    _reject_equal(context.record.source_path, private_path, "reviewer private key")
    _reject_equal(context.record.source_path, output, "review attestation")
    _reject_equal(private_path, output, "review attestation")
    if output.exists() and not force:
        raise FileExistsError(f"review attestation already exists: {output}")

    private_key = load_private_key(private_path)
    identity = public_key_identity(private_key.public_key())
    _require_independent_reviewer(identity.key_id, context)
    payload = {
        "schema_version": _ATTESTATION_SCHEMA_VERSION,
        "algorithm": _ALGORITHM,
        "key_id": identity.key_id,
        "public_key_base64": identity.public_key_base64,
        "review": _review_identity(context),
        "evidence_boundary": (
            "This detached signature authenticates an externally authored research-"
            "only review record. It does not prove legal identity, authorize release, "
            "authorize deployment, or authorize live trading."
        ),
    }
    signature = private_key.sign(canonical_json_bytes(payload))
    document = {
        "payload": payload,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    write_json(output, document)
    return document


def verify_review_record_attestation(
    *,
    record_path: Path,
    attestation_path: Path,
    trusted_reviewer_public_key_path: Path,
    request_path: Path,
    request_attestation_path: Path,
    trusted_requester_public_key_path: Path,
    dossier_path: Path,
    dossier_attestation_path: Path,
    trusted_dossier_public_key_path: Path,
) -> ReviewEvidenceAttestationResult:
    context = _review_context(
        record_path=record_path,
        request_path=request_path,
        request_attestation_path=request_attestation_path,
        trusted_requester_public_key_path=trusted_requester_public_key_path,
        dossier_path=dossier_path,
        dossier_attestation_path=dossier_attestation_path,
        trusted_dossier_public_key_path=trusted_dossier_public_key_path,
    )
    attestation = attestation_path.resolve()
    document = _load_attestation(attestation)
    payload = cast(dict[str, Any], document["payload"])
    if set(payload) != {
        "schema_version",
        "algorithm",
        "key_id",
        "public_key_base64",
        "review",
        "evidence_boundary",
    }:
        raise ValueError("review attestation contains unexpected fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _ATTESTATION_SCHEMA_VERSION:
        raise ValueError("review attestation schema_version must be 1")
    if payload.get("algorithm") != _ALGORITHM:
        raise ValueError("review attestation algorithm must be Ed25519")
    _required_string(payload.get("evidence_boundary"), "review evidence boundary")

    raw_public_key = _decode_base64(
        _required_string(
            payload.get("public_key_base64"),
            "review attestation public_key_base64",
        ),
        "review attestation public_key_base64",
    )
    if len(raw_public_key) != 32:
        raise ValueError("review attestation public key must be 32 raw bytes")
    public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
    identity = public_key_identity(public_key)
    key_id = _required_string(payload.get("key_id"), "review attestation key_id")
    if key_id != identity.key_id:
        raise ValueError("review attestation key_id does not match public key")
    trusted = public_key_identity(load_public_key(trusted_reviewer_public_key_path))
    if (
        trusted.key_id != key_id
        or trusted.public_key_base64 != identity.public_key_base64
    ):
        raise ValueError("review attestation signer does not match trusted public key")
    _require_independent_reviewer(key_id, context)

    signature = _decode_base64(
        cast(str, document["signature_base64"]),
        "review attestation signature_base64",
    )
    try:
        public_key.verify(signature, canonical_json_bytes(payload))
    except InvalidSignature as error:
        raise ValueError("review attestation signature is invalid") from error
    review_payload = payload.get("review")
    if not isinstance(review_payload, dict):
        raise ValueError("review attestation review identity must be an object")
    expected = _review_identity(context)
    if cast(dict[str, Any], review_payload) != expected:
        raise ValueError("review attestation does not match current review evidence")

    record = context.record.record
    return ReviewEvidenceAttestationResult(
        attestation_path=attestation,
        record_path=context.record.source_path,
        record_id=context.record.record_id,
        record_sha256=context.record.canonical_sha256,
        request_id=context.request.request_id,
        dossier_id=context.dossier.dossier.dossier_id,
        requested_candidate_id=record.requested_candidate_id,
        decision=record.decision,
        reviewer_key_id=key_id,
        requester_key_id=context.request_attestation.key_id,
        dossier_key_id=context.dossier_attestation.key_id,
        public_key_base64=identity.public_key_base64,
        trusted_key_matched=True,
    )


def _review_context(
    *,
    record_path: Path,
    request_path: Path,
    request_attestation_path: Path,
    trusted_requester_public_key_path: Path,
    dossier_path: Path,
    dossier_attestation_path: Path,
    trusted_dossier_public_key_path: Path,
) -> _ReviewContext:
    request = load_decision_request(request_path)
    request_attestation = verify_decision_request_attestation(
        request_path,
        request_attestation_path,
        trusted_public_key_path=trusted_requester_public_key_path,
    )
    dossier = load_selection_dossier(dossier_path)
    dossier_attestation = verify_selection_dossier_attestation(
        dossier_path,
        dossier_attestation_path,
        trusted_public_key_path=trusted_dossier_public_key_path,
    )
    record = load_review_record(record_path)
    _validate_context(record, request, dossier)
    return _ReviewContext(
        record=record,
        request=request,
        request_attestation=request_attestation,
        dossier=dossier,
        dossier_attestation=dossier_attestation,
    )


def _validate_context(
    record: ReviewRecordSnapshot,
    request: DecisionRequestSnapshot,
    dossier: SelectionDossierSnapshot,
) -> None:
    request_value = request.request
    dossier_value = dossier.dossier
    record_value = record.record
    if request_value.dossier.dossier_id != dossier_value.dossier_id:
        raise ValueError("decision request dossier_id does not match dossier")
    if request_value.dossier.sha256 != dossier.source_sha256:
        raise ValueError("decision request dossier hash does not match dossier")
    if record_value.request.identifier != request.request_id:
        raise ValueError("review record request_id does not match request")
    if record_value.request.sha256 != request.canonical_sha256:
        raise ValueError("review record request hash does not match request")
    if record_value.dossier.identifier != dossier_value.dossier_id:
        raise ValueError("review record dossier_id does not match dossier")
    if record_value.dossier.sha256 != dossier.source_sha256:
        raise ValueError("review record dossier hash does not match dossier")
    if record_value.requested_candidate_id != request_value.requested_candidate_id:
        raise ValueError("review record candidate does not match request")
    if record_value.requested_candidate_id not in dossier_value.eligible_candidate_ids:
        raise ValueError("requested candidate is not eligible for human review")
    if record_value.requested_candidate_id in dossier_value.blocked_candidate_ids:
        raise ValueError("requested candidate is blocked by the dossier")
    reviewed_at = _aware_utc(record_value.reviewed_at, "review record reviewed_at")
    requested_at = _aware_utc(request_value.requested_at, "request requested_at")
    expires_at = _aware_utc(request_value.expires_at, "request expires_at")
    if reviewed_at < requested_at:
        raise ValueError("review record predates the decision request")
    if reviewed_at > expires_at:
        raise ValueError("review record was authored after request expiry")
    if record_value.reviewer.subject == request_value.requester.subject:
        raise ValueError("reviewer subject must differ from requester subject")


def _require_independent_reviewer(key_id: str, context: _ReviewContext) -> None:
    if key_id == context.request_attestation.key_id:
        raise ValueError("reviewer key must differ from requester key")
    if key_id == context.dossier_attestation.key_id:
        raise ValueError("reviewer key must differ from dossier provenance key")


def _review_identity(context: _ReviewContext) -> dict[str, Any]:
    record = context.record.record
    payload = review_record_payload(record)
    return {
        "record_id": context.record.record_id,
        "canonical_sha256": context.record.canonical_sha256,
        "request_id": context.request.request_id,
        "request_sha256": context.request.canonical_sha256,
        "requester_key_id": context.request_attestation.key_id,
        "dossier_id": context.dossier.dossier.dossier_id,
        "dossier_sha256": context.dossier.source_sha256,
        "dossier_key_id": context.dossier_attestation.key_id,
        "requested_candidate_id": record.requested_candidate_id,
        "decision": record.decision,
        "reviewer_subject": record.reviewer.subject,
        "reviewed_at": payload["reviewed_at"],
        "deployment_authorized": False,
        "trading_authorized": False,
    }


def required_review_acknowledgements() -> tuple[str, ...]:
    return tuple(sorted(_REQUIRED_ACKNOWLEDGEMENTS))


def _load_attestation(path: Path) -> dict[str, Any]:
    payload = _json_object(path.read_bytes(), "review attestation")
    if set(payload) != {"payload", "signature_base64"}:
        raise ValueError("review attestation document has unexpected fields")
    if not isinstance(payload.get("payload"), dict):
        raise ValueError("review attestation payload must be an object")
    if not isinstance(payload.get("signature_base64"), str):
        raise ValueError("review attestation signature must be a string")
    return payload


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


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return cast(dict[str, Any], value)


def _reject_exact_fields(name: str, payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    missing = sorted(allowed - set(payload))
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")
    if missing:
        raise ValueError(f"{name} is missing fields: {', '.join(missing)}")


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value


def _bounded_text(value: Any, name: str, *, minimum: int, maximum: int) -> str:
    text = _required_string(value, name).strip()
    if not minimum <= len(text) <= maximum:
        raise ValueError(f"{name} length must be in [{minimum}, {maximum}]")
    return text


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list of strings")
    return tuple(_required_string(item, name) for item in value)


def _required_boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _timestamp(value: Any, name: str) -> datetime:
    text = _required_string(value, name)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from error
    return _aware_utc(parsed, name)


def _aware_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return value.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def _prefixed_identifier(value: str, prefix: str, name: str) -> str:
    suffix = value.removeprefix(prefix)
    if (
        not value.startswith(prefix)
        or len(suffix) != 40
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError(f"{name} must use {prefix}<40 lowercase hex>")
    return value


def _candidate_id(value: str) -> str:
    if (
        not value.startswith("candidate-")
        or len(value) <= len("candidate-")
        or len(value) > 160
        or value != value.strip()
    ):
        raise ValueError("requested_candidate_id must use a non-empty candidate-* value")
    return value


def _digest(value: str, name: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
    return value


def _decode_base64(value: str, name: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as error:
        raise ValueError(f"{name} is not valid base64") from error


def _reject_equal(first: Path, second: Path, name: str) -> None:
    if first == second:
        raise ValueError(f"{name} path must differ from review and signing inputs")


def _raise_non_finite(name: str, value: str) -> None:
    raise ValueError(f"{name} contains a non-finite number: {value}")
