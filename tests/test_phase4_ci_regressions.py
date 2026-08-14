from __future__ import annotations

from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.config import (
    ExperimentConfig,
    experiment_config_payload,
    load_experiment_config,
    parse_experiment_config,
)


def test_canonical_config_round_trips_scientific_float_notation(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    source = load_experiment_config(root / "examples" / "phase3" / "experiment.yaml")
    canonical_path = tmp_path / "candidate.yaml"
    canonical_path.write_bytes(source.canonical_bytes)

    restored = load_experiment_config(canonical_path)

    assert restored.config == source.config
    assert restored.canonical_sha256 == source.canonical_sha256
    assert restored.config.analytics.kalman_process_variance == pytest.approx(1e-5)


def test_scientific_float_string_is_accepted_for_non_monetary_parameter() -> None:
    payload = experiment_config_payload(ExperimentConfig())
    payload["analytics"]["kalman_process_variance"] = "1e-05"

    parsed = parse_experiment_config(payload)

    assert parsed.analytics.kalman_process_variance == pytest.approx(1e-5)


@pytest.mark.parametrize("invalid", [True, "not-a-number", "NaN", "Infinity", "-Infinity"])
def test_invalid_or_non_finite_float_values_still_fail_closed(invalid: object) -> None:
    payload = experiment_config_payload(ExperimentConfig())
    payload["analytics"]["kalman_process_variance"] = invalid

    with pytest.raises(ValueError):
        parse_experiment_config(payload)
