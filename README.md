# LLM Arbitrage System

A credential-free, paper-only research harness derived from the supplied *Trading Systems and Methods 資源* architecture. It studies deterministic funding carry, overcrowding reversion, and RWA lead-lag scenarios without connecting to accounts, wallets, brokers, exchanges, or withdrawal endpoints.

## Runtime, evidence, and trust state machine

```text
schema-v1 MarketEvent JSONL
  -> strict validation + canonical serialization
  -> content-addressed experiment manifest
  -> AnalyticsEngine
  -> PaperStrategyRouter
  -> StatefulPaperApprover
  -> DeterministicPaperExecutor
  -> SQLiteReplayJournal
  -> reports + checksummed evidence bundle
  -> detached Ed25519 attestation
  -> optional dataset-lineage DAG
  -> trusted local experiment registry
  -> matrix-bound test evaluation aggregation
```

The bounded `asyncio.Queue` pipeline keeps ingestion, planning, approval, and execution simulation independent. Phase 4 adds trust and out-of-sample registration around that offline data plane; it does not add a live execution path.

## Implemented phases

| Layer | Current implementation |
| --- | --- |
| Domain | Immutable typed contracts, timezone-aware timestamps, and `Decimal` |
| Analytics | Kaufman ER/KAMA, rolling Z-score, ATR percentage, and Kalman filtering |
| Strategy | Paper-only funding carry, crowding reversion, and RWA lead-lag |
| Approval | Freshness, edge, notional, exposure, duplicate, balance, and slippage gates |
| Simulation | Deterministic multi-leg fills and partial-outcome compensation |
| Evidence | Append-only SQLite journal, reports, manifests, checksums, and verification |
| Experiments | Strict inputs, semantic identities, deterministic IDs, grids, and purged walk-forward plans |
| Provenance | Detached Ed25519 attestations and trusted-public-key verification |
| Lineage | Content-addressed dataset DAG with parent-before-child imports |
| OOS registry | Trusted immutable bundle imports, matrix-bound evaluations, and coverage aggregation |
| CI | Ruff, strict Mypy, coverage, Python 3.10–3.13, Phase 3 and Phase 4 smoke paths |

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Reproducible experiment

```bash
llm-arbitrage run \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --output experiment-runs \
  --code-revision "$(git rev-parse HEAD)"

BUNDLE="$(find experiment-runs -mindepth 1 -maxdepth 1 -type d -name 'exp-*' -print -quit)"
llm-arbitrage verify "$BUNDLE"

llm-arbitrage plan-matrix \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --sweep examples/phase3/sweep.yaml \
  --output experiment-runs/matrix.json
```

## Phase 4 provenance and registry

```bash
llm-arbitrage keygen \
  --private-key .phase4-keys/provenance.pem \
  --public-key .phase4-keys/provenance.pub.pem

llm-arbitrage validate-lineage examples/phase4/lineage.yaml

llm-arbitrage sign-bundle \
  --bundle "$BUNDLE" \
  --private-key .phase4-keys/provenance.pem \
  --lineage examples/phase4/lineage.yaml \
  --output experiment-runs/base.attestation.json

llm-arbitrage verify-attestation \
  --bundle "$BUNDLE" \
  --attestation experiment-runs/base.attestation.json \
  --trusted-public-key .phase4-keys/provenance.pub.pem \
  --lineage examples/phase4/lineage.yaml

llm-arbitrage registry-init state/experiments.registry.sqlite3
llm-arbitrage registry-trust-key \
  state/experiments.registry.sqlite3 \
  .phase4-keys/provenance.pub.pem
llm-arbitrage registry-import-lineage \
  state/experiments.registry.sqlite3 \
  examples/phase4/lineage.yaml
llm-arbitrage registry-import-bundle \
  state/experiments.registry.sqlite3 \
  "$BUNDLE" \
  experiment-runs/base.attestation.json
```

`run-evaluation` executes exactly one matrix test slice. `registry-register-evaluation` verifies its candidate, configuration, window, and test-slice binding. `registry-aggregate` reports complete, partial, and missing coverage without choosing a winner.

## Evidence boundaries

A verified checksum bundle proves internal consistency. A valid Ed25519 attestation proves that one local provenance key signed the captured bundle identity. Neither proves data authenticity, legal identity, realized profit, future performance, or risk-free returns. Drawdown, Sharpe, and alpha decay remain unset unless their specific evidence contracts are met.

Private provenance keys are not trading credentials, but they are still secrets. Keep them outside the repository and evidence bundles. Generated private files use mode `0600`.

## Verify the repository

```bash
make check
make phase3-smoke
make phase4-smoke
```

## Change index

```text
main
├── PR #1  Phase 1: contracts and adaptive analytics
├── PR #3  Phase 2: offline strategy, approval, and simulation core
├── PR #4  Phase 2B: durable evidence, reports, and CI
├── PR #6  Phase 3: reproducible content-addressed experiments
└── Phase 4: signed provenance, lineage, and OOS registry
```

## Non-goals

This repository does not contain exchange API secrets, wallet keys, account registration automation, withdrawal functions, external order endpoints, venue SDKs, network probes, or a live-mode branch. It does not promise arbitrage profitability or protection from model and market risk.
