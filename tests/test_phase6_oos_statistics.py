from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.evaluation import (
    load_experiment_matrix,
    run_planned_evaluation,
)
from llm_arbitrage_system.experiments.oos_statistics import (
    EvaluationValuationInput,
    build_oos_statistics,
)
from llm_arbitrage_system.experiments.registry import ExperimentRegistry
from llm_arbitrage_system.experiments.signing import (
    generate_signing_keypair,
    sign_bundle,
)
from llm_arbitrage_system.experiments.walk_forward import (
    load_sweep_spec,
    matrix_payload,
)


def _write_dataset(path: Path, event_count: int = 20) -> Path:
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    lines: list[str] = []
    for index in range(event_count):
        price = Decimal("100") + Decimal(index) / Decimal("10")
        hedge = price + Decimal("0.05")
        timestamp = (start + timedelta(minutes=index)).isoformat().replace(
            "+00:00", "Z"
        )
        payload = {
            "schema_version": 1,
            "venue": "paper",
            "symbol": "BTC",
            "instrument": "perp",
            "price": str(price),
            "timestamp": timestamp,
            "bid": str(price - Decimal("0.05")),
            "ask": str(price + Decimal("0.05")),
            "high": str(price + Decimal("0.1")),
            "low": str(price - Decimal("0.1")),
            "volume_24h": "1000000",
            "funding_rate_hourly": "0.0005",
            "sentiment_score": 0.0,
            "reference_price": None,
            "reference_market_open": None,
            "metadata": {
                "paper_hedge_symbol": "BTC-SPOT",
                "paper_hedge_price": str(hedge),
            },
        }
        lines.append(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_config(path: Path) -> Path:
    path.write_text(
        """schema_version: 1
analytics:
  efficiency_period: 2
  kama_fast_period: 2
  kama_slow_period: 10
  zscore_window: 3
  kalman_process_variance: 0.00001
  kalman_measurement_variance: 0.01
strategy:
  scenario_notional_usd: "100"
  estimated_round_trip_cost_bps: "12"
  funding_entry_apy_pct: "50"
  funding_holding_hours: "24"
  crowd_entry_zscore: 99.0
  crowd_efficiency_ratio_maximum: 0.2
  crowd_requires_sentiment: false
  lead_lag_entry_premium_bps: "150"
approval:
  maximum_event_age_seconds: 5.0
  minimum_edge_bps: "1"
  maximum_leg_notional_usd: "1000"
  maximum_gross_exposure_usd: "10000"
  maximum_leg_imbalance_pct: "0.02"
  maximum_slippage_bps: "50"
execution:
  slippage_bps: "5"
  fee_bps: "1"
  fail_leg_indexes: []
runtime:
  queue_size: 16
""",
        encoding="utf-8",
    )
    return path


def _write_sweep(path: Path, *, step_size: int) -> Path:
    path.write_text(
        f"""schema_version: 1
maximum_candidates: 2
parameters:
  strategy.funding_entry_apy_pct: ["50"]
walk_forward:
  train_size: 5
  purge_size: 0
  test_size: 5
  step_size: {step_size}
  anchored: false
  minimum_windows: 3
""",
        encoding="utf-8",
    )
    return path


def _write_matrix(
    path: Path,
    dataset_path: Path,
    config_path: Path,
    sweep_path: Path,
) -> Path:
    dataset = load_jsonl_dataset(dataset_path)
    config = load_experiment_config(config_path)
    payload = matrix_payload(
        dataset,
        config.config,
        load_sweep_spec(sweep_path),
    )
    path.write_bytes(canonical_json_bytes(payload) + b"\n")
    return path


def _write_marks(
    path: Path,
    *,
    last_event_at: str,
    spot: str,
    perp: str,
    lag_seconds: int = 60,
) -> Path:
    normalized = (
        last_event_at[:-1] + "+00:00"
        if last_event_at.endswith("Z")
        else last_event_at
    )
    timestamp = datetime.fromisoformat(normalized) + timedelta(seconds=lag_seconds)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "as_of": timestamp.isoformat().replace("+00:00", "Z"),
                "marks": [
                    {"symbol": "BTC-SPOT", "price": spot},
                    {"symbol": "BTC:PERP", "price": perp},
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    return path


async def _trusted_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, str, tuple[EvaluationValuationInput, ...]]:
    dataset_path = _write_dataset(tmp_path / "events.jsonl")
    config_path = _write_config(tmp_path / "experiment.yaml")
    sweep_path = _write_sweep(tmp_path / "sweep.yaml", step_size=5)
    matrix_path = _write_matrix(
        tmp_path / "matrix.json",
        dataset_path,
        config_path,
        sweep_path,
    )
    matrix = load_experiment_matrix(matrix_path)
    assert len(matrix.evaluations) == 3
    candidate_id = matrix.evaluations[0].candidate_id

    private_key = tmp_path / "keys/private.pem"
    public_key = tmp_path / "keys/public.pem"
    generate_signing_keypair(private_key, public_key)
    registry_path = tmp_path / "registry.sqlite3"
    with ExperimentRegistry(registry_path) as registry:
        registry.trust_public_key(public_key)

    mark_pairs = (("102", "100"), ("101", "100.5"), ("100", "102"))
    inputs: list[EvaluationValuationInput] = []
    for planned, (spot, perp) in zip(matrix.evaluations, mark_pairs, strict=True):
        result = await run_planned_evaluation(
            dataset_path=dataset_path,
            config_path=config_path,
            matrix_path=matrix_path,
            evaluation_id=planned.evaluation_id,
            output_root=tmp_path / "evaluations",
            code_revision="phase6-oos-fixture",
        )
        bundle = result.experiment.bundle.bundle_path
        attestation = tmp_path / "attestations" / (
            planned.evaluation_id + ".attestation.json"
        )
        sign_bundle(bundle, private_key, attestation)
        with ExperimentRegistry(registry_path) as registry:
            registry.register_evaluation(
                matrix_path=matrix_path,
                evaluation_id=planned.evaluation_id,
                bundle_path=bundle,
                attestation_path=attestation,
            )
        manifest = json.loads(
            (bundle / "manifest.json").read_text(encoding="utf-8")
        )
        marks_path = _write_marks(
            tmp_path / "marks" / (planned.evaluation_id + ".json"),
            last_event_at=str(manifest["dataset"]["last_event_at"]),
            spot=spot,
            perp=perp,
        )
        inputs.append(
            EvaluationValuationInput(
                evaluation_id=planned.evaluation_id,
                bundle_path=bundle,
                marks_path=marks_path,
            )
        )
    return registry_path, matrix_path, candidate_id, tuple(inputs)


@pytest.mark.asyncio
async def test_oos_statistics_are_deterministic_and_withhold_selection(
    tmp_path: Path,
) -> None:
    registry, matrix, candidate_id, inputs = await _trusted_fixture(tmp_path)
    first = build_oos_statistics(
        registry_path=registry,
        matrix_path=matrix,
        candidate_ids=(candidate_id,),
        valuation_inputs=inputs,
        initial_equity_usd=Decimal("100000"),
        periods_per_year=252,
        code_revision="phase6-oos-test",
        package_version="0.1.0",
    )
    second = build_oos_statistics(
        registry_path=registry,
        matrix_path=matrix,
        candidate_ids=(candidate_id,),
        valuation_inputs=inputs,
        initial_equity_usd=Decimal("100000"),
        periods_per_year=252,
        code_revision="phase6-oos-test",
        package_version="0.1.0",
    )

    assert first == second
    candidate = first.candidates[0]
    assert candidate.coverage == "complete"
    assert candidate.observed_evaluation_count == 3
    assert candidate.mark_lag_microseconds == 60_000_000
    assert candidate.annualized_sharpe_ratio is not None
    assert candidate.maximum_drawdown_pct > 0
    assert candidate.oos_pnl_slope_bps_per_window is not None
    assert candidate.oos_pnl_slope_bps_per_window < 0
    assert candidate.alpha_decay_bps_per_window is not None
    assert candidate.alpha_decay_bps_per_window > 0
    payload = first.as_dict()
    assert payload["selection"] is None
    assert "winner" not in payload


@pytest.mark.asyncio
async def test_oos_statistics_require_complete_non_overlapping_evidence(
    tmp_path: Path,
) -> None:
    registry, matrix, candidate_id, inputs = await _trusted_fixture(tmp_path)
    with pytest.raises(ValueError, match="missing valuation evidence"):
        build_oos_statistics(
            registry_path=registry,
            matrix_path=matrix,
            candidate_ids=(candidate_id,),
            valuation_inputs=inputs[:-1],
            initial_equity_usd=Decimal("100000"),
            periods_per_year=252,
            code_revision="phase6-oos-missing",
        )

    dataset = tmp_path / "events.jsonl"
    config = tmp_path / "experiment.yaml"
    overlapping_matrix = _write_matrix(
        tmp_path / "overlapping.json",
        dataset,
        config,
        _write_sweep(tmp_path / "overlapping-sweep.yaml", step_size=4),
    )
    overlapping = load_experiment_matrix(overlapping_matrix)
    with pytest.raises(ValueError, match="overlapping test windows"):
        build_oos_statistics(
            registry_path=registry,
            matrix_path=overlapping_matrix,
            candidate_ids=(overlapping.evaluations[0].candidate_id,),
            valuation_inputs=(inputs[0],),
            initial_equity_usd=Decimal("100000"),
            periods_per_year=252,
            code_revision="phase6-oos-overlap",
        )


@pytest.mark.asyncio
async def test_oos_statistics_reject_mixed_mark_lags_and_bundle_drift(
    tmp_path: Path,
) -> None:
    registry, matrix, candidate_id, inputs = await _trusted_fixture(tmp_path)
    last = inputs[-1]
    manifest = json.loads(
        (last.bundle_path / "manifest.json").read_text(encoding="utf-8")
    )
    mixed_marks = _write_marks(
        tmp_path / "mixed-lag.json",
        last_event_at=str(manifest["dataset"]["last_event_at"]),
        spot="100",
        perp="102",
        lag_seconds=120,
    )
    mixed_inputs = (*inputs[:-1], EvaluationValuationInput(
        evaluation_id=last.evaluation_id,
        bundle_path=last.bundle_path,
        marks_path=mixed_marks,
    ))
    with pytest.raises(ValueError, match="mixed terminal-mark lags"):
        build_oos_statistics(
            registry_path=registry,
            matrix_path=matrix,
            candidate_ids=(candidate_id,),
            valuation_inputs=mixed_inputs,
            initial_equity_usd=Decimal("100000"),
            periods_per_year=252,
            code_revision="phase6-oos-lag",
        )

    wrong_bundle_inputs = (
        inputs[0],
        EvaluationValuationInput(
            evaluation_id=inputs[1].evaluation_id,
            bundle_path=inputs[0].bundle_path,
            marks_path=inputs[1].marks_path,
        ),
        inputs[2],
    )
    with pytest.raises(ValueError, match="not the planned evaluation"):
        build_oos_statistics(
            registry_path=registry,
            matrix_path=matrix,
            candidate_ids=(candidate_id,),
            valuation_inputs=wrong_bundle_inputs,
            initial_equity_usd=Decimal("100000"),
            periods_per_year=252,
            code_revision="phase6-oos-drift",
        )


@pytest.mark.asyncio
async def test_oos_statistics_require_trusted_registry_evidence(
    tmp_path: Path,
) -> None:
    registry, matrix, candidate_id, inputs = await _trusted_fixture(tmp_path)
    connection = sqlite3.connect(registry)
    try:
        experiment_id = json.loads(
            (inputs[0].bundle_path / "manifest.json").read_text(encoding="utf-8")
        )["experiment_id"]
        connection.execute(
            "UPDATE experiments SET trusted = 0 WHERE experiment_id = ?",
            (experiment_id,),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PermissionError, match="trusted evaluation evidence"):
        build_oos_statistics(
            registry_path=registry,
            matrix_path=matrix,
            candidate_ids=(candidate_id,),
            valuation_inputs=inputs,
            initial_equity_usd=Decimal("100000"),
            periods_per_year=252,
            code_revision="phase6-oos-untrusted",
        )
