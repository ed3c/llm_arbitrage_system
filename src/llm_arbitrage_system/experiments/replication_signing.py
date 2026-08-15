from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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

_REPORT_SCHEMA_VERSION = 1
_ATTESTATION_SCHEMA_VERSION = 1
_ALGORITHM = "Ed25519"
_REPORT_STATES = {
    "replication_insufficient",
    "replication_failed",
    "replication_consistent",
}
_REPORT_FIELDS = {
    "schema_version",
    "report_id",
    "plan_id",
    "plan_sha256",
    "candidate_id",
    "candidate_config_sha256",
    "status",
    "cohort_count",
    "research_approved_count",
    "positive_replication_count",
    "failed_replication_count",
    "insufficient_replication_count",
    "research_approved_fraction",
    "positive_replication_fraction",
    "worst_case_total_pnl_usd",
    "median_total_pnl_usd",
    "independence_checks",
    "comparability_checks",
    "acceptance_checks",
    "cohorts",
    "selection",
    "promotion",
    "human_admit_required",
    "automatic_promotion",
    "release_authorized",
    "deployment_authorized",
    "trading_authorized",
    "assumptions",
    "evidence_boundary",
}
_COHORT_FIELDS = {
    "cohort_id",
    "statistics_report_id",
    "statistics_report_sha256",
    "statistics_signer_key_id",
    "dossier_id",
    "dossier_sha256",
    "dossier_signer_key_id",
    "quorum_envelope_id",
    "quorum_envelope_sha256",
    "quorum_signer_key_id",
    "quorum_status",
    "matrix_sha256",
    "code_revision",
    "package_version",
    "periods_per_year",
    "mark_lag_microseconds",
    "window_count",
    "test_semantic_sha256",
    "total_mark_to_market_pnl_usd",
    "state",
    "reasons",
}
_INDEPENDENCE_CHECKS = {
    "minimum_replications",
    "minimum_distinct_quorum_signers",
    "minimum_distinct_dossier_signers",
    "minimum_distinct_statistics_signers",
    "disjoint_test_semantic_sha256",
    "distinct_matrix_sha256",
    "distinct_dossier_sha256",
    "distinct_quorum_envelope_sha256",
    "statistics_report_reuse_prohibited",
}
_COMPARABILITY_CHECKS = {
    "equal_code_revision",
    "equal_package_version",
    "equal_periods_per_year",
    "equal_terminal_mark_lag",
}
_ACCEPTANCE_CHECKS = {
    "minimum_research_approved_fraction",
    "minimum_positive_replication_fraction",
    "maximum_failed_replications",
    "maximum_insufficient_replications",
    "minimum_worst_case_total_pnl_usd",
    "minimum_median_total_pnl_usd",
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
class ReplicationReportSnapshot:
    source_path: Path
    payload: dict[str, Any]
    source_sha256: str

    @property
    def report_id(self) -> str:
        return _required_prefixed_id(
            self.payload,
            "report_id",
            "replication-report-",
            40,
            "replication report",
        )

    @property
    def plan_id(self) -> str:
        return _required_prefixed_id(
            self.payload,
            "plan_id",
            "replication-plan-",
            40,
            "replication report",
        )

    @property
    def status(self) -> str:
        return _required_string(self.payload, "status", "replication report")

    @property
    def participant_key_ids(self) -> frozenset[str]:
        keys: set[str] = set()
        for raw_cohort in cast(list[object], self.payload["cohorts"]):
            cohort = cast(dict[str, Any], raw_cohort)
            keys.update(
                {
                    cast(str, cohort["statistics_signer_key_id"]),
                    cast(str, cohort["dossier_signer_key_id"]),
                    cast(str, cohort["quorum_signer_key_id"]),
                }
            )
        return frozenset(keys)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "report_id": self.report_id,
            "plan_id": self.plan_id,
            "candidate_id": self.payload["candidate_id"],
            "status": self.status,
            "cohort_count": self.payload["cohort_count"],
            "human_admit_required": True,
            "automatic_promotion": False,
            "release_authorized": False,
            "deployment_authorized": False,
            "trading_authorized": False,
        }


@dataclass(frozen=True, slots=True)
class ReplicationAttestationResult:
    attestation_path: Path
    report_path: Path
    report_id: str
    report_sha256: str
    plan_id: str
    plan_sha256: str
    candidate_id: str
    candidate_config_sha256: str
    status: str
    cohort_count: int
    key_id: str
    public_key_base64: str
    trusted_key_matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "attestation_path": str(self.attestation_path),
            "report_path": str(self.report_path),
            "report_id": self.report_id,
            "report_sha256": self.report_sha256,
            "plan_id": self.plan_id,
            "plan_sha256": self.plan_sha256,
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "status": self.status,
            "cohort_count": self.cohort_count,
            "key_id": self.key_id,
            "public_key_base64": self.public_key_base64,
            "trusted_key_matched": self.trusted_key_matched,
            "selection": None,
            "promotion": None,
            "human_admit_required": True,
            "automatic_promotion": False,
            "release_authorized": False,
            "deployment_authorized": False,
            "trading_authorized": False,
        }


def load_replication_report(path: Path) -> ReplicationReportSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    payload = _json_object(source_bytes, "replication report")
    if set(payload) != _REPORT_FIELDS:
        raise ValueError("replication report contains unknown or missing fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _REPORT_SCHEMA_VERSION:
        raise ValueError("replication report schema_version must be 1")

    report_id = _required_prefixed_id(
        payload,
        "report_id",
        "replication-report-",
        40,
        "replication report",
    )
    _required_prefixed_id(
        payload,
        "plan_id",
        "replication-plan-",
        40,
        "replication report",
    )
    _required_digest(payload, "plan_sha256", "replication report")
    _required_prefixed_id(
        payload,
        "candidate_id",
        "candidate-",
        24,
        "replication report",
    )
    _required_digest(payload, "candidate_config_sha256", "replication report")
    status = _required_string(payload, "status", "replication report")
    if status not in _REPORT_STATES:
        raise ValueError(f"invalid replication report status: {status}")

    count_fields = (
        "cohort_count",
        "research_approved_count",
        "positive_replication_count",
        "failed_replication_count",
        "insufficient_replication_count",
    )
    counts = {
        key: _integer(payload.get(key), f"replication report {key}", minimum=0)
        for key in count_fields
    }
    if counts["cohort_count"] < 1:
        raise ValueError("replication report cohort_count must be positive")

    research_fraction = _decimal_string(
        payload.get("research_approved_fraction"),
        "replication report research_approved_fraction",
    )
    positive_fraction = _decimal_string(
        payload.get("positive_replication_fraction"),
        "replication report positive_replication_fraction",
    )
    for value, name in (
        (research_fraction, "research_approved_fraction"),
        (positive_fraction, "positive_replication_fraction"),
    ):
        if not Decimal("0") <= value <= Decimal("1"):
            raise ValueError(f"replication report {name} must be in [0, 1]")
    worst = _decimal_string(
        payload.get("worst_case_total_pnl_usd"),
        "replication report worst_case_total_pnl_usd",
    )
    median = _decimal_string(
        payload.get("median_total_pnl_usd"),
        "replication report median_total_pnl_usd",
    )

    independence = _boolean_checks(
        payload.get("independence_checks"),
        "replication report independence_checks",
        _INDEPENDENCE_CHECKS,
    )
    comparability = _boolean_checks(
        payload.get("comparability_checks"),
        "replication report comparability_checks",
        _COMPARABILITY_CHECKS,
    )
    acceptance = _boolean_checks(
        payload.get("acceptance_checks"),
        "replication report acceptance_checks",
        _ACCEPTANCE_CHECKS,
    )
    cohorts = _validate_cohorts(payload.get("cohorts"))
    _verify_aggregate_fields(
        cohorts,
        counts=counts,
        research_fraction=research_fraction,
        positive_fraction=positive_fraction,
        worst=worst,
        median=median,
    )
    expected_status = _expected_status(
        independence=independence,
        comparability=comparability,
        acceptance=acceptance,
        insufficient_count=counts["insufficient_replication_count"],
    )
    if status != expected_status:
        raise ValueError("replication report status does not match evidence checks")

    if payload.get("selection") is not None:
        raise ValueError("replication report selection must remain null")
    if payload.get("promotion") is not None:
        raise ValueError("replication report promotion must remain null")
    if payload.get("human_admit_required") is not True:
        raise ValueError("replication report human_admit_required must remain true")
    for key in (
        "automatic_promotion",
        "release_authorized",
        "deployment_authorized",
        "trading_authorized",
    ):
        if payload.get(key) is not False:
            raise ValueError(f"replication report {key} must remain false")
    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions or not all(
        isinstance(item, str) and item for item in assumptions
    ):
        raise ValueError("replication report assumptions must be non-empty strings")
    _required_string(payload, "evidence_boundary", "replication report")

    expected_id = "replication-report-" + sha256_hex(
        canonical_json_bytes(_report_identity_payload(payload))
    )[:40]
    if report_id != expected_id:
        raise ValueError("replication report_id does not match canonical evidence")
    canonical_bytes = canonical_json_bytes(payload) + b"\n"
    if source_bytes != canonical_bytes:
        raise ValueError("replication report must use canonical JSON encoding")
    return ReplicationReportSnapshot(
        source_path=resolved,
        payload=payload,
        source_sha256=sha256_hex(source_bytes),
    )


def sign_replication_report(
    report_path: Path,
    private_key_path: Path,
    output_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    report = load_replication_report(report_path)
    private_path = private_key_path.resolve()
    output = output_path.resolve()
    _reject_equal(report.source_path, private_path, "private key")
    _reject_equal(report.source_path, output, "attestation")
    _reject_equal(private_path, output, "attestation")
    if output.exists() and not force:
        raise FileExistsError(f"replication attestation already exists: {output}")
    private_key = load_private_key(private_path)
    identity = public_key_identity(private_key.public_key())
    _require_independent_signer(identity.key_id, report)
    payload = {
        "schema_version": _ATTESTATION_SCHEMA_VERSION,
        "algorithm": _ALGORITHM,
        "key_id": identity.key_id,
        "public_key_base64": identity.public_key_base64,
        "report": _attested_report_identity(report),
        "evidence_boundary": (
            "This detached signature authenticates one canonical offline replication "
            "report for one provenance key. It is not candidate selection, legal "
            "approval, release authority, deployment authority, or live-trading "
            "authority."
        ),
    }
    signature = private_key.sign(canonical_json_bytes(payload))
    document = {
        "payload": payload,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    write_json(output, document)
    return document


def verify_replication_attestation(
    report_path: Path,
    attestation_path: Path,
    *,
    trusted_public_key_path: Path | None = None,
) -> ReplicationAttestationResult:
    report = load_replication_report(report_path)
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
        raise ValueError("replication attestation contains unexpected fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _ATTESTATION_SCHEMA_VERSION:
        raise ValueError("replication attestation schema_version must be 1")
    if payload.get("algorithm") != _ALGORITHM:
        raise ValueError("replication attestation algorithm must be Ed25519")
    _required_string(payload, "evidence_boundary", "replication attestation")

    raw_public_key = _decode_base64(
        _required_string(
            payload,
            "public_key_base64",
            "replication attestation",
        ),
        "replication attestation public_key_base64",
    )
    if len(raw_public_key) != 32:
        raise ValueError("replication attestation public key must be 32 raw bytes")
    public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
    identity = public_key_identity(public_key)
    key_id = _required_string(payload, "key_id", "replication attestation")
    if key_id != identity.key_id:
        raise ValueError("replication attestation key_id does not match public key")
    _require_independent_signer(key_id, report)

    trusted_matched = False
    if trusted_public_key_path is not None:
        trusted = public_key_identity(load_public_key(trusted_public_key_path))
        if (
            trusted.key_id != key_id
            or trusted.public_key_base64 != identity.public_key_base64
        ):
            raise ValueError(
                "replication attestation signer does not match trusted public key"
            )
        trusted_matched = True

    signature = _decode_base64(
        cast(str, document["signature_base64"]),
        "replication attestation signature_base64",
    )
    try:
        public_key.verify(signature, canonical_json_bytes(payload))
    except InvalidSignature as error:
        raise ValueError("replication attestation signature is invalid") from error
    raw_report_identity = payload.get("report")
    if not isinstance(raw_report_identity, dict):
        raise ValueError("replication attestation report identity must be an object")
    expected = _attested_report_identity(report)
    if cast(dict[str, Any], raw_report_identity) != expected:
        raise ValueError(
            "replication attestation does not match current report evidence"
        )
    value = report.payload
    return ReplicationAttestationResult(
        attestation_path=attestation,
        report_path=report.source_path,
        report_id=report.report_id,
        report_sha256=report.source_sha256,
        plan_id=report.plan_id,
        plan_sha256=cast(str, value["plan_sha256"]),
        candidate_id=cast(str, value["candidate_id"]),
        candidate_config_sha256=cast(str, value["candidate_config_sha256"]),
        status=report.status,
        cohort_count=cast(int, value["cohort_count"]),
        key_id=key_id,
        public_key_base64=identity.public_key_base64,
        trusted_key_matched=trusted_matched,
    )


def _validate_cohorts(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("replication report cohorts must be a non-empty list")
    cohorts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    previous_id = ""
    for index, raw_cohort in enumerate(value):
        if not isinstance(raw_cohort, dict):
            raise ValueError(f"replication report cohort {index} must be an object")
        cohort = cast(dict[str, Any], raw_cohort)
        if set(cohort) != _COHORT_FIELDS:
            raise ValueError(
                f"replication report cohort {index} has unknown or missing fields"
            )
        cohort_id = _required_prefixed_id(
            cohort,
            "cohort_id",
            "cohort-",
            24,
            f"replication report cohort {index}",
        )
        if cohort_id in seen_ids:
            raise ValueError(f"duplicate replication report cohort_id: {cohort_id}")
        if previous_id and cohort_id <= previous_id:
            raise ValueError("replication report cohorts must use canonical ID order")
        seen_ids.add(cohort_id)
        previous_id = cohort_id
        _required_prefixed_id(
            cohort,
            "statistics_report_id",
            "oos-report-",
            40,
            f"replication report cohort {index}",
        )
        _required_digest(
            cohort,
            "statistics_report_sha256",
            f"replication report cohort {index}",
        )
        _required_key_id(
            cohort,
            "statistics_signer_key_id",
            f"replication report cohort {index}",
        )
        _required_prefixed_id(
            cohort,
            "dossier_id",
            "selection-dossier-",
            40,
            f"replication report cohort {index}",
        )
        _required_digest(
            cohort,
            "dossier_sha256",
            f"replication report cohort {index}",
        )
        _required_key_id(
            cohort,
            "dossier_signer_key_id",
            f"replication report cohort {index}",
        )
        _required_prefixed_id(
            cohort,
            "quorum_envelope_id",
            "review-quorum-",
            40,
            f"replication report cohort {index}",
        )
        _required_digest(
            cohort,
            "quorum_envelope_sha256",
            f"replication report cohort {index}",
        )
        _required_key_id(
            cohort,
            "quorum_signer_key_id",
            f"replication report cohort {index}",
        )
        _required_string(cohort, "quorum_status", f"replication report cohort {index}")
        _required_digest(cohort, "matrix_sha256", f"replication report cohort {index}")
        _required_string(cohort, "code_revision", f"replication report cohort {index}")
        _required_string(cohort, "package_version", f"replication report cohort {index}")
        _integer(
            cohort.get("periods_per_year"),
            f"replication report cohort {index} periods_per_year",
            minimum=1,
        )
        _integer(
            cohort.get("mark_lag_microseconds"),
            f"replication report cohort {index} mark_lag_microseconds",
            minimum=0,
        )
        window_count = _integer(
            cohort.get("window_count"),
            f"replication report cohort {index} window_count",
            minimum=1,
        )
        test_hashes = cohort.get("test_semantic_sha256")
        if not isinstance(test_hashes, list) or len(test_hashes) != window_count:
            raise ValueError(
                f"replication report cohort {index} test hash count must match windows"
            )
        normalized_hashes: list[str] = []
        for hash_index, raw_hash in enumerate(test_hashes):
            if not isinstance(raw_hash, str):
                raise ValueError(
                    f"replication report cohort {index} test hash {hash_index} "
                    "must be a string"
                )
            _validate_digest_text(
                raw_hash,
                f"replication report cohort {index} test hash {hash_index}",
            )
            normalized_hashes.append(raw_hash)
        if len(set(normalized_hashes)) != len(normalized_hashes):
            raise ValueError(f"replication report cohort {index} repeats test hashes")
        _decimal_string(
            cohort.get("total_mark_to_market_pnl_usd"),
            f"replication report cohort {index} total_mark_to_market_pnl_usd",
        )
        state = _required_string(
            cohort,
            "state",
            f"replication report cohort {index}",
        )
        if state not in _REPORT_STATES:
            raise ValueError(f"invalid replication report cohort state: {state}")
        reasons = cohort.get("reasons")
        if not isinstance(reasons, list) or not all(
            isinstance(reason, str) and reason for reason in reasons
        ):
            raise ValueError(
                f"replication report cohort {index} reasons must be strings"
            )
        cohorts.append(cohort)
    return tuple(cohorts)


def _verify_aggregate_fields(
    cohorts: tuple[dict[str, Any], ...],
    *,
    counts: Mapping[str, int],
    research_fraction: Decimal,
    positive_fraction: Decimal,
    worst: Decimal,
    median: Decimal,
) -> None:
    cohort_count = len(cohorts)
    approved_count = sum(
        cohort["quorum_status"] == "approved_for_research_only"
        for cohort in cohorts
    )
    positive_count = sum(
        cohort["state"] == "replication_consistent" for cohort in cohorts
    )
    failed_count = sum(
        cohort["state"] == "replication_failed" for cohort in cohorts
    )
    insufficient_count = sum(
        cohort["state"] == "replication_insufficient" for cohort in cohorts
    )
    expected_counts = {
        "cohort_count": cohort_count,
        "research_approved_count": approved_count,
        "positive_replication_count": positive_count,
        "failed_replication_count": failed_count,
        "insufficient_replication_count": insufficient_count,
    }
    if dict(counts) != expected_counts:
        raise ValueError("replication report aggregate counts do not match cohorts")
    if positive_count + failed_count + insufficient_count != cohort_count:
        raise ValueError("replication report cohort states are incomplete")
    expected_research_fraction = Decimal(approved_count) / Decimal(cohort_count)
    expected_positive_fraction = Decimal(positive_count) / Decimal(cohort_count)
    if research_fraction != expected_research_fraction:
        raise ValueError("replication report research-approved fraction drift")
    if positive_fraction != expected_positive_fraction:
        raise ValueError("replication report positive fraction drift")
    totals = tuple(
        _decimal_string(
            cohort["total_mark_to_market_pnl_usd"],
            "replication report cohort total PnL",
        )
        for cohort in cohorts
    )
    if worst != min(totals):
        raise ValueError("replication report worst-case PnL drift")
    if median != _median_decimal(totals):
        raise ValueError("replication report median PnL drift")


def _expected_status(
    *,
    independence: Mapping[str, bool],
    comparability: Mapping[str, bool],
    acceptance: Mapping[str, bool],
    insufficient_count: int,
) -> str:
    if (
        not all(independence.values())
        or not all(comparability.values())
        or (
            insufficient_count > 0
            and not acceptance["maximum_insufficient_replications"]
        )
    ):
        return "replication_insufficient"
    if all(acceptance.values()):
        return "replication_consistent"
    return "replication_failed"


def _report_identity_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload["schema_version"],
        "plan_id": payload["plan_id"],
        "plan_sha256": payload["plan_sha256"],
        "candidate_id": payload["candidate_id"],
        "candidate_config_sha256": payload["candidate_config_sha256"],
        "status": payload["status"],
        "cohort_count": payload["cohort_count"],
        "research_approved_count": payload["research_approved_count"],
        "positive_replication_count": payload["positive_replication_count"],
        "failed_replication_count": payload["failed_replication_count"],
        "insufficient_replication_count": payload[
            "insufficient_replication_count"
        ],
        "research_approved_fraction": payload["research_approved_fraction"],
        "positive_replication_fraction": payload[
            "positive_replication_fraction"
        ],
        "worst_case_total_pnl_usd": payload["worst_case_total_pnl_usd"],
        "median_total_pnl_usd": payload["median_total_pnl_usd"],
        "independence_checks": payload["independence_checks"],
        "comparability_checks": payload["comparability_checks"],
        "acceptance_checks": payload["acceptance_checks"],
        "cohorts": payload["cohorts"],
    }


def _attested_report_identity(report: ReplicationReportSnapshot) -> dict[str, Any]:
    payload = report.payload
    return {
        "report_id": report.report_id,
        "report_sha256": report.source_sha256,
        "plan_id": report.plan_id,
        "plan_sha256": payload["plan_sha256"],
        "candidate_id": payload["candidate_id"],
        "candidate_config_sha256": payload["candidate_config_sha256"],
        "status": report.status,
        "cohort_count": payload["cohort_count"],
        "selection": None,
        "promotion": None,
        "human_admit_required": True,
        "automatic_promotion": False,
        "release_authorized": False,
        "deployment_authorized": False,
        "trading_authorized": False,
    }


def _require_independent_signer(
    key_id: str,
    report: ReplicationReportSnapshot,
) -> None:
    if key_id in report.participant_key_ids:
        raise ValueError(
            "replication report signer must differ from every statistics, dossier, "
            "and quorum signer key"
        )


def _boolean_checks(
    value: object,
    name: str,
    expected_fields: set[str],
) -> dict[str, bool]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    payload = cast(dict[str, Any], value)
    if set(payload) != expected_fields:
        raise ValueError(f"{name} contains unknown or missing fields")
    if not all(isinstance(item, bool) for item in payload.values()):
        raise ValueError(f"{name} values must be booleans")
    return cast(dict[str, bool], payload)


def _load_attestation(path: Path) -> dict[str, Any]:
    payload = _json_object(path.read_bytes(), "replication attestation")
    if set(payload) != {"payload", "signature_base64"}:
        raise ValueError("replication attestation document has unexpected fields")
    if not isinstance(payload.get("payload"), dict):
        raise ValueError("replication attestation payload must be an object")
    if not isinstance(payload.get("signature_base64"), str):
        raise ValueError("replication attestation signature must be a string")
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


def _required_string(payload: Mapping[str, Any], key: str, name: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name}.{key} must be a non-empty string")
    return value


def _required_digest(payload: Mapping[str, Any], key: str, name: str) -> str:
    value = _required_string(payload, key, name)
    _validate_digest_text(value, f"{name}.{key}")
    return value


def _validate_digest_text(value: str, name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be 64 lowercase hex characters")


def _required_prefixed_id(
    payload: Mapping[str, Any],
    key: str,
    prefix: str,
    suffix_length: int,
    name: str,
) -> str:
    value = _required_string(payload, key, name)
    suffix = value.removeprefix(prefix)
    if (
        not value.startswith(prefix)
        or len(suffix) != suffix_length
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError(
            f"{name}.{key} must use {prefix}<{suffix_length} lowercase hex>"
        )
    return value


def _required_key_id(payload: Mapping[str, Any], key: str, name: str) -> str:
    value = _required_string(payload, key, name)
    suffix = value.removeprefix("ed25519-")
    if (
        not value.startswith("ed25519-")
        or len(suffix) != 32
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError(f"{name}.{key} must use ed25519-<32 lowercase hex>")
    return value


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return int(value)


def _decimal_string(value: object, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} is not a valid decimal string") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


def _median_decimal(values: tuple[Decimal, ...]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal("2")


def _decode_base64(value: str, name: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as error:
        raise ValueError(f"{name} is not valid base64") from error


def _reject_equal(first: Path, second: Path, name: str) -> None:
    if first == second:
        raise ValueError(f"{name} path must differ from report and signing inputs")


def _raise_non_finite(name: str, value: str) -> None:
    raise ValueError(f"{name} contains a non-finite number: {value}")
