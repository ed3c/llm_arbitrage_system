from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_REQUEST_SCHEMA_VERSION = 1
_REQUESTED_SCOPE = "research_review_only"
_REQUESTER_ROLE = "research_proposer"
_MAXIMUM_REQUEST_LIFETIME = timedelta(days=30)
_REQUIRED_ACKNOWLEDGEMENTS = frozenset(
    {
        "causal_alpha_unproven",
        "deployment_not_authorized",
        "future_profitability_unproven",
        "human_review_required",
        "live_trading_not_authorized",
        "source_market_truth_unverified",
    }
)


@dataclass(frozen=True, slots=True)
class DossierReference:
    dossier_id: str
    sha256: str

    def __post_init__(self) -> None:
        _prefixed_identifier(
            self.dossier_id,
            "selection-dossier-",
            "decision request dossier_id",
        )
        _digest(self.sha256, "decision request dossier sha256")


@dataclass(frozen=True, slots=True)
class RequesterIdentity:
    subject: str
    role: str = _REQUESTER_ROLE

    def __post_init__(self) -> None:
        _bounded_text(
            self.subject,
            "decision request requester.subject",
            minimum=1,
            maximum=256,
        )
        if self.role != _REQUESTER_ROLE:
            raise ValueError(f"decision request requester.role must be {_REQUESTER_ROLE}")


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    dossier: DossierReference
    requested_candidate_id: str
    requester: RequesterIdentity
    rationale: str
    requested_at: datetime
    expires_at: datetime
    requested_scope: str = _REQUESTED_SCOPE
    risk_acknowledgements: tuple[str, ...] = ()
    decision: None = None
    deployment_authorized: bool = False
    trading_authorized: bool = False

    def __post_init__(self) -> None:
        _candidate_id(self.requested_candidate_id)
        if self.requested_scope != _REQUESTED_SCOPE:
            raise ValueError(f"decision request scope must be {_REQUESTED_SCOPE}")
        _bounded_text(
            self.rationale,
            "decision request rationale",
            minimum=20,
            maximum=4000,
        )
        requested_at = _aware_utc(self.requested_at, "decision request requested_at")
        expires_at = _aware_utc(self.expires_at, "decision request expires_at")
        if expires_at <= requested_at:
            raise ValueError("decision request expires_at must be after requested_at")
        if expires_at - requested_at > _MAXIMUM_REQUEST_LIFETIME:
            raise ValueError("decision request lifetime cannot exceed 30 days")
        acknowledgements = tuple(sorted(self.risk_acknowledgements))
        if len(set(acknowledgements)) != len(acknowledgements):
            raise ValueError("decision request risk acknowledgements cannot contain duplicates")
        acknowledgement_set = set(acknowledgements)
        missing = sorted(_REQUIRED_ACKNOWLEDGEMENTS - acknowledgement_set)
        unknown = sorted(acknowledgement_set - _REQUIRED_ACKNOWLEDGEMENTS)
        if missing:
            raise ValueError(
                "decision request is missing risk acknowledgements: "
                + ", ".join(missing)
            )
        if unknown:
            raise ValueError(
                "decision request contains unknown risk acknowledgements: "
                + ", ".join(unknown)
            )
        if self.decision is not None:
            raise ValueError("decision request decision must remain null")
        if self.deployment_authorized:
            raise ValueError("decision request cannot authorize deployment")
        if self.trading_authorized:
            raise ValueError("decision request cannot authorize trading")


@dataclass(frozen=True, slots=True)
class DecisionRequestSnapshot:
    source_path: Path
    request: DecisionRequest
    request_id: str
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "request_id": self.request_id,
            "request": decision_request_payload(self.request),
        }


def load_decision_request(path: Path) -> DecisionRequestSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: decision request is not valid UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid decision-request YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("decision request must be a mapping")
    request = parse_decision_request(cast(dict[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(decision_request_payload(request)) + b"\n"
    canonical_sha256 = sha256_hex(canonical_bytes)
    return DecisionRequestSnapshot(
        source_path=resolved,
        request=request,
        request_id=f"decision-request-{canonical_sha256[:40]}",
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=canonical_sha256,
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_decision_request(payload: dict[str, Any]) -> DecisionRequest:
    _reject_unknown(
        "decision request",
        payload,
        {
            "schema_version",
            "dossier",
            "requested_candidate_id",
            "requested_scope",
            "requester",
            "rationale",
            "requested_at",
            "expires_at",
            "risk_acknowledgements",
            "decision",
            "deployment_authorized",
            "trading_authorized",
        },
    )
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _REQUEST_SCHEMA_VERSION:
        raise ValueError("decision request schema_version must be 1")

    dossier_payload = _mapping(payload.get("dossier"), "decision request dossier")
    _reject_unknown(
        "decision request dossier",
        dossier_payload,
        {"dossier_id", "sha256"},
    )
    requester_payload = _mapping(payload.get("requester"), "decision request requester")
    _reject_unknown(
        "decision request requester",
        requester_payload,
        {"subject", "role"},
    )
    decision_value = payload.get("decision")
    if decision_value is not None:
        raise ValueError("decision request decision must remain null")
    deployment_authorized = _required_boolean(
        payload.get("deployment_authorized"),
        "decision request deployment_authorized",
    )
    trading_authorized = _required_boolean(
        payload.get("trading_authorized"),
        "decision request trading_authorized",
    )
    return DecisionRequest(
        dossier=DossierReference(
            dossier_id=_required_string(
                dossier_payload.get("dossier_id"),
                "decision request dossier_id",
            ),
            sha256=_required_string(
                dossier_payload.get("sha256"),
                "decision request dossier sha256",
            ),
        ),
        requested_candidate_id=_required_string(
            payload.get("requested_candidate_id"),
            "decision request requested_candidate_id",
        ),
        requested_scope=_required_string(
            payload.get("requested_scope"),
            "decision request requested_scope",
        ),
        requester=RequesterIdentity(
            subject=_required_string(
                requester_payload.get("subject"),
                "decision request requester.subject",
            ),
            role=_required_string(
                requester_payload.get("role"),
                "decision request requester.role",
            ),
        ),
        rationale=_bounded_text(
            payload.get("rationale"),
            "decision request rationale",
            minimum=20,
            maximum=4000,
        ),
        requested_at=_timestamp(
            payload.get("requested_at"),
            "decision request requested_at",
        ),
        expires_at=_timestamp(
            payload.get("expires_at"),
            "decision request expires_at",
        ),
        risk_acknowledgements=_string_tuple(
            payload.get("risk_acknowledgements"),
            "decision request risk_acknowledgements",
        ),
        decision=None,
        deployment_authorized=deployment_authorized,
        trading_authorized=trading_authorized,
    )


def decision_request_payload(request: DecisionRequest) -> dict[str, Any]:
    requested_at = _aware_utc(request.requested_at, "decision request requested_at")
    expires_at = _aware_utc(request.expires_at, "decision request expires_at")
    return {
        "schema_version": _REQUEST_SCHEMA_VERSION,
        "dossier": {
            "dossier_id": request.dossier.dossier_id,
            "sha256": request.dossier.sha256,
        },
        "requested_candidate_id": request.requested_candidate_id,
        "requested_scope": request.requested_scope,
        "requester": {
            "subject": request.requester.subject.strip(),
            "role": request.requester.role,
        },
        "rationale": request.rationale.strip(),
        "requested_at": _timestamp_text(requested_at),
        "expires_at": _timestamp_text(expires_at),
        "risk_acknowledgements": sorted(request.risk_acknowledgements),
        "decision": None,
        "deployment_authorized": False,
        "trading_authorized": False,
    }


def required_risk_acknowledgements() -> tuple[str, ...]:
    return tuple(sorted(_REQUIRED_ACKNOWLEDGEMENTS))


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return cast(dict[str, Any], value)


def _reject_unknown(name: str, payload: dict[str, Any], allowed: set[str]) -> None:
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
        or "\x00" in value
    ):
        raise ValueError("requested_candidate_id must use a non-empty candidate-* value")
    return value


def _digest(value: str, name: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
    return value
