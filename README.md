# LLM Arbitrage System

A credential-free, paper-only research harness derived from the supplied *Trading Systems and Methods 資源* architecture. The repository studies three deterministic scenarios—funding carry, overcrowding reversion, and RWA lead-lag—without connecting to accounts, wallets, brokers, exchanges, or withdrawal endpoints.

## Runtime state machine

```text
MarketEvent
  -> AnalyticsEngine
  -> PaperStrategyRouter
  -> StatefulPaperApprover
  -> DeterministicPaperExecutor
  -> SQLiteReplayJournal
  -> ResearchPerformanceReport
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
| Reporting | Execution-quality, fees, turnover, edge-after-cost, optional drawdown/Sharpe, and explicit unsupported-metric notes |
| CI | Ruff, strict Mypy, coverage gate, and Python 3.10–3.13 compatibility matrix |

## Evidence boundaries

Execution cost and net settlement cash flow are replay evidence, not realized strategy profit. Drawdown and Sharpe are only produced when a caller supplies an explicit realized PnL series and initial equity. Alpha decay remains unset because one replay cannot support that claim.

## Install and verify

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
make check
```

## Stacked change index

```text
main
  -> PR #1  Phase 1: contracts and adaptive analytics
       -> PR #3  Phase 2: offline strategy, approval, and simulation core
            -> feat/replay-evidence-phase2b  durable evidence, reports, and CI
```

Merge order is oldest parent first. The Phase 2B branch must not be retargeted to `main` until its parents have merged and its CI evidence has been rerun against the new base.

## Non-goals

This repository does not contain private keys, API secrets, account registration automation, withdrawal functions, external order endpoints, venue SDKs, or a live-mode branch. It does not promise arbitrage profitability or risk-free returns.
