from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product
from typing import Any

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.config import (
    ExperimentConfig,
    apply_config_overrides,
    config_sha256,
)
from llm_arbitrage_system.experiments.dataset import DatasetSnapshot
from llm_arbitrage_system.experiments.sweep import (
    SweepSpec,
    WalkForwardSpec,
    load_sweep_spec,
)


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    def __post_init__(self) -> None:
        if not 0 <= self.train_start < self.train_end <= self.test_start < self.test_end:
            raise ValueError("walk-forward indexes are not ordered")

    @property
    def purge_size(self) -> int:
        return self.test_start - self.train_end

    def as_dict(self) -> dict[str, int]:
        return {
            "index": self.index,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "purge_size": self.purge_size,
        }


@dataclass(frozen=True, slots=True)
class ExperimentMatrixItem:
    evaluation_id: str
    candidate_id: str
    candidate_config_sha256: str
    overrides: Mapping[str, Any]
    window: WalkForwardWindow
    train_semantic_sha256: str
    test_semantic_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "candidate_id": self.candidate_id,
            "candidate_config_sha256": self.candidate_config_sha256,
            "overrides": dict(self.overrides),
            "window": self.window.as_dict(),
            "train_semantic_sha256": self.train_semantic_sha256,
            "test_semantic_sha256": self.test_semantic_sha256,
        }


def generate_walk_forward_windows(
    event_count: int,
    spec: WalkForwardSpec,
) -> tuple[WalkForwardWindow, ...]:
    if event_count < 1:
        raise ValueError("event_count must be positive")
    windows: list[WalkForwardWindow] = []
    offset = 0
    while True:
        train_start = 0 if spec.anchored else offset
        train_end = spec.train_size + offset
        test_start = train_end + spec.purge_size
        test_end = test_start + spec.test_size
        if test_end > event_count:
            break
        windows.append(
            WalkForwardWindow(
                index=len(windows),
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        offset += spec.step_size
    if len(windows) < spec.minimum_windows:
        raise ValueError(
            f"walk-forward plan produced {len(windows)} windows; "
            f"minimum is {spec.minimum_windows}"
        )
    return tuple(windows)


def expand_parameter_grid(spec: SweepSpec) -> tuple[dict[str, Any], ...]:
    names = sorted(spec.parameters)
    axes = [spec.parameters[name] for name in names]
    count = 1
    for axis in axes:
        count *= len(axis)
    if count > spec.maximum_candidates:
        raise ValueError(
            f"parameter grid contains {count} candidates; "
            f"maximum is {spec.maximum_candidates}"
        )
    return tuple(dict(zip(names, values, strict=True)) for values in product(*axes))


def build_experiment_matrix(
    dataset: DatasetSnapshot,
    base_config: ExperimentConfig,
    spec: SweepSpec,
) -> tuple[ExperimentMatrixItem, ...]:
    windows = generate_walk_forward_windows(dataset.event_count, spec.walk_forward)
    matrix: list[ExperimentMatrixItem] = []
    for overrides in expand_parameter_grid(spec):
        candidate_config = apply_config_overrides(base_config, overrides)
        candidate_hash = config_sha256(candidate_config)
        candidate_id = f"candidate-{candidate_hash[:24]}"
        for window in windows:
            train_hash = dataset.slice_semantic_sha256(
                window.train_start, window.train_end
            )
            test_hash = dataset.slice_semantic_sha256(
                window.test_start, window.test_end
            )
            identity = {
                "schema_version": 1,
                "candidate_config_sha256": candidate_hash,
                "dataset_semantic_sha256": dataset.semantic_sha256,
                "window": window.as_dict(),
                "train_semantic_sha256": train_hash,
                "test_semantic_sha256": test_hash,
            }
            evaluation_id = (
                f"evaluation-{sha256_hex(canonical_json_bytes(identity))[:32]}"
            )
            matrix.append(
                ExperimentMatrixItem(
                    evaluation_id=evaluation_id,
                    candidate_id=candidate_id,
                    candidate_config_sha256=candidate_hash,
                    overrides=overrides,
                    window=window,
                    train_semantic_sha256=train_hash,
                    test_semantic_sha256=test_hash,
                )
            )
    return tuple(matrix)


def matrix_payload(
    dataset: DatasetSnapshot,
    base_config: ExperimentConfig,
    spec: SweepSpec,
) -> dict[str, Any]:
    candidates = expand_parameter_grid(spec)
    windows = generate_walk_forward_windows(dataset.event_count, spec.walk_forward)
    items = build_experiment_matrix(dataset, base_config, spec)
    return {
        "schema_version": 1,
        "dataset_semantic_sha256": dataset.semantic_sha256,
        "base_config_sha256": config_sha256(base_config),
        "candidate_count": len(candidates),
        "window_count": len(windows),
        "evaluation_count": len(items),
        "evaluations": [item.as_dict() for item in items],
        "evidence_boundary": (
            "This matrix enforces deterministic train/purge/test boundaries; "
            "it does not select a profitable model."
        ),
    }


__all__ = [
    "ExperimentMatrixItem",
    "SweepSpec",
    "WalkForwardSpec",
    "WalkForwardWindow",
    "build_experiment_matrix",
    "expand_parameter_grid",
    "generate_walk_forward_windows",
    "load_sweep_spec",
    "matrix_payload",
]
