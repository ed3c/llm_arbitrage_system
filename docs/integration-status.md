# Integration status

## Scope

This file is the status source of truth for the merged Phase 1–4 implementation and the current documentation/Git-governance work. It distinguishes code that exists on `main` from issues that are open or planned.

Implementation baseline:

```text
repository: ed3c/llm_arbitrage_system
main:       55ecf0e9a91006f563a080661cb6adf650e2439a
mode:       offline, deterministic, paper-only
```

## Evidence vocabulary

| State | Meaning |
| --- | --- |
| `MERGED` | The bytes are reachable from the stated `main` subject. |
| `OPEN` | An issue or PR exists but has not been merged. |
| `PLANNED` | Work is decomposed and tracked, but implementation is not available. |
| `BLOCKED` | A required precondition is missing or a policy forbids progress. |
| `PASS` | The named assertion was exercised against the named exact subject and passed. |
| `FAIL` | The named assertion was exercised and failed. |
| `ABSENT` | Required evidence or configuration does not exist. |
| `NOT_IMPLEMENTED` | The mechanism has not been built. |
| `NOT_EXERCISED` | The mechanism exists or is specified, but the named live lane was not run. |
| `SKIPPED_BY_POLICY` | Policy intentionally prevented the action; this is not success. |

Never collapse these states. In particular, documentation, configuration, tool presence, local synchronization, publication, CI, review, merge, release, and production are separate evidence lanes.

## Source architecture versus repository implementation

The supplied *Trading Systems and Methods 資源* describes, on pages 15–20, a modular system with configuration, ingestion/storage, multi-venue adapters, Kaufman/noise analytics, three arbitrage strategy paths, risk/portfolio control, smart execution, backtesting, and an `asyncio.Queue` orchestrator.

This repository implements the safe offline subset and adds evidence/trust control planes:

| Source concept | Repository implementation | State |
| --- | --- | --- |
| Market event contracts | `src/llm_arbitrage_system/domain/` | `MERGED` |
| Kaufman ER/KAMA, Z-score, ATR, Kalman filtering | `src/llm_arbitrage_system/analytics/` | `MERGED` |
| Funding, overcrowding, RWA lead-lag routes | `simulation/strategy_router.py` | `MERGED`, paper-only |
| Central risk and capacity control | `simulation/approval.py` | `MERGED`, paper-only |
| Concurrent multi-leg execution | `simulation/executor.py` | `MERGED`, deterministic simulation only |
| Queue-based orchestration | `simulation/pipeline.py` | `MERGED` |
| Durable replay evidence | `storage/sqlite_journal.py` | `MERGED` |
| Performance reporting | `reporting/performance.py` | `MERGED`, evidence-bounded |
| Reproducible experiments and walk-forward planning | `experiments/` Phase 3 modules | `MERGED` |
| Signed provenance, lineage, OOS registry | `experiments/` Phase 4 modules | `MERGED` |
| Hyperliquid, Alpaca, CEX, wallet or broker adapters | no implementation | `NOT_IMPLEMENTED` |
| Real account registration, deposits, withdrawals, or live orders | prohibited | `BLOCKED` by policy |

The PDF is a design source, not proof that every proposed external integration exists or is safe. The code tree and merged PR history determine implementation truth.

## Merged phase ledger

| Phase | PR | Merge subject | Implemented result |
| --- | --- | --- | --- |
| Phase 1 | [#1](https://github.com/ed3c/llm_arbitrage_system/pull/1) | `0e8ceec3456ad2c74fa77237d3b814520f0213fc` | Packaging, immutable domain contracts, validated analytics parameters, Kaufman/noise analytics. |
| Phase 2 | [#3](https://github.com/ed3c/llm_arbitrage_system/pull/3) | `1a255ad865ce346816bc04ef8680d80477c32cc7` | Planner/approver/executor boundaries, three paper strategies, bounded queues, deterministic fills, compensation, stateful approval. |
| Phase 2B | [#4](https://github.com/ed3c/llm_arbitrage_system/pull/4) | `215ca9c7c81bea456a4e358a9d750a7157a9872b` | Append-only SQLite evidence, fail-closed lifecycle, performance reports, CI gates. |
| Phase 3 | [#6](https://github.com/ed3c/llm_arbitrage_system/pull/6) | `e201e4b012e1596a7c470309cd2af792e009ee17` | Strict JSONL/YAML inputs, semantic identities, deterministic IDs, atomic bundles, verification, parameter grids, purged walk-forward plans. |
| Phase 4 | [#10](https://github.com/ed3c/llm_arbitrage_system/pull/10) | `55ecf0e9a91006f563a080661cb6adf650e2439a` | Ed25519 attestations, lineage DAG, matrix-bound test execution, trusted immutable registry, coverage aggregation. |

## Merged implementation inventory

### Domain and analytics

```text
src/llm_arbitrage_system/domain/contracts.py
src/llm_arbitrage_system/analytics/
├── engine.py
├── kalman.py
├── kaufman.py
├── volatility.py
└── zscore.py
```

State: `MERGED`.

Key contract:

```text
MarketEvent
  → FeatureSnapshot
  → TradePlan / StrategyDecision
  → RiskEvaluation / ApprovedTradePlan
  → ExecutionResult
```

### Paper runtime

```text
src/llm_arbitrage_system/simulation/
├── protocols.py
├── strategy_router.py
├── approval.py
├── executor.py
└── pipeline.py
```

State: `MERGED`.

The runtime has no venue SDK or network path. `DeterministicPaperExecutor` simulates fills and reverses confirmed fills after a partial multi-leg failure. `StatefulPaperApprover` reserves capacity before execution and reconciles terminal results.

### Evidence and reporting

```text
src/llm_arbitrage_system/storage/sqlite_journal.py
src/llm_arbitrage_system/reporting/performance.py
```

State: `MERGED`.

SQLite owns replay lifecycle and append-only causal evidence. Reports separate execution quality from realized profit. Unsupported claims remain unset.

### Experiment control plane

```text
src/llm_arbitrage_system/experiments/
├── canonical.py
├── dataset.py
├── config.py
├── determinism.py
├── manifest.py
├── runner.py
├── bundle.py
├── bundle_io.py
├── bundle_types.py
├── bundle_validation.py
├── bundle_verify.py
├── strict_yaml.py
├── sweep.py
├── walk_forward.py
└── cli.py
```

State: `MERGED`.

Phase 3 validates and canonicalizes source inputs, derives content identities, runs one deterministic replay, publishes a checksummed bundle atomically, independently verifies it, and plans bounded train/purge/test matrices.

### Trust and OOS registry control plane

```text
src/llm_arbitrage_system/experiments/
├── signing.py
├── lineage.py
├── evaluation.py
├── registry.py
└── aggregation.py
```

State: `MERGED`.

Phase 4 creates detached provenance attestations, content-addressed lineage nodes, test-slice-only evaluation bundles, immutable registry imports, and cross-window coverage summaries. It does not authenticate the original market source or choose a profitable candidate.

## Current documentation stack

Epic: [#11](https://github.com/ed3c/llm_arbitrage_system/issues/11).

```text
main
└── docs/phase4-integration-ssot        issue #12  OPEN
    └── docs/git-town-governance        issue #13  OPEN
        └── docs/readme-state-flow-index issue #14  OPEN
```

| Issue | Owner paths | Purpose | State |
| --- | --- | --- | --- |
| [#12](https://github.com/ed3c/llm_arbitrage_system/issues/12) | `AGENTS.md`, integration/state/data-flow docs | Agent routing and implementation SSOT | `OPEN` |
| [#13](https://github.com/ed3c/llm_arbitrage_system/issues/13) | `.git-town.toml`, `docs/git/**`, `docs/harness/**`, issue/PR templates | Repository-owned Git Town governance | `OPEN` |
| [#14](https://github.com/ed3c/llm_arbitrage_system/issues/14) | `README.md`, final stack index | Directory/State Machine/data-flow convergence | `OPEN` |

These branches and PR bases form a Git Town-compatible serial stack, but no local Git Town synchronization receipt is claimed by this documentation work.

## Planned molecular Git Town leaves

| Issue | Planned branch | Dependency | Mechanism | State |
| --- | --- | --- | --- | --- |
| [#15](https://github.com/ed3c/llm_arbitrage_system/issues/15) | `infra/git-town-admission` | governance docs | exact Git Town host admission receipt | `PLANNED`, blocked on host/legal owners |
| [#16](https://github.com/ed3c/llm_arbitrage_system/issues/16) | `tooling/git-town-task-packet-validator` | #15 | typed task-packet/path-lease validator | `PLANNED` |
| [#17](https://github.com/ed3c/llm_arbitrage_system/issues/17) | `tooling/git-town-worktree-doctor` | #16 | linked-worktree and lease doctor | `PLANNED` |
| [#18](https://github.com/ed3c/llm_arbitrage_system/issues/18) | `tooling/git-town-bounded-sync` | #15–#17 | dry-run + bounded no-push synchronization and receipts | `PLANNED` |
| [#19](https://github.com/ed3c/llm_arbitrage_system/issues/19) | `test/git-town-fail-closed-canaries` | #18 | conflict/prompt/timeout/cleanup/rollback controls | `PLANNED` |
| [#20](https://github.com/ed3c/llm_arbitrage_system/issues/20) | `tooling/git-town-publication-gate` | #18–#19 | GitHub publication gate and remote ancestry verification | `PLANNED` |
| [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21) | `convergence/git-town-adoption-audit` | #15–#20 | live adoption audit and convergence report | `PLANNED` |

No file under `scripts/git-town/`, no Git Town receipt store, and no publication gate exists at this baseline. Those mechanisms remain `NOT_IMPLEMENTED` until their owning issues merge.

## Requirement matrix

| Requirement | Current state | Evidence / owner |
| --- | --- | --- |
| Agent mandatory read order | `OPEN` | issue #12 |
| Directory-to-State Machine ownership | `OPEN` | issue #12, converged by #14 |
| Runtime/evidence/trust data-flow documentation | `OPEN` | issue #12, converged by #14 |
| Shared Skill referenced without local shadow copy | `OPEN` | issue #13 |
| Repository Git Town profile and config | `OPEN` | issue #13 |
| Exact Git Town version pin | `OPEN` | issue #13 |
| Host executable digest/provenance/SBOM/notices/legal receipt | `NOT_EXERCISED` | issue #15 |
| Eval-first task-packet validator | `NOT_IMPLEMENTED` | issue #16 |
| Linked-worktree and path-lease doctor | `NOT_IMPLEMENTED` | issue #17 |
| Bounded no-push synchronization wrapper | `NOT_IMPLEMENTED` | issue #18 |
| Conflict/timeout/rollback canaries | `NOT_IMPLEMENTED` | issue #19 |
| GitHub publication gate | `NOT_IMPLEMENTED` | issue #20 |
| Live Git Town adoption audit | `NOT_EXERCISED` | issue #21 |
| Live exchange/broker execution | `BLOCKED` | repository safety policy |

## Verification baseline

The merged repository has fixed commands:

```bash
make check
make phase3-smoke
make phase4-smoke
```

The Phase 4 merge commit added the Phase 4 smoke to CI. A future documentation PR must use current exact-head workflow evidence rather than reusing the merge commit's result.

The commands above verify repository behavior. They do not prove:

```text
Git Town executable admission
linked-worktree isolation
branch/path lease exclusivity
live Git Town synchronization
publication authorization
remote ancestry after a new push
Human Admit
release or production state
```

## Safety and non-claims

The following are not part of the repository's current implementation:

```text
Hyperliquid / Alpaca / CEX adapters
wallet or exchange private keys
broker or exchange account access
deposit or withdrawal workflows
external order endpoints
live market WebSockets
production execution
profit guarantees
risk-free arbitrage claims
```

Checksums prove byte integrity. Ed25519 attestations prove that a holder of one provenance key signed a captured identity. Registry trust proves a local allowlist decision. None of these prove source-market truth, legal identity, realized profitability, future performance, or immunity from market/model risk.
