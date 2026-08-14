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
from llm_arbitrage_system.experiments.selection_dossier import (
    SelectionDossierSnapshot,
    load_selection_dossier,
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
class SelectionDossierAttestationResult:
    attestation_path: Path
    dossier_path: Path
    dossier_id: str
    dossier_sha256: str
    matrix_sha256: str
    key_id: str
    public_key_base64: str
    trusted_key_matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "attestation_path": str(self.attestation_path),
            "dossier_path": str(self.dossier_path),
            "dossier_id": self.dossier_id,
            "dossier_sha256": self.dossier_sha256,
            "matrix_sha256": self.matrix_sha256,
            "key_id": self.key_id,
            "public_key_base64": self.public_key_base64,
            "trusted_key_matched": self.trusted_key_matched,
        }


def sign_selection_dossier(
    dossier_path: Path,
    private_key_path: Path,
    output_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    dossier = load_selection_dossier(dossier_path)
    private_path = private_key_path.resolve()
    output = output_path.resolve()
    _reject_equal(dossier.source_path, private_path, "private key")
    _reject_equal(dossier.source_path, output, "attestation")
    _reject_equal(private_path, output, "attestation")
    if output.exists() and not force:
        raise FileExistsError(f"selection dossier attestation already exists: {output}")
    private_key = load_private_key(private_path)
    identity = public_key_identity(private_key.public_key())
    payload = {
        "schema_version": _ATTESTATION_SCHEMA_VERSION,
        "algorithm": _ALGORITHM,
        "key_id": identity.key_id,
        "public_key_base64": identity.public_key_base64,
        "dossier": _dossier_identity(dossier),
        "evidence_boundary": (
            "This detached signature authenticates one canonical offline selection "
            "dossier for one provenance key. It is not a human decision, trading "
            "instruction, deployment authority, or proof of future profitability."
        ),
    }
    signature = private_key.sign(canonical_json_bytes(payload))
    document = {
        "payload": payload,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    write_json(output, document)
    return document


def verify_selection_dossier_attestation(
    dossier_path: Path,
    attestation_path: Path,
    *,
    trusted_public_key_path: Path | None = None,
) -> SelectionDossierAttestationResult:
    dossier = load_selection_dossier(dossier_path)
    attestation = attestation_path.resolve()
    document = _load_attestation(attestation)
    payload = cast(dict[str, Any], document["payload"])
    if set(payload) != {
        "schema_version",
        "algorithm",
        "key_id",
        "public_key_base64",
        "dossier",
        "evidence_boundary",
    }:
        raise ValueError("selection dossier attestation contains unexpected fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _ATTESTATION_SCHEMA_VERSION:
        raise ValueError("selection dossier attestation schema_version must be 1")
    if payload.get("algorithm") != _ALGORITHM:
        raise ValueError("selection dossier attestation algorithm must be Ed25519")
    _required_string(payload, "evidence_boundary", "selection dossier attestation")

    raw_public_key = _decode_base64(
        _required_string(
            payload,
            "public_key_base64",
            "selection dossier attestation",
        ),
        "selection dossier attestation public_key_base64",
    )
    if len(raw_public_key) != 32:
        raise ValueError("selection dossier attestation public key must be 32 raw bytes")
    public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
    identity = public_key_identity(public_key)
    key_id = _required_string(payload, "key_id", "selection dossier attestation")
    if key_id != identity.key_id:
        raise ValueError("selection dossier attestation key_id does not match public key")

    trusted_matched = False
    if trusted_public_key_path is not None:
        trusted = public_key_identity(load_public_key(trusted_public_key_path))
        if (
            trusted.key_id != key_id
            or trusted.public_key_base64 != identity.public_key_base64
        ):
            raise ValueError(
                "selection dossier attestation signer does not match trusted public key"
            )
        trusted_matched = True

    signature = _decode_base64(
        cast(str, document["signature_base64"]),
        "selection dossier attestation signature_base64",
    )
    try:
        public_key.verify(signature, canonical_json_bytes(payload))
    except InvalidSignature as error:
        raise ValueError("selection dossier attestation signature is invalid") from error

    dossier_payload = payload.get("dossier")
    if not isinstance(dossier_payload, dict):
        raise ValueError("selection dossier attestation dossier identity must be an object")
    expected = _dossier_identity(dossier)
    if cast(dict[str, Any], dossier_payload) != expected:
        raise ValueError(
            "selection dossier attestation does not match current dossier evidence"
        )
    return SelectionDossierAttestationResult(
        attestation_path=attestation,
        dossier_path=dossier.source_path,
        dossier_id=dossier.dossier.dossier_id,
        dossier_sha256=dossier.source_sha256,
        matrix_sha256=dossier.dossier.matrix_sha256,
        key_id=key_id,
        public_key_base64=identity.public_key_base64,
        trusted_key_matched=trusted_matched,
    )


def _dossier_identity(snapshot: SelectionDossierSnapshot) -> dict[str, Any]:
    dossier = snapshot.dossier
    return {
        "dossier_id": dossier.dossier_id,
        "dossier_sha256": snapshot.source_sha256,
        "matrix_sha256": dossier.matrix_sha256,
        "policy_id": dossier.policy["policy_id"],
        "policy_sha256": dossier.policy["sha256"],
        "statistics_report_id": dossier.statistics["report_id"],
        "statistics_report_sha256": dossier.statistics["sha256"],
        "diagnostics_id": dossier.diagnostics["diagnostics_id"],
        "diagnostics_sha256": dossier.diagnostics["sha256"],
        "family_state": dossier.family_state,
        "eligible_candidate_count": len(dossier.eligible_candidate_ids),
        "blocked_candidate_count": len(dossier.blocked_candidate_ids),
        "code_revision": dossier.code_revision,
        "package_version": dossier.package_version,
        "human_decision": None,
        "selected_candidate_id": None,
        "promotion": None,
    }


def _load_attestation(path: Path) -> dict[str, Any]:
    payload = _json_object(path.read_bytes(), "selection dossier attestation")
    if set(payload) != {"payload", "signature_base64"}:
        raise ValueError("selection dossier attestation document has unexpected fields")
    if not isinstance(payload.get("payload"), dict):
        raise ValueError("selection dossier attestation payload must be an object")
    if not isinstance(payload.get("signature_base64"), str):
        raise ValueError("selection dossier attestation signature must be a string")
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
        raise ValueError(f"{name} path must differ from dossier and signing inputs")


def _raise_non_finite(name: str, value: str) -> None:
    raise ValueError(f"{name} contains a non-finite number: {value}")
