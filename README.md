<!-- i18n-key: README; locale: en; reviewed: 2026-08-15 -->
[English](README.md) · [繁體中文](README.zh-TW.md)

# LLM Arbitrage System

[![CI](https://github.com/ed3c/llm_arbitrage_system/actions/workflows/ci.yml/badge.svg)](https://github.com/ed3c/llm_arbitrage_system/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10–3.13](https://img.shields.io/badge/Python-3.10%E2%80%933.13-blue.svg)](pyproject.toml)

**A deterministic, paper-only research harness for strategy replay, risk-gated execution simulation, reproducible experiments, and evidence-bound evaluation.**

> **Maturity:** research software. The repository does not connect to exchanges, brokers, wallets, deposits, withdrawals, live market WebSockets, or order endpoints. It does not establish profitability, financial suitability, or permission to trade.

## Why this project exists

Market research prototypes often mix strategy logic, risk decisions, simulated fills, performance reporting, model selection, and deployment claims. That makes failures hard to reproduce and lets a successful-looking result hide weak lineage or unsafe assumptions.

LLM Arbitrage System separates those responsibilities into typed State Machines and durable evidence:

```text
offline market events
→ adaptive analytics
→ paper strategy proposal
→ risk and capacity approval
→ deterministic simulated execution
→ append-only replay evidence
→ reproducible experiment bundle
→ trusted out-of-sample evaluation
→ valuation and selection diagnostics
→ independent human review
```

Each later phase may add evidence. It does not gain trading, release, or deployment authority.

## Core capabilities

| Area | What is implemented on `main` |
|---|---|
| Domain contracts | Immutable typed events, plans, approvals, fills, reports, timezone-aware timestamps, and exact decimal values |
| Analytics | Kaufman efficiency ratio, KAMA, rolling Z-score, ATR percentage, and Kalman filtering |
| Strategy routing | Offline paper scenarios for funding carry, overcrowding reversion, and RWA lead-lag |
| Risk control | Freshness, edge, notional, exposure, duplicate, balance, and slippage gates |
| Simulation | Bounded queue orchestration, deterministic concurrent fills, failure injection, compensation, and residual-risk handling |
| Evidence | Append-only SQLite lifecycle, events, decisions, risk checks, results, reports, and integrity checks |
| Experiments | Strict JSONL/YAML inputs, semantic IDs, content-addressed bundles, sweeps, walk-forward plans, and replay verification |
| Trust and evaluation | Ed25519 attestations, lineage DAG, trusted local registry, out-of-sample evaluation, and coverage aggregation |
| Governance | Resumable campaigns, terminal valuation, selection diagnostics, and signed independent-review records |

The exact merged, open, planned, and blocked state is maintained in [`docs/integration-status.md`](docs/integration-status.md). Open Pull Requests are not part of the supported `main` capability until merged.

## Architecture

```mermaid
flowchart LR
    A[Offline JSONL market events] --> B[Typed dataset validation]
    B --> C[Adaptive analytics]
    C --> D[Paper strategy router]
    D --> E[Risk and capacity approval]
    E -->|rejected| J[(Replay journal)]
    E -->|approved| F[Deterministic paper executor]
    F --> G[Compensation / reconciliation]
    G --> J
    J --> H[Experiment bundle + verification]
    H --> I[Trusted OOS registry]
    I --> K[Valuation + selection diagnostics]
    K --> L[Independent human review]
```

See [`docs/architecture.md`](docs/architecture.md), [`docs/state-machines.md`](docs/state-machines.md), and [`docs/data-flow.md`](docs/data-flow.md) for transition ownership and failure behavior.

## Quick start

### Requirements

- Python 3.10–3.13
- Git
- No exchange, broker, wallet, or model-provider credential is required for the deterministic local path

```bash
git clone https://github.com/ed3c/llm_arbitrage_system.git
cd llm_arbitrage_system

python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

llm-arbitrage --help
make check
```

Run the Phase 3 deterministic experiment smoke:

```bash
make phase3-smoke
```

Additional offline gates are available as:

```bash
make phase4-smoke
make phase5-smoke
make phase6-smoke
make phase7-smoke
make phase8-smoke
```

These commands prove only the behavior and evidence captured by their local fixtures. They do not prove live market data quality, independent cohort construction, causal alpha, future returns, release readiness, or trading safety.

## Evidence model

The repository keeps the following claims separate:

```text
code exists
!= command is reachable
!= deterministic test passed
!= hosted CI passed
!= evidence bundle verified
!= trusted OOS evaluation passed
!= independent review approved
!= release authorized
!= live trading authorized
```

Identifiers, source hashes, configuration hashes, code revision, package version, signer identity, and parent lineage are bound where the relevant phase requires them. Missing or conflicting evidence fails closed.

## Repository map

```text
src/llm_arbitrage_system/
├── domain/          immutable contracts
├── analytics/       adaptive market features
├── simulation/      strategy, approval, execution, orchestration
├── storage/         append-only SQLite replay journal
├── reporting/       evidence-bounded performance reports
└── experiments/     bundles, trust, OOS, campaigns, valuation and review

examples/            deterministic inputs and policies
tests/               positive, negative, tamper and recovery coverage
scripts/             offline smoke and delivery helpers
docs/                architecture, state, evidence and integration ledgers
```

## Documentation

- [Documentation index](docs/README.md)
- [Current integration status](docs/integration-status.md)
- [Architecture](docs/architecture.md)
- [State Machines](docs/state-machines.md)
- [Data flow](docs/data-flow.md)
- [Replay evidence](docs/replay-evidence.md)
- [Experiment contract](docs/phase3-experiments.md)
- [Trust and OOS registry](docs/phase4-trust-registry.md)
- [Campaigns, valuation, selection, and review](docs/phase5-campaigns.md)
- [Documentation language policy](docs/I18N.md)
- [Open-source readiness checklist](docs/OPEN_SOURCE_CHECKLIST.md)

## Safety and responsible use

- Paper execution is the only supported execution mode.
- No credential, account, wallet, deposit, withdrawal, or external order route belongs in this repository.
- Generated metrics must name their data, configuration, code, runtime, and evidence limitations.
- Backtest or OOS evidence must not be represented as realized or future profit.
- Legal, financial, operational, release, deployment, and trading decisions remain human-owned.

Report vulnerabilities privately through [SECURITY.md](SECURITY.md).

## Contributing and governance

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing code or evidence semantics. Public support boundaries are in [SUPPORT.md](SUPPORT.md), decision authority is in [GOVERNANCE.md](GOVERNANCE.md), and maintainers are listed in [MAINTAINERS.md](MAINTAINERS.md).

## License

Licensed under the [MIT License](LICENSE). This license does not grant rights to third-party data, market feeds, documents, trademarks, or services.
