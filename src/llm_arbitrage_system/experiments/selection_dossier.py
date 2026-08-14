from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.manifest import installed_package_version
from llm_arbitrage_system.experiments.selection_policy import load_selection_policy
from llm_arbitrage_system.experiments.statistics_signing import load_statistics_report

_DOSSIER_SCHEMA_VERSION = 1
_DIAGNOSTICS_SCHEMA_VERSION = 1
_DIAGNOSTICS_FIELDS = {
    "schema_version",
    "diagnostics_id",
    "policy_id",
    "policy_sha256",
    "statistics_report_id",
    "statistics_report_sha256",
    "matrix_sha256",
    "code_revision",
    "package_version",
    "family_state",
    "global_blockers",
    "family",
    "candidates",
    "pairwise",
    "selection",
    "ranking",
    "promotion",
    "assumptions",
    "evidence_boundary",
}
_DOSSIER_FIELDS = {
    "schema_version",
    "dossier_id",
    "matrix_sha256",
    "policy",
    "statistics",
    "diagnostics",
    "family_state",
    "global_blockers",
    "eligible_candidate_ids",
    "blocked_candidate_ids",
    "code_revision",
    "package_version",
    "human_decision",
    "selected_candidate_id",
    "promotion",
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
class SelectionDiagnosticsSnapshot:
    source_path: Path
    payload: dict[str, Any]
    source_sha256: str

    @property
    def diagnostics_id(self) -> str:
        return _identifier(
            self.payload.get("diagnostics_id"),
            "selection-diagnostics-",
            "diagnostics_id",
        )

    @property
    def matrix_sha256(self) -> str:
        return _digest(self.payload.get("matrix_sha256"), "diagnostics matrix")

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "diagnostics_id": self.diagnostics_id,
            "matrix_sha256": self.matrix_sha256,
            "family_state": self.payload["family_state"],
            "candidate_count": len(self.payload["candidates"]),
        }


@dataclass(frozen=True, slots=True)
class SelectionDossier:
    dossier_id: str
    matrix_sha256: str
    policy: dict[str, str]
    statistics: dict[str, str]
    diagnostics: dict[str, str]
    family_state: str
    global_blockers: tuple[str, ...]
    eligible_candidate_ids: tuple[str, ...]
    blocked_candidate_ids: tuple[str, ...]
    code_revision: str
    package_version: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _DOSSIER_SCHEMA_VERSION,
            "dossier_id": self.dossier_id,
            "matrix_sha256": self.matrix_sha256,
            "policy": self.policy,
            "statistics": self.statistics,
            "diagnostics": self.diagnostics,
            "family_state": self.family_state,
            "global_blockers": list(self.global_blockers),
            "eligible_candidate_ids": list(self.eligible_candidate_ids),
            "blocked_candidate_ids": list(self.blocked_candidate_ids),
            "code_revision": self.code_revision,
            "package_version": self.package_version,
            "human_decision": None,
            "selected_candidate_id": None,
            "promotion": None,
            "assumptions": [
                (
                    "This dossier preserves preregistration, Phase 6 OOS evidence, and "
                    "Phase 7 diagnostics without performance ranking."
                ),
                (
                    "An eligible candidate is only structurally admissible for human "
                    "review and is not selected, approved, or deployable."
                ),
                (
                    "A future human decision must be stored as separate, explicitly "
                    "authorized evidence rather than mutating this immutable dossier."
                ),
            ],
            "evidence_boundary": (
                "This dossier binds captured offline paper-research evidence. It is not "
                "a trading instruction, approval, deployment authority, proof of market-"
                "data truth, proof of causal alpha, or assurance of future performance."
            ),
        }


@dataclass(frozen=True, slots=True)
class SelectionDossierSnapshot:
    source_path: Path
    dossier: SelectionDossier
    source_sha256: str

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "dossier_id": self.dossier.dossier_id,
            "matrix_sha256": self.dossier.matrix_sha256,
            "family_state": self.dossier.family_state,
            "eligible_candidate_ids": list(self.dossier.eligible_candidate_ids),
            "blocked_candidate_ids": list(self.dossier.blocked_candidate_ids),
            "human_decision": None,
        }


def load_selection_diagnostics(path: Path) -> SelectionDiagnosticsSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    payload = _json_object(source_bytes, "selection diagnostics")
    if set(payload) != _DIAGNOSTICS_FIELDS:
        raise ValueError("selection diagnostics contain unknown or missing fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _DIAGNOSTICS_SCHEMA_VERSION:
        raise ValueError("selection diagnostics schema_version must be 1")
    _identifier(
        payload.get("diagnostics_id"),
        "selection-diagnostics-",
        "diagnostics_id",
    )
    _identifier(payload.get("policy_id"), "selection-policy-", "policy_id")
    _digest(payload.get("policy_sha256"), "diagnostics policy_sha256")
    _identifier(
        payload.get("statistics_report_id"),
        "oos-report-",
        "statistics_report_id",
    )
    _digest(
        payload.get("statistics_report_sha256"),
        "diagnostics statistics_report_sha256",
    )
    _digest(payload.get("matrix_sha256"), "diagnostics matrix_sha256")
    _non_empty_string(payload.get("code_revision"), "diagnostics code_revision")
    _non_empty_string(payload.get("package_version"), "diagnostics package_version")
    family_state = _non_empty_string(
        payload.get("family_state"),
        "diagnostics family_state",
    )
    if family_state not in {"blocked", "eligible_for_human_review"}:
        raise ValueError("selection diagnostics family_state is invalid")
    _string_list(payload.get("global_blockers"), "diagnostics global_blockers")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("selection diagnostics candidates must be a non-empty list")
    _candidate_partitions(candidates)
    pairwise = payload.get("pairwise")
    assumptions = payload.get("assumptions")
    if not isinstance(pairwise, list):
        raise ValueError("selection diagnostics pairwise must be a list")
    if not isinstance(assumptions, list) or not all(
        isinstance(item, str) and item for item in assumptions
    ):
        raise ValueError("selection diagnostics assumptions are invalid")
    _non_empty_string(
        payload.get("evidence_boundary"),
        "diagnostics evidence_boundary",
    )
    if any(payload.get(key) is not None for key in ("selection", "ranking", "promotion")):
        raise ValueError("selection diagnostics decision fields must remain null")
    canonical = canonical_json_bytes(payload) + b"\n"
    if source_bytes != canonical:
        raise ValueError("selection diagnostics must use canonical JSON encoding")
    return SelectionDiagnosticsSnapshot(
        source_path=resolved,
        payload=payload,
        source_sha256=sha256_hex(source_bytes),
    )


def build_selection_dossier(
    *,
    policy_path: Path,
    statistics_report_path: Path,
    diagnostics_path: Path,
    code_revision: str,
    package_version: str | None = None,
) -> SelectionDossier:
    policy = load_selection_policy(policy_path)
    statistics = load_statistics_report(statistics_report_path)
    diagnostics = load_selection_diagnostics(diagnostics_path)
    diagnostic_payload = diagnostics.payload

    if statistics.matrix_sha256 != policy.policy.matrix_sha256:
        raise ValueError("selection policy matrix does not match statistics report")
    if diagnostics.matrix_sha256 != policy.policy.matrix_sha256:
        raise ValueError("selection diagnostics matrix does not match selection policy")
    if diagnostic_payload["policy_id"] != policy.policy_id:
        raise ValueError("selection diagnostics policy_id does not match policy")
    if diagnostic_payload["policy_sha256"] != policy.canonical_sha256:
        raise ValueError("selection diagnostics policy hash does not match policy")
    if diagnostic_payload["statistics_report_id"] != statistics.report_id:
        raise ValueError("selection diagnostics report_id does not match statistics")
    if diagnostic_payload["statistics_report_sha256"] != statistics.source_sha256:
        raise ValueError("selection diagnostics report hash does not match statistics")

    eligible, blocked = _candidate_partitions(diagnostic_payload["candidates"])
    revision = _revision(code_revision)
    version = package_version or installed_package_version()
    identity = {
        "schema_version": _DOSSIER_SCHEMA_VERSION,
        "matrix_sha256": policy.policy.matrix_sha256,
        "policy": {
            "policy_id": policy.policy_id,
            "sha256": policy.canonical_sha256,
        },
        "statistics": {
            "report_id": statistics.report_id,
            "sha256": statistics.source_sha256,
        },
        "diagnostics": {
            "diagnostics_id": diagnostics.diagnostics_id,
            "sha256": diagnostics.source_sha256,
        },
        "family_state": diagnostic_payload["family_state"],
        "global_blockers": diagnostic_payload["global_blockers"],
        "eligible_candidate_ids": list(eligible),
        "blocked_candidate_ids": list(blocked),
        "code_revision": revision,
        "package_version": version,
    }
    dossier_id = "selection-dossier-" + sha256_hex(
        canonical_json_bytes(identity)
    )[:40]
    return SelectionDossier(
        dossier_id=dossier_id,
        matrix_sha256=policy.policy.matrix_sha256,
        policy=cast(dict[str, str], identity["policy"]),
        statistics=cast(dict[str, str], identity["statistics"]),
        diagnostics=cast(dict[str, str], identity["diagnostics"]),
        family_state=cast(str, identity["family_state"]),
        global_blockers=tuple(cast(list[str], identity["global_blockers"])),
        eligible_candidate_ids=eligible,
        blocked_candidate_ids=blocked,
        code_revision=revision,
        package_version=version,
    )


def load_selection_dossier(path: Path) -> SelectionDossierSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    payload = _json_object(source_bytes, "selection dossier")
    if set(payload) != _DOSSIER_FIELDS:
        raise ValueError("selection dossier contains unknown or missing fields")
    schema_version = payload.get("schema_version")
    if isinstance(schema_version, bool) or schema_version != _DOSSIER_SCHEMA_VERSION:
        raise ValueError("selection dossier schema_version must be 1")
    dossier_id = _identifier(
        payload.get("dossier_id"),
        "selection-dossier-",
        "dossier_id",
    )
    matrix_sha = _digest(payload.get("matrix_sha256"), "dossier matrix_sha256")
    policy = _identity_object(payload.get("policy"), "policy", "policy_id")
    statistics = _identity_object(
        payload.get("statistics"),
        "statistics",
        "report_id",
    )
    diagnostics = _identity_object(
        payload.get("diagnostics"),
        "diagnostics",
        "diagnostics_id",
    )
    _identifier(policy["policy_id"], "selection-policy-", "policy_id")
    _identifier(statistics["report_id"], "oos-report-", "report_id")
    _identifier(
        diagnostics["diagnostics_id"],
        "selection-diagnostics-",
        "diagnostics_id",
    )
    family_state = _non_empty_string(payload.get("family_state"), "family_state")
    if family_state not in {"blocked", "eligible_for_human_review"}:
        raise ValueError("selection dossier family_state is invalid")
    blockers = _string_list(payload.get("global_blockers"), "global_blockers")
    eligible = _ordered_unique_strings(
        payload.get("eligible_candidate_ids"),
        "eligible_candidate_ids",
    )
    blocked = _ordered_unique_strings(
        payload.get("blocked_candidate_ids"),
        "blocked_candidate_ids",
    )
    if set(eligible) & set(blocked):
        raise ValueError("selection dossier candidate partitions overlap")
    revision = _revision(_non_empty_string(payload.get("code_revision"), "code_revision"))
    version = _non_empty_string(payload.get("package_version"), "package_version")
    if any(
        payload.get(key) is not None
        for key in ("human_decision", "selected_candidate_id", "promotion")
    ):
        raise ValueError("selection dossier decision fields must remain null")
    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, list) or not all(
        isinstance(item, str) and item for item in assumptions
    ):
        raise ValueError("selection dossier assumptions are invalid")
    _non_empty_string(payload.get("evidence_boundary"), "evidence_boundary")
    canonical = canonical_json_bytes(payload) + b"\n"
    if source_bytes != canonical:
        raise ValueError("selection dossier must use canonical JSON encoding")

    identity = {
        "schema_version": _DOSSIER_SCHEMA_VERSION,
        "matrix_sha256": matrix_sha,
        "policy": policy,
        "statistics": statistics,
        "diagnostics": diagnostics,
        "family_state": family_state,
        "global_blockers": list(blockers),
        "eligible_candidate_ids": list(eligible),
        "blocked_candidate_ids": list(blocked),
        "code_revision": revision,
        "package_version": version,
    }
    expected_id = "selection-dossier-" + sha256_hex(
        canonical_json_bytes(identity)
    )[:40]
    if dossier_id != expected_id:
        raise ValueError("selection dossier_id does not match dossier evidence")
    dossier = SelectionDossier(
        dossier_id=dossier_id,
        matrix_sha256=matrix_sha,
        policy=policy,
        statistics=statistics,
        diagnostics=diagnostics,
        family_state=family_state,
        global_blockers=blockers,
        eligible_candidate_ids=eligible,
        blocked_candidate_ids=blocked,
        code_revision=revision,
        package_version=version,
    )
    if payload != dossier.as_dict():
        raise ValueError("selection dossier payload is not canonical schema-v1 evidence")
    return SelectionDossierSnapshot(
        source_path=resolved,
        dossier=dossier,
        source_sha256=sha256_hex(source_bytes),
    )


def _candidate_partitions(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, list) or not value:
        raise ValueError("selection diagnostics candidates must be a non-empty list")
    eligible: list[str] = []
    blocked: list[str] = []
    seen: set[str] = set()
    previous = ""
    for candidate in value:
        if not isinstance(candidate, dict):
            raise ValueError("selection diagnostics candidate must be an object")
        candidate_id = _non_empty_string(candidate.get("candidate_id"), "candidate_id")
        if candidate_id in seen or candidate_id <= previous:
            raise ValueError("selection diagnostics candidates must be unique and lexical")
        seen.add(candidate_id)
        previous = candidate_id
        status = _non_empty_string(candidate.get("status"), "candidate status")
        if status == "eligible_for_human_review":
            eligible.append(candidate_id)
        elif status == "blocked":
            blocked.append(candidate_id)
        else:
            raise ValueError("selection diagnostics candidate status is invalid")
    return tuple(eligible), tuple(blocked)


def _identity_object(value: Any, name: str, identifier_key: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {identifier_key, "sha256"}:
        raise ValueError(f"selection dossier {name} identity is invalid")
    identifier = _non_empty_string(value.get(identifier_key), identifier_key)
    digest = _digest(value.get("sha256"), f"{name} sha256")
    return {identifier_key: identifier, "sha256": digest}


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


def _identifier(value: Any, prefix: str, name: str) -> str:
    result = _non_empty_string(value, name)
    suffix = result.removeprefix(prefix)
    if (
        not result.startswith(prefix)
        or len(suffix) != 40
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError(f"{name} must use {prefix}<40 lowercase hex>")
    return result


def _digest(value: Any, name: str) -> str:
    result = _non_empty_string(value, name)
    if len(result) != 64 or any(
        character not in "0123456789abcdef" for character in result
    ):
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")
    return result


def _non_empty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _string_list(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(f"{name} must be a list of non-empty strings")
    return tuple(value)


def _ordered_unique_strings(value: Any, name: str) -> tuple[str, ...]:
    result = _string_list(value, name)
    if tuple(sorted(set(result))) != result:
        raise ValueError(f"{name} must be unique and lexical")
    return result


def _revision(value: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError("code_revision cannot be empty")
    if len(result) > 160:
        raise ValueError("code_revision is too long")
    return result


def _raise_non_finite(name: str, value: str) -> None:
    raise ValueError(f"{name} contains a non-finite number: {value}")
