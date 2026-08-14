# Integration status

## Scope

This file is the status source of truth for the merged Phase 1–8 implementation, the documentation/Git-governance layer, and the Git Town delivery mechanisms. It distinguishes code that exists on `main` from issues that are open, planned or blocked.

Implementation baseline:

```text
repository: ed3c/llm_arbitrage_system
main:       2bcbeae05a9ea43497060d4cb61ad0a437c1bdb5
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
| CI prerequisite | [#26](https://github.com/ed3c/llm_arbitrage_system/pull/26) | `989ee49533bfaef1bbbb1b1462dc58cf71897e6f` | Canonical-config round trip accepts scientific-notation floats; strict Mypy baseline restored. Repaired a `main` that had been red. |
| Documentation SSOT | [#22](https://github.com/ed3c/llm_arbitrage_system/pull/22), [#23](https://github.com/ed3c/llm_arbitrage_system/pull/23), [#24](https://github.com/ed3c/llm_arbitrage_system/pull/24) | `8a2b955`, `60bb437`, `b0e1e86` | Agent read order, integration/state/data-flow SSOT, Git Town governance and profile, README index. |
| Phase 5 | [#31](https://github.com/ed3c/llm_arbitrage_system/pull/31), [#32](https://github.com/ed3c/llm_arbitrage_system/pull/32), [#33](https://github.com/ed3c/llm_arbitrage_system/pull/33) | `53b9a8b`, `96d387e`, `f8fe5f8` | Strict campaign contracts, durable SQLite state journal with interruption recovery, bounded runner, signed evaluations, trusted registration, campaign CLI and smoke. |
| Phase 6 | [#39](https://github.com/ed3c/llm_arbitrage_system/pull/39), [#40](https://github.com/ed3c/llm_arbitrage_system/pull/40), [#41](https://github.com/ed3c/llm_arbitrage_system/pull/41) | `3af5bb5`, `3d96416`, `00b2fd1` | Strict terminal marks, deterministic bundle valuation, chronological trusted OOS statistics, valuation CLI and signed reports. |
| Phase 7 | [#50](https://github.com/ed3c/llm_arbitrage_system/pull/50), [#52](https://github.com/ed3c/llm_arbitrage_system/pull/52), [#53](https://github.com/ed3c/llm_arbitrage_system/pull/53) | `ae45c60`, `31e6fc4`, `b54013b` | Preregistered selection policy, candidate stability and Holm family diagnostics, signed human-review dossier. Selection stays human-owned. |
| Phase 8 | [#59](https://github.com/ed3c/llm_arbitrage_system/pull/59), [#60](https://github.com/ed3c/llm_arbitrage_system/pull/60), [#61](https://github.com/ed3c/llm_arbitrage_system/pull/61) | `8bb7459`, `d8a5a01`, `008fb92` | Strict research-review request contracts, signed independent reviewer evidence, non-deployable quorum envelope. Deployment and trading flags stay false. |
| Git Town mechanisms | [#62](https://github.com/ed3c/llm_arbitrage_system/pull/62)–[#66](https://github.com/ed3c/llm_arbitrage_system/pull/66) | `955aa12`, `d38428c`, `f230887`, `dab0908`, `2bcbeae` | Task-packet validator, worktree/lease doctor, bounded no-push sync and receipts, fail-closed canaries, publication gate and remote verifier. |

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

### Campaign, valuation, selection and review control plane

```text
src/llm_arbitrage_system/experiments/
├── campaign.py                 Phase 5  strict campaign contracts
├── campaign_store.py           Phase 5  durable state journal
├── campaign_runner.py          Phase 5  bounded execution and registration
├── valuation.py                Phase 6  terminal marks, bundle valuation
├── oos_statistics.py           Phase 6  chronological trusted OOS statistics
├── selection_policy.py         Phase 7  preregistered policy contracts
├── selection_diagnostics.py    Phase 7  stability and Holm family diagnostics
├── selection_dossier.py        Phase 7  signed human-review dossier
├── selection_signing.py        Phase 7  dossier attestations
├── decision_request.py         Phase 8  strict research-review requests
├── review_evidence.py          Phase 8  signed independent reviewer records
├── review_quorum.py            Phase 8  non-deployable quorum envelope
└── operator_cli.py             Phase 7–8 fixed operator commands
```

State: `MERGED`.

Each phase adds evidence, never authority. Phase 6 marks positions without claiming the mark is a realizable price. Phase 7 diagnoses stability and multiple-testing risk without selecting a candidate. Phase 8 records a human decision and keeps deployment, trading and release flags false.

### Git Town delivery mechanisms

```text
scripts/git-town/
├── task_packet.py              #16  typed packet and path-lease validator
├── doctor.sh, lease.py         #17  linked-worktree admission and lease store
├── sync.sh, receipt.py         #18  bounded no-push sync, verification, receipts
├── publish.sh                  #20  publication gate driver
├── github_snapshot.py          #20  trusted snapshot schema and gate decision
└── remote_verify.py            #20  post-push head and ancestry verification

fixtures/git-town/canary_tool.sh  #19  deterministic condition generator
tests/git-town/                   #16–#20  mechanism selftests and controls
```

State: `MERGED` as mechanisms; `NOT_EXERCISED` as live lanes.

Every entrypoint carries `--selftest`, and the `Git Town delivery mechanisms` CI job runs all of them plus `tests/git-town` on every push. Git Town `v24.0.0` is admitted for `darwin_arm64` by receipt `eda73fcc` (#15). Admission makes a live run possible; it does not make one observed. `live_canary` stays `NOT_EXERCISED` until issue #21 runs it, and a host without its own receipt still returns `BLOCKED_TOOL_ADMISSION`.

## Documentation stack (merged)

Epic: [#11](https://github.com/ed3c/llm_arbitrage_system/issues/11).

| Issue / PR | Owner paths | Purpose | State |
| --- | --- | --- | --- |
| [#12](https://github.com/ed3c/llm_arbitrage_system/issues/12) / [#22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `AGENTS.md`, integration/state/data-flow docs | Agent routing and implementation SSOT | `MERGED` |
| [#13](https://github.com/ed3c/llm_arbitrage_system/issues/13) / [#23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `.git-town.toml`, `docs/git/**`, `docs/harness/**`, issue/PR templates | Repository-owned Git Town governance | `MERGED` |
| [#14](https://github.com/ed3c/llm_arbitrage_system/issues/14) / [#24](https://github.com/ed3c/llm_arbitrage_system/pull/24) | `README.md`, stack index | Directory/State Machine/data-flow convergence | `MERGED` |

These branches and PR bases formed a Git Town-compatible serial stack, but no local Git Town synchronization receipt was produced: every merge was performed through GitHub under explicit human authorization.

## Git Town molecular leaves

| Issue | Branch | Mechanism | State |
| --- | --- | --- | --- |
| [#15](https://github.com/ed3c/llm_arbitrage_system/issues/15) | `infra/git-town-admitted` | exact Git Town host admission receipt | `PASS` for `darwin_arm64`, receipt `eda73fcc` |
| [#16](https://github.com/ed3c/llm_arbitrage_system/issues/16) | `tooling/git-town-task-packet-validator` | typed task-packet/path-lease validator | `MERGED` |
| [#17](https://github.com/ed3c/llm_arbitrage_system/issues/17) | `tooling/git-town-worktree-doctor` | linked-worktree and lease doctor | `MERGED` |
| [#18](https://github.com/ed3c/llm_arbitrage_system/issues/18) | `tooling/git-town-bounded-sync` | dry-run + bounded no-push synchronization and receipts | `MERGED` |
| [#19](https://github.com/ed3c/llm_arbitrage_system/issues/19) | `test/git-town-fail-closed-canaries` | conflict/prompt/timeout/cleanup/rollback controls | `MERGED` |
| [#20](https://github.com/ed3c/llm_arbitrage_system/issues/20) | `tooling/git-town-publication-gate` | GitHub publication gate and remote ancestry verification | `MERGED` |
| [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21) | `convergence/git-town-adoption-audit` | live adoption audit and convergence report | `PLANNED`, depends on #15 and a live run |

`#16` declared `infra/git-town-admission` as its parent. That branch was never created, because `#15` is blocked on human decisions. The tooling stack parented onto the documentation stack instead and asserts no `#15` lane.

## Requirement matrix

| Requirement | Current state | Evidence / owner |
| --- | --- | --- |
| Agent mandatory read order | `MERGED` | `AGENTS.md` |
| Directory-to-State Machine ownership | `MERGED` | `README.md`, `docs/state-machines.md` |
| Runtime/evidence/trust data-flow documentation | `MERGED` | `docs/data-flow.md` |
| Shared Skill referenced without local shadow copy | `MERGED` | `docs/git/README.md`, `AGENTS.md` |
| Repository Git Town profile and config | `MERGED` | `.git-town.toml`, `docs/git/REPO_PROFILE.md` |
| Exact Git Town version pin | `MERGED` | `docs/git/GIT_TOWN_ADMISSION.md` |
| Host executable digest/provenance/SBOM/notices/legal receipt | `NOT_EXERCISED` | issue #15 |
| Eval-first task-packet validator | `MERGED` | `scripts/git-town/task_packet.py` |
| Linked-worktree and path-lease doctor | `MERGED` | `scripts/git-town/doctor.sh`, `lease.py` |
| Bounded no-push synchronization wrapper | `MERGED` | `scripts/git-town/sync.sh`, `receipt.py` |
| Conflict/timeout/rollback canaries | `MERGED` | `tests/git-town/test_fail_closed_canaries.py` |
| GitHub publication gate | `MERGED` | `scripts/git-town/publish.sh`, `github_snapshot.py` |
| Live Git Town synchronization | `NOT_EXERCISED` | issues #15 and #21 |
| Live Git Town adoption audit | `NOT_EXERCISED` | issue #21 |
| Live exchange/broker execution | `BLOCKED` | repository safety policy |

A `MERGED` mechanism row means the mechanism and its disagreement-producing controls exist and pass in CI. It does not promote any live lane: `NOT_EXERCISED` rows stay `NOT_EXERCISED`.

## Verification baseline

The merged repository has fixed commands:

```bash
make check
make phase3-smoke
make phase4-smoke
make phase5-smoke
make phase6-smoke
make phase7-smoke
make phase8-smoke
pytest tests/git-town
```

CI runs three jobs: `Quality gates (Python 3.13)` (ruff, strict mypy, pytest with the coverage floor, and the phase 3–8 smokes), `Python 3.10/3.11/3.12` compatibility, and `Git Town delivery mechanisms` (every `--selftest` plus `tests/git-town`).

Evidence must come from the exact head under review. Reusing an older commit's green result is the failure mode `scripts/git-town/github_snapshot.py` refuses as `BLOCKED_STALE_EVIDENCE`.

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
