from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex

_SCHEMA_VERSION = 1
_COHORT_PREFIX = "cohort-"
_ARTIFACT_FIELDS = {"evidence", "attestation", "trusted_public_key"}


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
class ReplicationArtifactInput:
    evidence_path: Path
    attestation_path: Path
    trusted_public_key_path: Path


@dataclass(frozen=True, slots=True)
class ReplicationCohortInput:
    cohort_id: str
    statistics: ReplicationArtifactInput
    dossier: ReplicationArtifactInput
    quorum: ReplicationArtifactInput


@dataclass(frozen=True, slots=True)
class ReplicationInputSnapshot:
    source_path: Path
    cohorts: tuple[ReplicationCohortInput, ...]
    source_sha256: str
    canonical_sha256: str

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "cohort_ids": [cohort.cohort_id for cohort in self.cohorts],
            "cohort_count": len(self.cohorts),
        }


def load_replication_inputs(path: Path) -> ReplicationInputSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    payload = _json_object(source_bytes, "replication inputs")
    if set(payload) != {"schema_version", "cohorts"}:
        raise ValueError("replication inputs contain unknown or missing fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _SCHEMA_VERSION:
        raise ValueError("replication inputs schema_version must be 1")
    raw_cohorts = payload.get("cohorts")
    if not isinstance(raw_cohorts, list) or not raw_cohorts:
        raise ValueError("replication inputs cohorts must be a non-empty list")

    cohorts: list[ReplicationCohortInput] = []
    canonical_cohorts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    evidence_paths: set[Path] = set()
    attestation_paths: set[Path] = set()
    for index, raw_cohort in enumerate(raw_cohorts):
        if not isinstance(raw_cohort, dict):
            raise ValueError(f"replication cohort {index} must be an object")
        cohort_payload = cast(dict[str, Any], raw_cohort)
        if set(cohort_payload) != {"cohort_id", "statistics", "dossier", "quorum"}:
            raise ValueError(
                f"replication cohort {index} contains unknown or missing fields"
            )
        cohort_id = _cohort_id(
            _required_string(cohort_payload.get("cohort_id"), f"cohort {index} id")
        )
        if cohort_id in seen_ids:
            raise ValueError(f"duplicate replication cohort_id: {cohort_id}")
        seen_ids.add(cohort_id)

        statistics, statistics_canonical = _artifact_input(
            resolved.parent,
            cohort_payload.get("statistics"),
            f"cohort {cohort_id} statistics",
        )
        dossier, dossier_canonical = _artifact_input(
            resolved.parent,
            cohort_payload.get("dossier"),
            f"cohort {cohort_id} dossier",
        )
        quorum, quorum_canonical = _artifact_input(
            resolved.parent,
            cohort_payload.get("quorum"),
            f"cohort {cohort_id} quorum",
        )
        cohort = ReplicationCohortInput(
            cohort_id=cohort_id,
            statistics=statistics,
            dossier=dossier,
            quorum=quorum,
        )
        _reject_reused_evidence_paths(
            cohort,
            evidence_paths=evidence_paths,
            attestation_paths=attestation_paths,
        )
        cohorts.append(cohort)
        canonical_cohorts.append(
            {
                "cohort_id": cohort_id,
                "statistics": statistics_canonical,
                "dossier": dossier_canonical,
                "quorum": quorum_canonical,
            }
        )

    cohorts.sort(key=lambda cohort: cohort.cohort_id)
    canonical_cohorts.sort(key=lambda cohort: cast(str, cohort["cohort_id"]))
    canonical_payload = {
        "schema_version": _SCHEMA_VERSION,
        "cohorts": canonical_cohorts,
    }
    return ReplicationInputSnapshot(
        source_path=resolved,
        cohorts=tuple(cohorts),
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=sha256_hex(canonical_json_bytes(canonical_payload)),
    )


def _artifact_input(
    root: Path,
    value: object,
    name: str,
) -> tuple[ReplicationArtifactInput, dict[str, str]]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    payload = cast(dict[str, Any], value)
    if set(payload) != _ARTIFACT_FIELDS:
        raise ValueError(f"{name} contains unknown or missing fields")
    evidence_text = _safe_relative_path(
        _required_string(payload.get("evidence"), f"{name} evidence"),
        f"{name} evidence",
    )
    attestation_text = _safe_relative_path(
        _required_string(payload.get("attestation"), f"{name} attestation"),
        f"{name} attestation",
    )
    trusted_key_text = _safe_relative_path(
        _required_string(
            payload.get("trusted_public_key"),
            f"{name} trusted_public_key",
        ),
        f"{name} trusted_public_key",
    )
    evidence = (root / evidence_text).resolve()
    attestation = (root / attestation_text).resolve()
    trusted_key = (root / trusted_key_text).resolve()
    for item, role in (
        (evidence, "evidence"),
        (attestation, "attestation"),
        (trusted_key, "trusted public key"),
    ):
        if not item.is_file():
            raise ValueError(f"{name} {role} is not a file: {item}")
    if len({evidence, attestation, trusted_key}) != 3:
        raise ValueError(f"{name} paths must be distinct")
    return (
        ReplicationArtifactInput(
            evidence_path=evidence,
            attestation_path=attestation,
            trusted_public_key_path=trusted_key,
        ),
        {
            "evidence": evidence_text.as_posix(),
            "attestation": attestation_text.as_posix(),
            "trusted_public_key": trusted_key_text.as_posix(),
        },
    )


def _reject_reused_evidence_paths(
    cohort: ReplicationCohortInput,
    *,
    evidence_paths: set[Path],
    attestation_paths: set[Path],
) -> None:
    current_evidence = {
        cohort.statistics.evidence_path,
        cohort.dossier.evidence_path,
        cohort.quorum.evidence_path,
    }
    current_attestations = {
        cohort.statistics.attestation_path,
        cohort.dossier.attestation_path,
        cohort.quorum.attestation_path,
    }
    if len(current_evidence) != 3:
        raise ValueError(f"cohort {cohort.cohort_id} reuses an evidence path")
    if len(current_attestations) != 3:
        raise ValueError(f"cohort {cohort.cohort_id} reuses an attestation path")
    reused_evidence = sorted(str(path) for path in current_evidence & evidence_paths)
    if reused_evidence:
        raise ValueError(
            "replication cohorts cannot reuse evidence paths: "
            + ", ".join(reused_evidence)
        )
    reused_attestations = sorted(
        str(path) for path in current_attestations & attestation_paths
    )
    if reused_attestations:
        raise ValueError(
            "replication cohorts cannot reuse attestation paths: "
            + ", ".join(reused_attestations)
        )
    evidence_paths.update(current_evidence)
    attestation_paths.update(current_attestations)


def _json_object(value: bytes, name: str) -> dict[str, Any]:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{name} are not valid UTF-8") from error
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


def _safe_relative_path(value: str, name: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or normalized.startswith("~") or ".." in path.parts:
        raise ValueError(f"{name} must be a safe relative path")
    if not path.parts or any(part in {"", "."} for part in path.parts):
        raise ValueError(f"{name} must be a normalized relative path")
    return path


def _cohort_id(value: str) -> str:
    suffix = value.removeprefix(_COHORT_PREFIX)
    if (
        not value.startswith(_COHORT_PREFIX)
        or len(suffix) != 24
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError("cohort_id must use cohort-<24 lowercase hex>")
    return value


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if "\x00" in value:
        raise ValueError(f"{name} cannot contain NUL")
    return value


def _raise_non_finite(name: str, value: str) -> None:
    raise ValueError(f"{name} contain a non-finite number: {value}")
