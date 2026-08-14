# LLM Arbitrage System

A credential-free, paper-only research harness derived from the supplied *Trading Systems and Methods 資源* architecture. The repository studies three deterministic scenarios—funding carry, overcrowding reversion, and RWA lead-lag—without connecting to accounts, wallets, brokers, exchanges, or withdrawal endpoints.

## Runtime and evidence state machine

```text
schema-v1 MarketEvent JSONL
  -> strict validation + canonical serialization
  -> content-addressed experiment manifest
  -> AnalyticsEngine
  -> PaperStrategyRouter
  -> StatefulPaperApprover
  -> DeterministicPaperExecutor
  -> SQLiteReplayJournal
  -> ResearchPerformanceReport
  -> checksummed evidence bundle
  -> independent bundle verification
```

The bounded `asyncio.Queue` pipeline keeps ingestion, analytics/planning, approval, and execution simulation independent. Every terminal result is sent back to a compatible approver for reservation reconciliation before the run is considered complete.

## Implemented phases

| Layer | Current implementation |
| --- | --- |
| Domain | Immutable, typed contracts using timezone-aware timestamps and `Decimal` |
| Analytics | Kaufman ER/KAMA, rolling Z-score, ATR percentage, one-dimensional Kalman filter |
| Strategy | Paper-only funding carry, crowding reversion, and RWA lead-lag routing |
| Approval | Freshness, edge, notional, exposure, duplicate-position, balance, and slippage gates |
| Simulation | Deterministic multi-leg fills and reversal of partial outcomes |
| Evidence | Append-only SQLite replay journal with WAL, full synchronization, run status, and integrity checks |
| Reporting | Execution quality, fees, turnover, edge-after-cost, optional drawdown/Sharpe, and explicit unsupported-metric notes |
| Experiments | Strict JSONL/YAML inputs, semantic hashes, deterministic identifiers, manifests, bundles, verification, parameter grids, and purged walk-forward plans |
| CI | Ruff, strict Mypy, coverage gate, Python 3.10–3.13, and a Phase 3 CLI smoke run |

## Phase 3 quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

llm-arbitrage validate-dataset examples/phase3/market_events.jsonl
llm-arbitrage validate-config examples/phase3/experiment.yaml

llm-arbitrage run \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --output .phase3-runs \
  --code-revision "$(git rev-parse HEAD)"

BUNDLE="$(find .phase3-runs -mindepth 1 -maxdepth 1 -type d -name 'exp-*' -print -quit)"
llm-arbitrage verify "$BUNDLE"

llm-arbitrage plan-matrix \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --sweep examples/phase3/sweep.yaml \
  --output .phase3-runs/matrix.json
```

The `run` command refuses to overwrite an existing experiment by default. `--force` is explicit and should only be used when replacing local disposable evidence.

## Evidence bundle

```text
exp-<semantic-identity>/
├── checksums.sha256
├── evidence.sqlite3
├── manifest.json
├── replay_report.json
├── performance_report.json
├── report.md
└── inputs/
    ├── dataset.source.jsonl
    ├── dataset.canonical.jsonl
    ├── config.source.yaml
    └── config.canonical.json
```

`verify` checks the complete file set, SHA-256 values, manifest identity, raw-to-canonical input linkage, event metadata, SQLite integrity, the single replay `run_id`, and the terminal `completed` state. This is integrity and provenance evidence, not a digital signature or a profitability claim.

## Walk-forward boundary

`plan-matrix` creates a deterministic Cartesian parameter grid and rolling or anchored train/purge/test windows. It caps candidate count and records semantic hashes for each train and test slice. It does not automatically select a profitable candidate or populate alpha-decay metrics.

## Evidence boundaries

Execution cost and net settlement cash flow are replay evidence, not realized strategy profit. Drawdown and Sharpe are only produced when a caller supplies an explicit realized PnL series and initial equity. Alpha decay remains unset until repeated out-of-sample windows provide the required evidence.

## Verify the repository

```bash
make check
make phase3-smoke
```

## Change index

```text
main
├── PR #1  Phase 1: contracts and adaptive analytics
├── PR #3  Phase 2: offline strategy, approval, and simulation core
├── PR #4  Phase 2B: durable evidence, reports, and CI
└── Phase 3: reproducible content-addressed experiment runner
```

## Non-goals

This repository does not contain private keys, API secrets, account registration automation, withdrawal functions, external order endpoints, venue SDKs, network probes, or a live-mode branch. It does not promise arbitrage profitability, risk-free returns, or protection from model and market risk.
