from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from llm_arbitrage_system.experiments.bundle import verify_bundle
from llm_arbitrage_system.experiments.bundle_io import file_sha256, write_json
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex

_ATTESTATION_SCHEMA_VERSION = 1
_ALGORITHM = "Ed25519"


@dataclass(frozen=True, slots=True)
class SigningKeyIdentity:
    key_id: str
    algorithm: str
    public_key_base64: str

    def as_dict(self) -> dict[str, str]:
        return {
            "key_id": self.key_id,
            "algorithm": self.algorithm,
            "public_key_base64": self.public_key_base64,
        }


@dataclass(frozen=True, slots=True)
class AttestationVerificationResult:
    attestation_path: Path
    experiment_id: str
    run_id: str
    key_id: str
    public_key_base64: str
    bundle_root_sha256: str
    lineage_id: str | None
    trusted_key_matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "attestation_path": str(self.attestation_path),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "key_id": self.key_id,
            "public_key_base64": self.public_key_base64,
            "bundle_root_sha256": self.bundle_root_sha256,
            "lineage_id": self.lineage_id,
            "trusted_key_matched": self.trusted_key_matched,
        }


def generate_signing_keypair(
    private_key_path: Path,
    public_key_path: Path,
    *,
    force: bool = False,
) -> SigningKeyIdentity:
    private_path = private_key_path.resolve()
    public_path = public_key_path.resolve()
    if private_path == public_path:
        raise ValueError("private and public key paths must differ")
    for path in (private_path, public_path):
        if path.exists() and not force:
            raise FileExistsError(f"signing key path already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _atomic_write(private_path, private_bytes, mode=0o600)
    _atomic_write(public_path, public_bytes, mode=0o644)
    return public_key_identity(public_key)


def public_key_identity(public_key: Ed25519PublicKey) -> SigningKeyIdentity:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return SigningKeyIdentity(
        key_id=f"ed25519-{sha256_hex(raw)[:32]}",
        algorithm=_ALGORITHM,
        public_key_base64=base64.b64encode(raw).decode("ascii"),
    )


def load_private_key(path: Path) -> Ed25519PrivateKey:
    value = serialization.load_pem_private_key(path.resolve().read_bytes(), password=None)
    if not isinstance(value, Ed25519PrivateKey):
        raise ValueError("private key is not Ed25519")
    return value


def load_public_key(path: Path) -> Ed25519PublicKey:
    value = serialization.load_pem_public_key(path.resolve().read_bytes())
    if not isinstance(value, Ed25519PublicKey):
        raise ValueError("public key is not Ed25519")
    return value


def sign_bundle(
    bundle_path: Path,
    private_key_path: Path,
    output_path: Path,
    *,
    lineage_id: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    bundle = bundle_path.resolve()
    verification = verify_bundle(bundle)
    output = output_path.resolve()
    if output.exists() and not force:
        raise FileExistsError(f"attestation already exists: {output}")
    private_key = load_private_key(private_key_path)
    identity = public_key_identity(private_key.public_key())
    payload = _attestation_payload(
        bundle,
        experiment_id=verification.experiment_id,
        run_id=verification.run_id,
        identity=identity,
        lineage_id=lineage_id,
    )
    signature = private_key.sign(canonical_json_bytes(payload))
    document = {
        "payload": payload,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    write_json(output, document)
    return document


def verify_attestation(
    bundle_path: Path,
    attestation_path: Path,
    *,
    trusted_public_key_path: Path | None = None,
    expected_lineage_id: str | None = None,
) -> AttestationVerificationResult:
    bundle = bundle_path.resolve()
    attestation = attestation_path.resolve()
    document = _load_attestation_document(attestation)
    payload = cast(dict[str, Any], document["payload"])
    signature = _decode_base64(
        cast(str, document["signature_base64"]),
        "signature_base64",
    )
    if payload.get("schema_version") != _ATTESTATION_SCHEMA_VERSION:
        raise ValueError("attestation schema_version must be 1")
    if payload.get("algorithm") != _ALGORITHM:
        raise ValueError("attestation algorithm must be Ed25519")

    public_key_raw = _decode_base64(
        _required_string(payload, "public_key_base64"),
        "payload.public_key_base64",
    )
    if len(public_key_raw) != 32:
        raise ValueError("attestation public key must contain 32 raw bytes")
    public_key = Ed25519PublicKey.from_public_bytes(public_key_raw)
    identity = public_key_identity(public_key)
    key_id = _required_string(payload, "key_id")
    if identity.key_id != key_id:
        raise ValueError("attestation key_id does not match the embedded public key")

    trusted_matched = False
    if trusted_public_key_path is not None:
        trusted = public_key_identity(load_public_key(trusted_public_key_path))
        if (
            trusted.key_id != key_id
            or trusted.public_key_base64 != identity.public_key_base64
        ):
            raise ValueError("attestation signer does not match the trusted public key")
        trusted_matched = True

    try:
        public_key.verify(signature, canonical_json_bytes(payload))
    except InvalidSignature as error:
        raise ValueError("attestation signature is invalid") from error

    bundle_verification = verify_bundle(bundle)
    if _required_string(payload, "experiment_id") != bundle_verification.experiment_id:
        raise ValueError("attestation experiment_id does not match the bundle")
    if _required_string(payload, "run_id") != bundle_verification.run_id:
        raise ValueError("attestation run_id does not match the bundle")

    expected_bundle = _bundle_identity(bundle, bundle_verification.experiment_id)
    bundle_payload = payload.get("bundle")
    if not isinstance(bundle_payload, dict):
        raise ValueError("attestation payload.bundle must be an object")
    if cast(dict[str, Any], bundle_payload) != expected_bundle:
        raise ValueError("attestation bundle identity does not match current bundle evidence")

    lineage_value = payload.get("lineage_id")
    if lineage_value is not None and not isinstance(lineage_value, str):
        raise ValueError("attestation lineage_id must be a string or null")
    lineage_id = cast(str | None, lineage_value)
    if expected_lineage_id is not None and lineage_id != expected_lineage_id:
        raise ValueError("attestation lineage_id does not match the expected lineage")

    return AttestationVerificationResult(
        attestation_path=attestation,
        experiment_id=bundle_verification.experiment_id,
        run_id=bundle_verification.run_id,
        key_id=key_id,
        public_key_base64=identity.public_key_base64,
        bundle_root_sha256=_required_string(expected_bundle, "root_sha256"),
        lineage_id=lineage_id,
        trusted_key_matched=trusted_matched,
    )


def _attestation_payload(
    bundle: Path,
    *,
    experiment_id: str,
    run_id: str,
    identity: SigningKeyIdentity,
    lineage_id: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": _ATTESTATION_SCHEMA_VERSION,
        "algorithm": _ALGORITHM,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "key_id": identity.key_id,
        "public_key_base64": identity.public_key_base64,
        "lineage_id": lineage_id,
        "bundle": _bundle_identity(bundle, experiment_id),
        "evidence_boundary": (
            "This detached signature authenticates captured bundle bytes for one local "
            "provenance key; it does not prove market-data truth or profitability."
        ),
    }


def _bundle_identity(bundle: Path, experiment_id: str) -> dict[str, str]:
    manifest_sha = file_sha256(bundle / "manifest.json")
    checksums_sha = file_sha256(bundle / "checksums.sha256")
    root_payload = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "manifest_sha256": manifest_sha,
        "checksums_sha256": checksums_sha,
    }
    return {
        "manifest_sha256": manifest_sha,
        "checksums_sha256": checksums_sha,
        "root_sha256": sha256_hex(canonical_json_bytes(root_payload)),
    }


def _load_attestation_document(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid attestation document: {path}") from error
    if not isinstance(parsed, dict):
        raise ValueError("attestation document must be an object")
    document = cast(dict[str, Any], parsed)
    if set(document) != {"payload", "signature_base64"}:
        raise ValueError("attestation document contains unexpected fields")
    if not isinstance(document.get("payload"), dict):
        raise ValueError("attestation payload must be an object")
    if not isinstance(document.get("signature_base64"), str):
        raise ValueError("attestation signature_base64 must be a string")
    return document


def _decode_base64(value: str, name: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, ValueError, UnicodeEncodeError) as error:
        raise ValueError(f"{name} is not valid base64") from error


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"attestation.{key} must be a non-empty string")
    return value


def _atomic_write(path: Path, value: bytes, *, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(value)
    os.chmod(temporary, mode)
    temporary.replace(path)
    os.chmod(path, mode)
