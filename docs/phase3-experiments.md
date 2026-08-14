# Phase 3 reproducible experiments

Phase 3 turns the deterministic paper runtime into a repeatable experiment compiler. It connects one validated dataset, one behavior configuration, one code revision, and one package version to one content-addressed evidence bundle.

## Commands

```bash
llm-arbitrage validate-dataset DATASET.jsonl
llm-arbitrage validate-config EXPERIMENT.yaml
llm-arbitrage run --dataset DATASET.jsonl --config EXPERIMENT.yaml --output RUNS
llm-arbitrage verify RUNS/exp-...
llm-arbitrage plan-matrix \
  --dataset DATASET.jsonl \
  --config EXPERIMENT.yaml \
  --sweep SWEEP.yaml \
  --output matrix.json
```

Exit code `0` means success. Validation or verification errors return `2` and do not publish a completed bundle.

## Dataset schema

Each JSONL line is one schema-v1 `MarketEvent` object. Required fields are:

```json
{
  "schema_version": 1,
  "venue": "paper",
  "symbol": "BTC",
  "instrument": "perp",
  "price": "100.0",
  "timestamp": "2026-01-01T00:00:00Z"
}
```

Optional fields are `bid`, `ask`, `high`, `low`, `volume_24h`, `funding_rate_hourly`, `sentiment_score`, `reference_price`, `reference_market_open`, and `metadata`.

Prices, notional-related values, rates, and other decimal fields must use JSON strings or integers. JSON floats are rejected for monetary fields because binary floating-point text cannot preserve the intended decimal contract. Timestamps must include a timezone and records must be globally non-decreasing. Blank records, BOMs, duplicate object keys, unknown fields, unsupported enum values, and non-finite values fail closed.

## Experiment configuration

`experiment.yaml` contains five behavior sections:

- `analytics`: Kaufman, Z-score, ATR, and Kalman windows/variances.
- `strategy`: scenario notional, cost estimate, funding, crowding, and lead-lag thresholds.
- `approval`: freshness, edge, notional, exposure, balance, and slippage limits.
- `execution`: deterministic slippage, fees, and injected failed leg indexes.
- `runtime`: bounded queue size.

Duplicate or unknown YAML keys are rejected. Decimal behavior fields should be quoted strings. Canonical JSON removes YAML formatting and mapping-order differences before hashing.

## Identity

```text
experiment_id = SHA256(
  bundle_schema_version
  + dataset_semantic_sha256
  + config_canonical_sha256
  + code_revision
  + package_version
)
```

The raw source SHA-256 values remain in the manifest for provenance but are not semantic identity fields. This allows harmless whitespace or key-order changes to keep the same experiment identity while still recording the exact source bytes used.

`ContentAddressedPlanner` replaces UUID-generated plan and leg IDs with hashes derived from the semantic dataset, feature sequence, event, feature snapshot, and plan semantics. The deterministic paper executor then derives fill IDs from the plan and leg index.

## Bundle publication

A run writes to `.<experiment_id>.staging`. The target directory is published only after:

1. All queue stages terminate successfully.
2. Replay and performance reports are persisted.
3. The SQLite run status is `completed`.
4. SQLite `PRAGMA integrity_check` returns `ok`.
5. WAL content is checkpointed.
6. Manifest and reports are written.
7. Checksums are generated.
8. The staging bundle verifies successfully.

An existing target is not overwritten unless the caller explicitly supplies `--force`.

## Independent verification

`llm-arbitrage verify` checks:

- exact file set with no unexpected or missing files
- lowercase SHA-256 digests and safe relative paths
- absence of symbolic links
- manifest experiment identity
- raw source hashes
- source-to-canonical dataset and configuration equivalence
- event count and first/last timestamps
- exactly one SQLite replay run
- manifest/SQLite run ID equality
- `completed` terminal state
- SQLite integrity

The bundle is not cryptographically signed. A trusted release process may add signatures later without changing the semantic experiment identity.

## Parameter grids and walk-forward windows

`sweep.yaml` defines a bounded Cartesian grid plus rolling or anchored windows:

```yaml
schema_version: 1
maximum_candidates: 16
parameters:
  strategy.funding_entry_apy_pct: ["40", "50", "60"]
  analytics.efficiency_period: [2, 3]
walk_forward:
  train_size: 6
  purge_size: 1
  test_size: 3
  step_size: 2
  anchored: false
  minimum_windows: 2
```

The matrix contains candidate configuration hashes, overrides, window indexes, train/test semantic hashes, and stable evaluation IDs. The purge region is explicit to reduce temporal leakage. Phase 3 plans evaluations but does not automatically choose a winner, calculate alpha decay, or treat in-sample results as evidence of future returns.

## Evidence boundary

A verified bundle proves internal consistency of the captured offline evidence. It does not prove who produced the bundle, that the source market data is authentic, that the strategy is profitable, or that any opportunity is risk-free.
