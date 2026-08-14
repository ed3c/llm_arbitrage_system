# Implementation status

## Phase 1 — merged

- immutable typed contracts
- validated analytics configuration
- Kaufman ER/KAMA, Z-score, ATR percentage, and Kalman filtering

## Phase 2 and Phase 2B — merged

- three paper-only strategy routes
- stateful approval and capacity reservation
- deterministic multi-leg simulation and compensation
- bounded asyncio orchestration
- append-only SQLite evidence and execution-quality reports
- Ruff, strict Mypy, coverage, and Python 3.10–3.13 CI

## Phase 3 — merged

- strict JSONL/YAML experiment inputs
- canonical serialization and semantic identities
- deterministic plan/candidate/evaluation IDs
- content-addressed evidence bundles and verification
- bounded parameter grids and purged walk-forward plans

## Phase 4 — current change

- Ed25519 provenance key generation with private files outside evidence
- detached bundle attestations and trusted-key verification
- content-addressed dataset lineage manifests and parent DAGs
- one planned test-slice evaluation runner
- checksummed evaluation binding records
- local SQLite trusted experiment registry
- immutable experiment and evaluation imports
- complete/partial/missing cross-window coverage aggregation
- CLI, examples, tests, documentation, and Phase 4 CI smoke

## Release gate

The project remains offline and paper-only. No real venue integration is in scope. Any future adapter requires independent review for secrets, authorization, idempotency, reconciliation, stale-data rejection, unmatched-leg handling, regulatory constraints, and an explicit opt-in boundary.
