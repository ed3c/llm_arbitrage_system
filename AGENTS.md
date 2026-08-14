# Agent instructions

## Current phase

Phase 2B adds durable replay evidence, execution-quality reporting, and repository CI on top of the offline paper runtime. Preserve the stacked dependency chain and keep every component credential-free.

## Commands

```bash
python -m pip install -e ".[dev]"
make check
```

## State-machine ownership

- `domain/`: immutable cross-layer contracts; no I/O.
- `analytics/`: deterministic feature state keyed by venue and symbol.
- `simulation/strategy_router.py`: creates paper plans only.
- `simulation/approval.py`: reserves capacity and reconciles terminal results.
- `simulation/executor.py`: deterministic fills and compensation; no network path.
- `simulation/pipeline.py`: bounded queues, lifecycle, cancellation, and stage ordering.
- `storage/sqlite_journal.py`: append-only local evidence and replay-run status.
- `reporting/performance.py`: evidence-supported metrics and explicit withheld claims.

## Required invariants

- Use timezone-aware timestamps and `Decimal` for prices, amounts, fees, and limits.
- Keep domain contracts immutable.
- A pipeline instance is single-use.
- A run is `completed` only after all queue stages finish and its report is persisted.
- A stage failure cancels sibling tasks and marks the journal `aborted`.
- Persist market events before queue admission, decisions before approval, risk outcomes before execution admission, and execution results before reconciliation.
- Deterministic simulation identifiers must derive from the plan and leg index, not random UUIDs.
- Execution cost is not strategy PnL. Do not populate Sharpe, drawdown, or alpha-decay fields without the evidence required by the reporting contract.
- Add deterministic tests for every schema, lifecycle, metric, or state-transition change.

## Prohibited changes

Do not add private keys, API secrets, seed phrases, withdrawal functions, account access, venue SDKs, external order endpoints, or a live-mode branch. Do not weaken CI or silently convert missing evidence into a positive metric.

## Stacked PR sequence

```text
PR #1 -> PR #3 -> feat/replay-evidence-phase2b
```

Merge and retarget in that order. Record CI evidence again after each base change.
