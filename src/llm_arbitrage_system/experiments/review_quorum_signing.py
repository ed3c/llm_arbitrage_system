from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.review_quorum import (
    ReviewQuorumEnvelopeSnapshot,
    load_review_quorum_envelope,
)
from llm_arbitrage_system.experiments.signing import (
    load_private_key,
    load_public_key,
    public_key_identity,
)

_ATTESTATION_SCHEMA_VERSION = 1
_ALGORITHM = "Ed25519"


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
class ReviewQuorumAttestationResult:
    attestation_path: Path
    envelope_path: Path
    envelope_id: str
    envelope_sha256: str
    request_id: str
    dossier_id: str
    requested_candidate_id: str
    status: str
    key_id: str
    public_key_base64: str
    trusted_key_matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "attestation_path": str(self.attestation_path),
            "envelope_path": str(self.envelope_path),
            "envelope_id": self.envelope_id,
            "envelope_sha256": self.envelope_sha256,
            "request_id": self.request_id,
            "dossier_id": self.dossier_id,
            "requested_candidate_id": self.requested_candidate_id,
            "status": self.status,
            "key_id": self.key_id,
            "public_key_base64": self.public_key_base64,
            "trusted_key_matched": self.trusted_key_matched,
            "deployment_authorized": False,
            "trading_authorized": False,
            "release_authorized": False,
        }


def sign_review_quorum_envelope(
    envelope_path: Path,
    private_key_path: Path,
    output_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    envelope = load_review_quorum_envelope(envelope_path)
    private_path = private_key_path.resolve()
    output = output_path.resolve()
    _reject_equal(envelope.source_path, private_path, "private key")
    _reject_equal(envelope.source_path, output, "attestation")
    _reject_equal(private_path, output, "attestation")
    if output.exists() and not force:
        raise FileExistsError(f"review quorum attestation already exists: {output}")
    private_key = load_private_key(private_path)
    identity = public_key_identity(private_key.public_key())
    _require_independent_signer(identity.key_id, envelope)
    payload = {
        "schema_version": _ATTESTATION_SCHEMA_VERSION,
        "algorithm": _ALGORITHM,
        "key_id": identity.key_id,
        "public_key_base64": identity.public_key_base64,
        "envelope": _envelope_identity(envelope),
        "evidence_boundary": (
            "This detached signature authenticates one non-deployable research-only "
            "review quorum envelope for one provenance key. It is not legal approval, "
            "release authority, deployment authority, or live-trading authority."
        ),
    }
    signature = private_key.sign(canonical_json_bytes(payload))
    document = {
        "payload": payload,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    write_json(output, document)
    return document


def verify_review_quorum_attestation(
    envelope_path: Path,
    attestation_path: Path,
    *,
    trusted_public_key_path: Path | None = None,
) -> ReviewQuorumAttestationResult:
    envelope = load_review_quorum_envelope(envelope_path)
    attestation = attestation_path.resolve()
    document = _load_attestation(attestation)
    payload = cast(dict[str, Any], document["payload"])
    if set(payload) != {
        "schema_version",
        "algorithm",
        "key_id",
        "public_key_base64",
        "envelope",
        "evidence_boundary",
    }:
        raise ValueError("review quorum attestation contains unexpected fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _ATTESTATION_SCHEMA_VERSION:
        raise ValueError("review quorum attestation schema_version must be 1")
    if payload.get("algorithm") != _ALGORITHM:
        raise ValueError("review quorum attestation algorithm must be Ed25519")
    _required_string(payload, "evidence_boundary", "review quorum attestation")

    raw_public_key = _decode_base64(
        _required_string(
            payload,
            "public_key_base64",
            "review quorum attestation",
        ),
        "review quorum attestation public_key_base64",
    )
    if len(raw_public_key) != 32:
        raise ValueError("review quorum attestation public key must be 32 raw bytes")
    public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
    identity = public_key_identity(public_key)
    key_id = _required_string(payload, "key_id", "review quorum attestation")
    if key_id != identity.key_id:
        raise ValueError("review quorum attestation key_id does not match public key")
    _require_independent_signer(key_id, envelope)

    trusted_matched = False
    if trusted_public_key_path is not None:
        trusted = public_key_identity(load_public_key(trusted_public_key_path))
        if (
            trusted.key_id != key_id
            or trusted.public_key_base64 != identity.public_key_base64
        ):
            raise ValueError(
                "review quorum attestation signer does not match trusted public key"
            )
        trusted_matched = True

    signature = _decode_base64(
        cast(str, document["signature_base64"]),
        "review quorum attestation signature_base64",
    )
    try:
        public_key.verify(signature, canonical_json_bytes(payload))
    except InvalidSignature as error:
        raise ValueError("review quorum attestation signature is invalid") from error
    envelope_payload = payload.get("envelope")
    if not isinstance(envelope_payload, dict):
        raise ValueError("review quorum attestation envelope identity must be an object")
    expected = _envelope_identity(envelope)
    if cast(dict[str, Any], envelope_payload) != expected:
        raise ValueError(
            "review quorum attestation does not match current envelope evidence"
        )
    value = envelope.envelope
    return ReviewQuorumAttestationResult(
        attestation_path=attestation,
        envelope_path=envelope.source_path,
        envelope_id=value.envelope_id,
        envelope_sha256=envelope.source_sha256,
        request_id=value.request_id,
        dossier_id=value.dossier_id,
        requested_candidate_id=value.requested_candidate_id,
        status=value.status,
        key_id=key_id,
        public_key_base64=identity.public_key_base64,
        trusted_key_matched=trusted_matched,
    )


def _envelope_identity(snapshot: ReviewQuorumEnvelopeSnapshot) -> dict[str, Any]:
    envelope = snapshot.envelope
    return {
        "envelope_id": envelope.envelope_id,
        "envelope_sha256": snapshot.source_sha256,
        "request_id": envelope.request_id,
        "request_sha256": envelope.request_sha256,
        "requester_key_id": envelope.requester_key_id,
        "dossier_id": envelope.dossier_id,
        "dossier_sha256": envelope.dossier_sha256,
        "dossier_key_id": envelope.dossier_key_id,
        "requested_candidate_id": envelope.requested_candidate_id,
        "minimum_distinct_reviewers": envelope.minimum_distinct_reviewers,
        "review_count": len(envelope.reviews),
        "review_record_ids": [review.record_id for review in envelope.reviews],
        "reviewer_key_ids": [review.reviewer_key_id for review in envelope.reviews],
        "status": envelope.status,
        "deployment_authorized": False,
        "trading_authorized": False,
        "release_authorized": False,
    }


def _require_independent_signer(
    key_id: str,
    envelope: ReviewQuorumEnvelopeSnapshot,
) -> None:
    if key_id in envelope.envelope.participant_key_ids:
        raise ValueError(
            "review quorum signer key must differ from requester, dossier, and reviewer keys"
        )


def _load_attestation(path: Path) -> dict[str, Any]:
    payload = _json_object(path.read_bytes(), "review quorum attestation")
    if set(payload) != {"payload", "signature_base64"}:
        raise ValueError("review quorum attestation document has unexpected fields")
    if not isinstance(payload.get("payload"), dict):
        raise ValueError("review quorum attestation payload must be an object")
    if not isinstance(payload.get("signature_base64"), str):
        raise ValueError("review quorum attestation signature must be a string")
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


def _decode_base64(value: str, name: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as error:
        raise ValueError(f"{name} is not valid base64") from error


def _required_string(payload: Mapping[str, Any], key: str, name: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name}.{key} must be a non-empty string")
    return value


def _reject_equal(first: Path, second: Path, name: str) -> None:
    if first == second:
        raise ValueError(f"{name} path must differ from envelope and signing inputs")


def _raise_non_finite(name: str, value: str) -> None:
    raise ValueError(f"{name} contains a non-finite number: {value}")
