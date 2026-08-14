from __future__ import annotations

from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.config import ExperimentConfig
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.walk_forward import (
    SweepSpec,
    WalkForwardSpec,
    build_experiment_matrix,
    expand_parameter_grid,
    generate_walk_forward_windows,
    load_sweep_spec,
)


def test_walk_forward_windows_enforce_purge_gap() -> None:
    spec = WalkForwardSpec(
        train_size=6,
        test_size=3,
        step_size=2,
        purge_size=1,
        minimum_windows=2,
    )
    windows = generate_walk_forward_windows(12, spec)

    assert [window.as_dict() for window in windows] == [
        {
            "index": 0,
            "train_start": 0,
            "train_end": 6,
            "test_start": 7,
            "test_end": 10,
            "purge_size": 1,
        },
        {
            "index": 1,
            "train_start": 2,
            "train_end": 8,
            "test_start": 9,
            "test_end": 12,
            "purge_size": 1,
        },
    ]


def test_parameter_grid_is_canonical_and_bounded() -> None:
    spec = SweepSpec(
        parameters={
            "strategy.funding_entry_apy_pct": ("60", "40"),
            "analytics.efficiency_period": (3, 2),
        },
        walk_forward=WalkForwardSpec(train_size=2, test_size=1, step_size=1),
        maximum_candidates=4,
    )
    assert expand_parameter_grid(spec) == (
        {
            "analytics.efficiency_period": 3,
            "strategy.funding_entry_apy_pct": "60",
        },
        {
            "analytics.efficiency_period": 3,
            "strategy.funding_entry_apy_pct": "40",
        },
        {
            "analytics.efficiency_period": 2,
            "strategy.funding_entry_apy_pct": "60",
        },
        {
            "analytics.efficiency_period": 2,
            "strategy.funding_entry_apy_pct": "40",
        },
    )

    too_small = SweepSpec(
        parameters=spec.parameters,
        walk_forward=spec.walk_forward,
        maximum_candidates=3,
    )
    with pytest.raises(ValueError, match="4 candidates"):
        expand_parameter_grid(too_small)


def test_experiment_matrix_has_stable_evaluation_ids() -> None:
    root = Path(__file__).parents[1]
    dataset = load_jsonl_dataset(root / "examples" / "phase3" / "market_events.jsonl")
    spec = SweepSpec(
        parameters={"strategy.funding_entry_apy_pct": ("40", "50")},
        walk_forward=WalkForwardSpec(
            train_size=6,
            test_size=3,
            step_size=2,
            purge_size=1,
            minimum_windows=2,
        ),
    )

    first = build_experiment_matrix(dataset, ExperimentConfig(), spec)
    second = build_experiment_matrix(dataset, ExperimentConfig(), spec)

    assert len(first) == 4
    assert [item.evaluation_id for item in first] == [item.evaluation_id for item in second]
    assert all(item.train_semantic_sha256 != item.test_semantic_sha256 for item in first)


def test_sweep_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-sweep.yaml"
    path.write_text(
        "schema_version: 1\nmaximum_candidates: 4\nmaximum_candidates: 8\n"
        "parameters:\n  analytics.efficiency_period: [2]\n"
        "walk_forward:\n  train_size: 2\n  test_size: 1\n  step_size: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate key"):
        load_sweep_spec(path)
