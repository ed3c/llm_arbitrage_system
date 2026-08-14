from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.evaluation import ExperimentMatrixSnapshot
from llm_arbitrage_system.experiments.manifest import installed_package_version
from llm_arbitrage_system.experiments.strict_yaml import strict_yaml_load

_CAMPAIGN_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CampaignExecutionPolicy:
    maximum_parallel_evaluations: int = 1
    maximum_failures: int = 1
    stop_on_failure: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_parallel_evaluations <= 16:
            raise ValueError("maximum_parallel_evaluations must be in [1, 16]")
        if not 1 <= self.maximum_failures <= 4096:
            raise ValueError("maximum_failures must be in [1, 4096]")


@dataclass(frozen=True, slots=True)
class CampaignSelection:
    include_evaluation_ids: tuple[str, ...] = ()
    exclude_evaluation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_unique_ids(self.include_evaluation_ids, "include_evaluation_ids")
        _validate_unique_ids(self.exclude_evaluation_ids, "exclude_evaluation_ids")
        overlap = sorted(
            set(self.include_evaluation_ids) & set(self.exclude_evaluation_ids)
        )
        if overlap:
            raise ValueError(
                "campaign selection cannot include and exclude the same evaluations: "
                + ", ".join(overlap)
            )


@dataclass(frozen=True, slots=True)
class CampaignSpec:
    execution: CampaignExecutionPolicy = field(
        default_factory=CampaignExecutionPolicy
    )
    selection: CampaignSelection = field(default_factory=CampaignSelection)


@dataclass(frozen=True, slots=True)
class CampaignSpecSnapshot:
    source_path: Path
    spec: CampaignSpec
    source_sha256: str
    canonical_sha256: str
    canonical_bytes: bytes = field(repr=False)
    source_bytes: bytes = field(repr=False)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256,
            "canonical_sha256": self.canonical_sha256,
            "campaign": campaign_spec_payload(self.spec),
        }


@dataclass(frozen=True, slots=True)
class CampaignManifest:
    campaign_id: str
    campaign_run_id: str
    matrix_sha256: str
    dataset_semantic_sha256: str
    base_config_sha256: str
    campaign_config_sha256: str
    evaluation_ids_sha256: str
    evaluation_count: int
    code_revision: str
    package_version: str
    signer_key_id: str
    lineage_id: str | None

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": _CAMPAIGN_SCHEMA_VERSION,
            "matrix_sha256": self.matrix_sha256,
            "dataset_semantic_sha256": self.dataset_semantic_sha256,
            "base_config_sha256": self.base_config_sha256,
            "campaign_config_sha256": self.campaign_config_sha256,
            "evaluation_ids_sha256": self.evaluation_ids_sha256,
            "code_revision": self.code_revision,
            "package_version": self.package_version,
            "signer_key_id": self.signer_key_id,
            "lineage_id": self.lineage_id,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _CAMPAIGN_SCHEMA_VERSION,
            "campaign_id": self.campaign_id,
            "campaign_run_id": self.campaign_run_id,
            "matrix_sha256": self.matrix_sha256,
            "dataset_semantic_sha256": self.dataset_semantic_sha256,
            "base_config_sha256": self.base_config_sha256,
            "campaign_config_sha256": self.campaign_config_sha256,
            "evaluation_ids_sha256": self.evaluation_ids_sha256,
            "evaluation_count": self.evaluation_count,
            "code_revision": self.code_revision,
            "package_version": self.package_version,
            "signer_key_id": self.signer_key_id,
            "lineage_id": self.lineage_id,
            "reproducibility_scope": (
                "matrix identity, selected evaluation set, campaign policy, code "
                "revision, package version, and provenance signer"
            ),
            "evidence_boundary": (
                "Campaign identity and orchestration receipts do not prove market-data "
                "truth, strategy profitability, or release readiness."
            ),
        }


def load_campaign_spec(path: Path) -> CampaignSpecSnapshot:
    resolved = path.resolve()
    source_bytes = resolved.read_bytes()
    try:
        text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{resolved}: campaign configuration is not UTF-8") from error
    try:
        parsed = strict_yaml_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{resolved}: invalid campaign YAML: {error}") from error
    if not isinstance(parsed, dict):
        raise ValueError("campaign configuration must be a mapping")
    spec = parse_campaign_spec(cast(Mapping[str, Any], parsed))
    canonical_bytes = canonical_json_bytes(campaign_spec_payload(spec)) + b"\n"
    return CampaignSpecSnapshot(
        source_path=resolved,
        spec=spec,
        source_sha256=sha256_hex(source_bytes),
        canonical_sha256=sha256_hex(canonical_bytes),
        canonical_bytes=canonical_bytes,
        source_bytes=source_bytes,
    )


def parse_campaign_spec(payload: Mapping[str, Any]) -> CampaignSpec:
    _reject_unknown(
        "campaign",
        payload,
        {"schema_version", "execution", "selection"},
    )
    if payload.get("schema_version") != _CAMPAIGN_SCHEMA_VERSION:
        raise ValueError("campaign.schema_version must be 1")

    execution_payload = _section(payload, "execution")
    _reject_unknown(
        "campaign.execution",
        execution_payload,
        {
            "maximum_parallel_evaluations",
            "maximum_failures",
            "stop_on_failure",
        },
    )
    execution = CampaignExecutionPolicy(
        maximum_parallel_evaluations=_integer(
            execution_payload,
            "maximum_parallel_evaluations",
            1,
        ),
        maximum_failures=_integer(
            execution_payload,
            "maximum_failures",
            1,
        ),
        stop_on_failure=_boolean(
            execution_payload,
            "stop_on_failure",
            True,
        ),
    )

    selection_payload = _section(payload, "selection")
    _reject_unknown(
        "campaign.selection",
        selection_payload,
        {"include_evaluation_ids", "exclude_evaluation_ids"},
    )
    selection = CampaignSelection(
        include_evaluation_ids=_string_tuple(
            selection_payload.get("include_evaluation_ids", ()),
            "campaign.selection.include_evaluation_ids",
        ),
        exclude_evaluation_ids=_string_tuple(
            selection_payload.get("exclude_evaluation_ids", ()),
            "campaign.selection.exclude_evaluation_ids",
        ),
    )
    return CampaignSpec(execution=execution, selection=selection)


def campaign_spec_payload(spec: CampaignSpec) -> dict[str, Any]:
    return {
        "schema_version": _CAMPAIGN_SCHEMA_VERSION,
        "execution": {
            "maximum_parallel_evaluations": (
                spec.execution.maximum_parallel_evaluations
            ),
            "maximum_failures": spec.execution.maximum_failures,
            "stop_on_failure": spec.execution.stop_on_failure,
        },
        "selection": {
            "include_evaluation_ids": list(
                spec.selection.include_evaluation_ids
            ),
            "exclude_evaluation_ids": list(
                spec.selection.exclude_evaluation_ids
            ),
        },
    }


def resolve_campaign_evaluation_ids(
    matrix: ExperimentMatrixSnapshot,
    selection: CampaignSelection,
) -> tuple[str, ...]:
    matrix_ids = tuple(item.evaluation_id for item in matrix.evaluations)
    known = set(matrix_ids)
    requested = set(selection.include_evaluation_ids)
    excluded = set(selection.exclude_evaluation_ids)
    unknown_requested = sorted(requested - known)
    unknown_excluded = sorted(excluded - known)
    if unknown_requested:
        raise ValueError(
            "campaign includes unknown evaluations: "
            + ", ".join(unknown_requested)
        )
    if unknown_excluded:
        raise ValueError(
            "campaign excludes unknown evaluations: "
            + ", ".join(unknown_excluded)
        )
    selected = requested if requested else known
    result = tuple(
        evaluation_id
        for evaluation_id in matrix_ids
        if evaluation_id in selected and evaluation_id not in excluded
    )
    if not result:
        raise ValueError("campaign selection produced no evaluations")
    return result


def build_campaign_manifest(
    matrix: ExperimentMatrixSnapshot,
    campaign: CampaignSpecSnapshot,
    evaluation_ids: Sequence[str],
    *,
    code_revision: str,
    signer_key_id: str,
    lineage_id: str | None = None,
    package_version: str | None = None,
) -> CampaignManifest:
    normalized_revision = code_revision.strip()
    if not normalized_revision:
        raise ValueError("code_revision cannot be empty")
    if len(normalized_revision) > 160:
        raise ValueError("code_revision is too long")
    _validate_signer_key_id(signer_key_id)
    _validate_lineage_id(lineage_id)
    evaluation_ids_payload = list(evaluation_ids)
    if not evaluation_ids_payload:
        raise ValueError("campaign must contain at least one evaluation")
    _validate_unique_ids(tuple(evaluation_ids_payload), "evaluation_ids")
    evaluation_ids_sha256 = sha256_hex(
        canonical_json_bytes(evaluation_ids_payload)
    )
    identity = {
        "schema_version": _CAMPAIGN_SCHEMA_VERSION,
        "matrix_sha256": matrix.semantic_sha256,
        "dataset_semantic_sha256": matrix.dataset_semantic_sha256,
        "base_config_sha256": matrix.base_config_sha256,
        "campaign_config_sha256": campaign.canonical_sha256,
        "evaluation_ids_sha256": evaluation_ids_sha256,
        "code_revision": normalized_revision,
        "package_version": package_version or installed_package_version(),
        "signer_key_id": signer_key_id,
        "lineage_id": lineage_id,
    }
    digest = sha256_hex(canonical_json_bytes(identity))
    return CampaignManifest(
        campaign_id=f"campaign-{digest[:40]}",
        campaign_run_id=f"campaign-run-{digest[:32]}",
        matrix_sha256=matrix.semantic_sha256,
        dataset_semantic_sha256=matrix.dataset_semantic_sha256,
        base_config_sha256=matrix.base_config_sha256,
        campaign_config_sha256=campaign.canonical_sha256,
        evaluation_ids_sha256=evaluation_ids_sha256,
        evaluation_count=len(evaluation_ids_payload),
        code_revision=normalized_revision,
        package_version=str(identity["package_version"]),
        signer_key_id=signer_key_id,
        lineage_id=lineage_id,
    )


def campaign_id_from_identity(identity: Mapping[str, Any]) -> str:
    return f"campaign-{sha256_hex(canonical_json_bytes(identity))[:40]}"


def _section(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"campaign.{key} must be a mapping")
    return cast(Mapping[str, Any], value)


def _reject_unknown(
    name: str,
    payload: Mapping[str, Any],
    allowed: set[str],
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{name} contains unknown fields: {', '.join(unknown)}")


def _integer(payload: Mapping[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"campaign.{key} must be an integer")
    return value


def _boolean(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"campaign.{key} must be a boolean")
    return value


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{name} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _validate_unique_ids(values: tuple[str, ...], name: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{name} cannot contain duplicates")


def _validate_signer_key_id(value: str) -> None:
    suffix = value.removeprefix("ed25519-")
    if (
        not value.startswith("ed25519-")
        or len(suffix) != 32
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError("signer_key_id must use ed25519-<32 lowercase hex>")


def _validate_lineage_id(value: str | None) -> None:
    if value is None:
        return
    suffix = value.removeprefix("lineage-")
    if (
        not value.startswith("lineage-")
        or len(suffix) != 40
        or any(character not in "0123456789abcdef" for character in suffix)
    ):
        raise ValueError("lineage_id must use lineage-<40 lowercase hex>")
