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
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.signing import (
    load_private_key,
    load_public_key,
    public_key_identity,
)

_ATTESTATION_SCHEMA_VERSION = 1
_REPORT_SCHEMA_VERSION = 1
_ALGORITHM = "Ed25519"
_REPORT_FIELDS = {
    "schema_version",
    "report_id",
    "matrix_sha256",
    "code_revision",
    "package_version",
    "periods_per_year",
    "candidates",
    "selection",
    "assumptions",
    "evidence_boundary",
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
class StatisticsReportSnapshot:
    source_path: Path
    payload: dict[str, Any]
    source_sha256: str

    @property
    def report_id(self) -> str:
        return _required_string(self.payload, "report_id", "statistics report")

    @property
    def matrix_sha256(self) -> str:
        return _required_digest(self.payload, "matrix_sha256", "statistics report")

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "report_id": self.report_id,
            "matrix_sha256": self.matrix_sha256,
            "candidate_count": len(self.payload["candidates"]),
            "periods_per_year": self.payload["periods_per_year"],
        }


@dataclass(frozen=True, slots=True)
class StatisticsAttestationVerificationResult:
    attestation_path: Path
    report_path: Path
    report_id: str
    report_sha256: str
    matrix_sha256: str
    key_id: str
    public_key_base64: str
    trusted_key_matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "attestation_path": str(self.attestation_path),
            "report_path": str(self.report_path),
            "report_id": self.report_id,
            "report_sha256": self.report_sha256,
            "matrix_sha256": self.matrix_sha256,
            "key_id": self.key_id,
            "public_key_base64": self.public_key_base64,
            "trusted_key_matched": self.trusted_key_matched,
        }


def load_statistics_report(path: Path) -> StatisticsReportSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    payload = _load_json_object(source_bytes, "statistics report")
    if set(payload) != _REPORT_FIELDS:
        raise ValueError("statistics report contains unknown or missing fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _REPORT_SCHEMA_VERSION:
        raise ValueError("statistics report schema_version must be 1")
    report_id = _required_string(payload, "report_id", "statistics report")
    suffix = report_id.removeprefix("oos-report-")
    if (
        not report_id.startswith("oos-report-")
        or len(suffix) != 40
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError("statistics report_id must use oos-report-<40 lowercase hex>")
    _required_digest(payload, "matrix_sha256", "statistics report")
    _required_string(payload, "code_revision", "statistics report")
    _required_string(payload, "package_version", "statistics report")
    periods = payload.get("periods_per_year")
    if isinstance(periods, bool) or not isinstance(periods, int) or periods < 1:
        raise ValueError("statistics report periods_per_year must be positive")
    candidates = payload.get("candidates")
    assumptions = payload.get("assumptions")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("statistics report candidates must be a non-empty list")
    if payload.get("selection") is not None:
        raise ValueError("statistics report selection must remain null")
    if not isinstance(assumptions, list) or not all(
        isinstance(item, str) and item for item in assumptions
    ):
        raise ValueError("statistics report assumptions must be non-empty strings")
    _required_string(payload, "evidence_boundary", "statistics report")
    canonical_bytes = canonical_json_bytes(payload) + b"\n"
    if source_bytes != canonical_bytes:
        raise ValueError("statistics report must use canonical JSON encoding")
    return StatisticsReportSnapshot(
        source_path=resolved,
        payload=payload,
        source_sha256=sha256_hex(source_bytes),
    )


def sign_statistics_report(
    report_path: Path,
    private_key_path: Path,
    output_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    report = load_statistics_report(report_path)
    private_path = private_key_path.resolve()
    output = output_path.resolve()
    _reject_equal_paths(report.source_path, private_path, "private key")
    _reject_equal_paths(report.source_path, output, "attestation")
    _reject_equal_paths(private_path, output, "attestation")
    if output.exists() and not force:
        raise FileExistsError(f"statistics attestation already exists: {output}")
    private_key = load_private_key(private_path)
    identity = public_key_identity(private_key.public_key())
    payload = {
        "schema_version": _ATTESTATION_SCHEMA_VERSION,
        "algorithm": _ALGORITHM,
        "key_id": identity.key_id,
        "public_key_base64": identity.public_key_base64,
        "report": _report_identity(report),
        "evidence_boundary": (
            "This detached signature authenticates the captured canonical OOS report "
            "for one local provenance key; it does not prove source-market truth, "
            "causal alpha, realized live profit, future returns, or production safety."
        ),
    }
    signature = private_key.sign(canonical_json_bytes(payload))
    document = {
        "payload": payload,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    write_json(output, document)
    return document


def verify_statistics_attestation(
    report_path: Path,
    attestation_path: Path,
    *,
    trusted_public_key_path: Path | None = None,
) -> StatisticsAttestationVerificationResult:
    report = load_statistics_report(report_path)
    attestation = attestation_path.resolve()
    document = _load_attestation(attestation)
    payload = cast(dict[str, Any], document["payload"])
    if set(payload) != {
        "schema_version",
        "algorithm",
        "key_id",
        "public_key_base64",
        "report",
        "evidence_boundary",
    }:
        raise ValueError("statistics attestation payload contains unexpected fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _ATTESTATION_SCHEMA_VERSION:
        raise ValueError("statistics attestation schema_version must be 1")
    if payload.get("algorithm") != _ALGORITHM:
        raise ValueError("statistics attestation algorithm must be Ed25519")
    _required_string(payload, "evidence_boundary", "statistics attestation")

    raw_public_key = _decode_base64(
        _required_string(payload, "public_key_base64", "statistics attestation"),
        "statistics attestation public_key_base64",
    )
    if len(raw_public_key) != 32:
        raise ValueError("statistics attestation public key must contain 32 raw bytes")
    public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
    identity = public_key_identity(public_key)
    key_id = _required_string(payload, "key_id", "statistics attestation")
    if key_id != identity.key_id:
        raise ValueError("statistics attestation key_id does not match public key")

    trusted_matched = False
    if trusted_public_key_path is not None:
        trusted = public_key_identity(load_public_key(trusted_public_key_path))
        if (
            trusted.key_id != key_id
            or trusted.public_key_base64 != identity.public_key_base64
        ):
            raise ValueError(
                "statistics attestation signer does not match trusted public key"
            )
        trusted_matched = True

    signature = _decode_base64(
        cast(str, document["signature_base64"]),
        "statistics attestation signature_base64",
    )
    try:
        public_key.verify(signature, canonical_json_bytes(payload))
    except InvalidSignature as error:
        raise ValueError("statistics attestation signature is invalid") from error

    report_payload = payload.get("report")
    if not isinstance(report_payload, dict):
        raise ValueError("statistics attestation report identity must be an object")
    expected = _report_identity(report)
    if cast(dict[str, Any], report_payload) != expected:
        raise ValueError("statistics attestation does not match current report evidence")
    return StatisticsAttestationVerificationResult(
        attestation_path=attestation,
        report_path=report.source_path,
        report_id=report.report_id,
        report_sha256=report.source_sha256,
        matrix_sha256=report.matrix_sha256,
        key_id=key_id,
        public_key_base64=identity.public_key_base64,
        trusted_key_matched=trusted_matched,
    )


def _report_identity(report: StatisticsReportSnapshot) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "report_sha256": report.source_sha256,
        "matrix_sha256": report.matrix_sha256,
        "code_revision": _required_string(
            report.payload,
            "code_revision",
            "statistics report",
        ),
        "package_version": _required_string(
            report.payload,
            "package_version",
            "statistics report",
        ),
        "periods_per_year": report.payload["periods_per_year"],
        "candidate_count": len(report.payload["candidates"]),
    }


def _load_attestation(path: Path) -> dict[str, Any]:
    payload = _load_json_object(path.read_bytes(), "statistics attestation")
    if set(payload) != {"payload", "signature_base64"}:
        raise ValueError("statistics attestation document contains unexpected fields")
    if not isinstance(payload.get("payload"), dict):
        raise ValueError("statistics attestation payload must be an object")
    if not isinstance(payload.get("signature_base64"), str):
        raise ValueError("statistics attestation signature_base64 must be a string")
    return payload


def _load_json_object(value: bytes, name: str) -> dict[str, Any]:
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


def _required_digest(payload: Mapping[str, Any], key: str, name: str) -> str:
    value = _required_string(payload, key, name)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name}.{key} must be 64 lowercase hex characters")
    return value


def _reject_equal_paths(first: Path, second: Path, name: str) -> None:
    if first == second:
        raise ValueError(f"{name} path must differ from report and signing inputs")


def _raise_non_finite(name: str, value: str) -> None:
    raise ValueError(f"{name} contains a non-finite number: {value}")
