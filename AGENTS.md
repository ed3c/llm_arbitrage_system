# Agent instructions

## Current phase

Phase 3 adds reproducible, content-addressed experiment orchestration on top of the merged offline paper runtime. Preserve the paper-only boundary and treat datasets, configuration, manifests, SQLite evidence, and checksums as one linked evidence chain.

## Commands

```bash
python -m pip install -e ".[dev]"
make check
make phase3-smoke
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
- `experiments/dataset.py`: strict schema-v1 JSONL validation and semantic dataset hashes.
- `experiments/config.py`: strict schema-v1 behavior configuration and canonical hashes.
- `experiments/determinism.py`: evidence-derived plan and leg identifiers.
- `experiments/manifest.py`: experiment identity and code-revision provenance.
- `experiments/runner.py`: composition root for one reproducible paper experiment.
- `experiments/bundle.py`: atomic bundle publication and independent verification.
- `experiments/walk_forward.py`: bounded parameter grids and train/purge/test plans.
- `experiments/cli.py`: credential-free operator interface.

## Required invariants

- Use timezone-aware timestamps and `Decimal` for prices, amounts, fees, and limits.
- Keep domain contracts immutable.
- Reject unknown fields, duplicate JSON/YAML keys, naive timestamps, non-finite values, time reversal, and floating-point monetary inputs.
- Canonical identity is based on semantic dataset content, canonical behavior configuration, code revision, and package version.
- Raw source hashes remain evidence, but whitespace and mapping order do not change semantic identity.
- Operational SQLite timestamps are not part of the experiment identity.
- Deterministic plan and leg identifiers must derive from input evidence, feature sequence, and plan semantics—not UUID defaults.
- A pipeline instance is single-use.
- A run is `completed` only after all queue stages finish and reports persist.
- A stage failure cancels sibling tasks and marks the journal `aborted`.
- Persist market events before queue admission, decisions before approval, risk outcomes before execution admission, and execution results before reconciliation.
- Do not silently overwrite an existing content-addressed bundle.
- Bundle verification must check the exact file set, SHA-256 values, manifest identity, raw/canonical linkage, event metadata, SQLite integrity, `run_id`, and terminal status.
- Walk-forward windows must maintain explicit train, purge, and test boundaries. Never train on or select from the test slice.
- Parameter grids must be deterministic and bounded before expansion.
- Execution cost is not strategy PnL. Do not populate Sharpe, drawdown, or alpha-decay fields without the evidence required by the reporting contract.
- Add deterministic tests for every schema, lifecycle, identity, checksum, metric, or state-transition change.

## Prohibited changes

Do not add private keys, API secrets, seed phrases, withdrawal functions, account access, venue SDKs, external order endpoints, network probes, or a live-mode branch. Do not weaken validation, CI, evidence boundaries, overwrite protection, or bundle verification. Do not claim that content addressing proves authenticity or profitability.

## Phase sequence

```text
Phase 1 contracts/analytics
  -> Phase 2 paper runtime
  -> Phase 2B durable evidence/reporting
  -> Phase 3 reproducible experiments
```
