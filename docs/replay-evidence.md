# Replay evidence, reporting, and CI contract

## Purpose

Phase 2B makes an offline replay auditable. It does not expand the runtime into live trading. The phase persists the state transitions already produced by the paper pipeline and computes only metrics supported by those stored artifacts.

## Data flow

```text
Iterable[MarketEvent]
  |
  | record_market_event
  v
bounded data_queue
  |
  v
AnalyticsEngine -> FeatureSnapshot
  |
  v
Planner -> StrategyDecision
  |         |
  |         +-- record_decision
  v
Approver -> RiskEvaluation
  |         |
  |         +-- record_risk_evaluation
  v
bounded approved_queue
  |
  v
PaperExecutor -> ExecutionResult
  |               |
  |               +-- record_execution_result
  v
ResultReconciler
  |
  v
ReplayReport + ResearchPerformanceReport
  |
  +-- complete_run
```

A failure at any queue stage cancels sibling tasks. The journal transitions from `running` to `aborted`; a successful run transitions to `completed` only after replay and performance reports have been written.

## SQLite ownership

`SQLiteReplayJournal` owns five tables:

| Table | Responsibility |
| --- | --- |
| `replay_runs` | Lifecycle status, terminal error, replay report, performance report |
| `market_events` | Ordered input evidence per run |
| `strategy_decisions` | Plan-producing decisions keyed by `plan_id` |
| `risk_evaluations` | Accepted or rejected approval evidence |
| `execution_results` | Approved plan plus deterministic terminal result |

The store enables foreign keys, WAL journaling, and `synchronous=FULL`. Payloads use stable JSON ordering, exact decimal strings, enum wire values, and ISO-8601 timestamps. `PRAGMA integrity_check` is exposed as a verification gate.

## Metric contract

The report provides:

- approved and terminal-plan counts by status
- fill count and gross turnover
- fees and signed settlement cash flow
- expected edge before costs
- average and maximum execution cost in basis points
- expected edge after execution costs
- optional maximum drawdown and annualized Sharpe ratio

Drawdown and Sharpe require an explicit realized PnL sequence plus initial equity. Alpha decay requires repeated out-of-sample windows and remains `None` for a single replay. Net settlement cash flow is not labeled as realized profit.

## CI gates

The workflow uses read-only repository permissions and pinned action commits. It runs:

1. Ruff, strict Mypy, tests, and a coverage floor on Python 3.13.
2. Compatibility tests on Python 3.10, 3.11, and 3.12.
3. No credentials, network probes, exchange SDKs, or live endpoints.

## Merge topology

```text
main
  -> PR #1
       -> PR #3
            -> feat/replay-evidence-phase2b
```

After a parent merges, retarget the child, rerun all gates, and only then review the child for merge.
