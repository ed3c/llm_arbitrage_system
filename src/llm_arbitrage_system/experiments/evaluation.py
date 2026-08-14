from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from llm_arbitrage_system.experiments.bundle import verify_bundle
from llm_arbitrage_system.experiments.bundle_io import write_checksums, write_json
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.config import (
    apply_config_overrides,
    config_canonical_bytes,
    config_sha256,
    load_experiment_config,
)
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.runner import ExperimentRunResult, run_experiment


@dataclass(frozen=True, slots=True)
class MatrixEvaluation:
    evaluation_id: str
    candidate_id: str
    candidate_config_sha256: str
    overrides: dict[str, Any]
    window: dict[str, int]
    train_semantic_sha256: str
    test_semantic_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "overrides": self.overrides,
            "window": self.window,
            "train_semantic_sha256": self.train_semantic_sha256,
            "test_semantic_sha256": self.test_semantic_sha256,
        }


@dataclass(frozen=True, slots=True)
class ExperimentMatrixSnapshot:
    source_path: Path
    dataset_semantic_sha256: str
    base_config_sha256: str
    evaluations: tuple[MatrixEvaluation, ...]
    semantic_sha256: str
    canonical_bytes: bytes = field(repr=False)

    def evaluation(self, evaluation_id: str) -> MatrixEvaluation:
        matches = [item for item in self.evaluations if item.evaluation_id == evaluation_id]
        if len(matches) != 1:
            raise ValueError(f"matrix must contain evaluation_id exactly once: {evaluation_id}")
        return matches[0]


@dataclass(frozen=True, slots=True)
class PlannedEvaluationRunResult:
    matrix_sha256: str
    evaluation: MatrixEvaluation
    experiment: ExperimentRunResult
    evaluation_path: Path

    def as_dict(self) -> dict[str, Any]:
        return {
            "matrix_sha256": self.matrix_sha256,
            "evaluation": self.evaluation.as_dict(),
            "experiment": self.experiment.as_dict(),
            "evaluation_path": str(self.evaluation_path),
        }


def load_experiment_matrix(path: Path) -> ExperimentMatrixSnapshot:
    resolved = path.resolve()
    try:
        parsed = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid experiment matrix: {resolved}") from error
    if not isinstance(parsed, dict):
        raise ValueError("experiment matrix must contain an object")
    payload = cast(dict[str, Any], parsed)
    if payload.get("schema_version") != 1:
        raise ValueError("matrix schema_version must be 1")
    dataset_hash = _sha256(payload.get("dataset_semantic_sha256"), "dataset hash")
    base_config_hash = _sha256(payload.get("base_config_sha256"), "base config hash")
    raw = payload.get("evaluations")
    if not isinstance(raw, list):
        raise ValueError("matrix evaluations must be a sequence")
    evaluations = tuple(_parse_evaluation(item) for item in raw)
    if len({item.evaluation_id for item in evaluations}) != len(evaluations):
        raise ValueError("matrix evaluation_id values must be unique")
    if _required_int(payload, "evaluation_count") != len(evaluations):
        raise ValueError("matrix evaluation_count does not match evaluations")
    canonical = canonical_json_bytes(payload) + b"\n"
    return ExperimentMatrixSnapshot(
        source_path=resolved,
        dataset_semantic_sha256=dataset_hash,
        base_config_sha256=base_config_hash,
        evaluations=evaluations,
        semantic_sha256=sha256_hex(canonical),
        canonical_bytes=canonical,
    )


async def run_planned_evaluation(
    *,
    dataset_path: Path,
    config_path: Path,
    matrix_path: Path,
    evaluation_id: str,
    output_root: Path,
    code_revision: str | None = None,
    lineage_id: str | None = None,
    force: bool = False,
) -> PlannedEvaluationRunResult:
    dataset = load_jsonl_dataset(dataset_path)
    config_snapshot = load_experiment_config(config_path)
    matrix = load_experiment_matrix(matrix_path)
    if matrix.dataset_semantic_sha256 != dataset.semantic_sha256:
        raise ValueError("matrix dataset hash does not match the supplied dataset")
    if matrix.base_config_sha256 != config_snapshot.canonical_sha256:
        raise ValueError("matrix base config hash does not match the supplied config")
    evaluation = matrix.evaluation(evaluation_id)
    candidate = apply_config_overrides(config_snapshot.config, evaluation.overrides)
    if config_sha256(candidate) != evaluation.candidate_config_sha256:
        raise ValueError("planned candidate hash does not match its overrides")
    window = evaluation.window
    if dataset.slice_semantic_sha256(
        window["train_start"], window["train_end"]
    ) != evaluation.train_semantic_sha256:
        raise ValueError("planned train slice hash does not match the dataset")
    if dataset.slice_semantic_sha256(
        window["test_start"], window["test_end"]
    ) != evaluation.test_semantic_sha256:
        raise ValueError("planned test slice hash does not match the dataset")

    with tempfile.TemporaryDirectory(prefix="llm-arbitrage-evaluation-") as temporary:
        root = Path(temporary)
        test_path = root / "test.jsonl"
        config_path_temporary = root / "candidate.yaml"
        lines = dataset.canonical_jsonl.splitlines(keepends=True)
        test_path.write_bytes(b"".join(lines[window["test_start"] : window["test_end"]]))
        config_path_temporary.write_bytes(config_canonical_bytes(candidate))
        experiment = await run_experiment(
            dataset_path=test_path,
            config_path=config_path_temporary,
            output_root=output_root,
            code_revision=code_revision,
            force=force,
        )

    if experiment.manifest.dataset_semantic_sha256 != evaluation.test_semantic_sha256:
        raise RuntimeError("evaluation bundle is not the planned test slice")
    if experiment.manifest.config_canonical_sha256 != evaluation.candidate_config_sha256:
        raise RuntimeError("evaluation bundle is not the planned candidate")
    record = {
        "schema_version": 1,
        "evaluation_id": evaluation.evaluation_id,
        "candidate_id": evaluation.candidate_id,
        "candidate_config_sha256": evaluation.candidate_config_sha256,
        "matrix_sha256": matrix.semantic_sha256,
        "source_dataset_semantic_sha256": dataset.semantic_sha256,
        "train_semantic_sha256": evaluation.train_semantic_sha256,
        "test_semantic_sha256": evaluation.test_semantic_sha256,
        "window": evaluation.window,
        "overrides": evaluation.overrides,
        "experiment_id": experiment.manifest.experiment_id,
        "run_id": experiment.manifest.run_id,
        "lineage_id": lineage_id,
        "evidence_boundary": "Only the planned test slice was replayed; no winner was selected.",
    }
    bundle = experiment.bundle.bundle_path
    evaluation_path = bundle / "evaluation.json"
    write_json(evaluation_path, record)
    write_checksums(bundle)
    verification = verify_bundle(bundle)
    return PlannedEvaluationRunResult(
        matrix_sha256=matrix.semantic_sha256,
        evaluation=evaluation,
        experiment=ExperimentRunResult(
            manifest=experiment.manifest,
            bundle=verification,
            replay_report=experiment.replay_report,
            performance_report=experiment.performance_report,
        ),
        evaluation_path=evaluation_path,
    )


def load_evaluation_record(bundle_path: Path) -> dict[str, Any]:
    path = bundle_path.resolve() / "evaluation.json"
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid evaluation record: {path}") from error
    if not isinstance(parsed, dict) or parsed.get("schema_version") != 1:
        raise ValueError("evaluation record must be a schema-v1 object")
    return cast(dict[str, Any], parsed)


def _parse_evaluation(value: Any) -> MatrixEvaluation:
    if not isinstance(value, dict):
        raise ValueError("matrix evaluation must be an object")
    payload = cast(dict[str, Any], value)
    overrides = payload.get("overrides")
    window_value = payload.get("window")
    if not isinstance(overrides, dict) or not isinstance(window_value, dict):
        raise ValueError("matrix evaluation overrides/window must be objects")
    window_payload = cast(dict[str, Any], window_value)
    keys = ("index", "train_start", "train_end", "test_start", "test_end", "purge_size")
    window = {key: _required_int(window_payload, key) for key in keys}
    if not (
        0 <= window["train_start"] < window["train_end"] <= window["test_start"] < window["test_end"]
    ):
        raise ValueError("matrix evaluation indexes are not ordered")
    return MatrixEvaluation(
        evaluation_id=_required_string(payload, "evaluation_id"),
        candidate_id=_required_string(payload, "candidate_id"),
        candidate_config_sha256=_sha256(payload.get("candidate_config_sha256"), "candidate hash"),
        overrides=cast(dict[str, Any], overrides),
        window=window,
        train_semantic_sha256=_sha256(payload.get("train_semantic_sha256"), "train hash"),
        test_semantic_sha256=_sha256(payload.get("test_semantic_sha256"), "test hash"),
    )


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value
