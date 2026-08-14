# Implementation status

## Phase 1 — merged

- immutable typed domain contracts
- validated analytics configuration
- Kaufman ER/KAMA, rolling Z-score, ATR percentage, and Kalman filtering
- packaging, contribution, security, and architecture documentation

## Phase 2 and Phase 2B — merged

- paper-only funding carry, crowding reversion, and RWA lead-lag routing
- stateful approval, capacity reservation, and terminal reconciliation
- deterministic multi-leg simulation and partial-outcome compensation
- bounded asyncio orchestration
- append-only SQLite replay evidence
- execution-quality reporting with explicit evidence limits
- Ruff, strict Mypy, coverage, and Python 3.10–3.13 CI gates

## Phase 3 — current change

- strict schema-v1 MarketEvent JSONL datasets
- strict schema-v1 YAML experiment and sweep configuration
- canonical serialization and semantic SHA-256 identities
- deterministic plan, leg, candidate, and evaluation identifiers
- CLI validation, execution, verification, and matrix-planning commands
- content-addressed evidence bundles with source/canonical inputs
- manifest, SQLite evidence, JSON reports, Markdown report, and checksums
- independent raw/canonical, manifest, checksum, run-state, and SQLite verification
- bounded parameter grids and purged walk-forward plans
- deterministic tests and CI CLI smoke coverage

## Release gate

The project remains offline and paper-only. No real venue integration is in scope. A future adapter would require independent review for secrets, authorization, idempotency, reconciliation, stale-data rejection, unmatched-leg handling, regulatory constraints, and an explicit opt-in execution boundary.
