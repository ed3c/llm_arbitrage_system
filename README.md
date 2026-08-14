# LLM Arbitrage System

A credential-free, deterministic, paper-only research harness derived from the supplied *Trading Systems and Methods 資源* architecture.

The merged data plane studies three offline scenarios—funding carry, overcrowding reversion, and RWA lead-lag—through Kaufman/noise analytics, central approval, compensated paper execution, durable evidence, reproducible experiments, signed provenance, dataset lineage, and a trusted local OOS registry.

It does **not** connect to exchanges, brokers, wallets, accounts, deposits, withdrawals, market WebSockets, or live order endpoints.

## Status vocabulary

```text
MERGED            bytes are reachable from the stated main subject
OPEN_DRAFT        issue/PR exists and is intentionally Draft
OPEN_READY        admitted for review; not merge authority
PLANNED           decomposed work with no available implementation
BLOCKED           policy or a missing precondition prevents progress

PASS
FAIL
ABSENT
NOT_IMPLEMENTED
NOT_EXERCISED
SKIPPED_BY_POLICY
```

Documentation, static config, tool presence, local sync, publication, CI, review, merge, release, production, market truth, and profitability are separate evidence lanes.

## Agent entrypoint

Read in this order before editing:

1. [`AGENTS.md`](AGENTS.md);
2. this `README.md`;
3. [`docs/integration-status.md`](docs/integration-status.md);
4. [`docs/state-machines.md`](docs/state-machines.md) and [`docs/data-flow.md`](docs/data-flow.md);
5. the owning domain documents:
   - [`docs/architecture.md`](docs/architecture.md);
   - [`docs/replay-evidence.md`](docs/replay-evidence.md);
   - [`docs/phase3-experiments.md`](docs/phase3-experiments.md);
   - [`docs/phase4-trust-registry.md`](docs/phase4-trust-registry.md);
   - [`docs/phase5-campaigns.md`](docs/phase5-campaigns.md);
   - [`docs/phase6-valuation.md`](docs/phase6-valuation.md);
   - [`docs/phase7-selection-governance.md`](docs/phase7-selection-governance.md);
   - [`docs/phase8-separation-of-duties.md`](docs/phase8-separation-of-duties.md);
6. for Git/Stack PR work:
   - [`docs/git/README.md`](docs/git/README.md);
   - [`docs/git/REPO_PROFILE.md`](docs/git/REPO_PROFILE.md);
   - [`docs/git/GIT_TOWN_ADMISSION.md`](docs/git/GIT_TOWN_ADMISSION.md);
   - [`docs/git/STACKED_PRS.md`](docs/git/STACKED_PRS.md);
   - [`docs/git/WORKER_PROTOCOL.md`](docs/git/WORKER_PROTOCOL.md);
   - [`docs/git/TASK_PACKET.md`](docs/git/TASK_PACKET.md);
   - [`docs/git/EVALS.md`](docs/git/EVALS.md);
   - [`docs/git/PUBLICATION.md`](docs/git/PUBLICATION.md);
   - [`docs/git/ADOPTION_AUDIT.md`](docs/git/ADOPTION_AUDIT.md);
   - [`docs/harness/README.md`](docs/harness/README.md) and the per-mechanism
     contracts beside it ([task packet](docs/harness/git-town-task-packet.md),
     [doctor](docs/harness/git-town-doctor.md),
     [sync](docs/harness/git-town-sync.md),
     [canaries](docs/harness/git-town-canaries.md),
     [publication](docs/harness/git-town-publication.md));
7. the canonical issue/task packet, nearest directory `README.md`, current branch/PR graph, exact heads, and current workflow evidence.

Authority precedence:

```text
repository policy and merged code
  > canonical issue/task packet
  > canonical shared Skill
  > tool defaults
  > conversational summaries
```

## Current integration state

Implementation baseline:

```text
main@2bcbeae05a9ea43497060d4cb61ad0a437c1bdb5
```

| Layer | Implementation | State |
| --- | --- | --- |
| Domain | immutable typed contracts, timezone-aware timestamps, exact `Decimal` values | `MERGED` |
| Analytics | Kaufman ER/KAMA, rolling Z-score, ATR percentage, Kalman filter | `MERGED` |
| Strategy | paper-only funding, crowding, and RWA lead-lag routing | `MERGED` |
| Approval | freshness, edge, notional, exposure, duplicate, balance, slippage gates | `MERGED` |
| Simulation | deterministic concurrent fills, failure injection, partial-outcome reversal | `MERGED` |
| Replay evidence | append-only SQLite lifecycle/events/decisions/risk/results/reports | `MERGED` |
| Reporting | execution quality and evidence-bounded optional risk metrics | `MERGED` |
| Phase 3 experiments | strict inputs, semantic IDs, atomic bundles, verification, sweeps, walk-forward plans | `MERGED` |
| Phase 4 trust/OOS | Ed25519 attestations, lineage DAG, test-only evaluation, trusted registry, coverage aggregation | `MERGED` |
| Phase 5 campaigns | strict campaign contracts, durable state journal with interruption recovery, bounded runner, trusted registration | `MERGED` |
| Phase 6 valuation | strict terminal marks, deterministic bundle valuation, chronological trusted OOS statistics, signed reports | `MERGED` |
| Phase 7 selection governance | preregistered policy, stability and Holm family diagnostics, signed human-review dossier | `MERGED` |
| Phase 8 separation of duties | strict review requests, signed independent reviewer evidence, non-deployable quorum envelope | `MERGED` |
| Agent/integration SSOT | issue #12 / [PR #22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `MERGED` |
| Git Town governance/profile | issue #13 / [PR #23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `MERGED` |
| README convergence/index | issue #14 / [PR #24](https://github.com/ed3c/llm_arbitrage_system/pull/24) | `MERGED` |
| Git Town delivery mechanisms | issues #16–#20 / PRs [#62](https://github.com/ed3c/llm_arbitrage_system/pull/62)–[#66](https://github.com/ed3c/llm_arbitrage_system/pull/66) | `MERGED` as mechanisms, `NOT_EXERCISED` as live lanes |
| Git Town host admission | issue #15 | `PASS` for `darwin_arm64`, receipt `eda73fcc` |
| Live Git Town adoption audit | issue #21 | sync lane `PASS`, publication lanes `NOT_EXERCISED` — `docs/git/ADOPTION_AUDIT.md` |
| Live exchange/broker execution | prohibited | `BLOCKED` |

Phase 5 through 8 each add evidence, never authority. Phase 6 marks positions without claiming the mark is realizable, Phase 7 diagnoses without selecting, and Phase 8 records a human decision while keeping deployment, trading and release flags false.

See [`docs/integration-status.md`](docs/integration-status.md) for the exact merged/open/planned ledger and non-claims.

## Source architecture mapping

The supplied PDF's pages 15–20 describe:

```text
configuration
  → ingestion/storage
  → Kaufman/noise analytics
  → funding / overcrowding / RWA lead-lag routing
  → risk and portfolio control
  → smart multi-venue execution
  → asyncio.Queue orchestration
```

Repository mapping:

| Source concept | Actual repository owner | Boundary |
| --- | --- | --- |
| configuration | `src/llm_arbitrage_system/config/`, `experiments/config.py`, examples | behavior config; no secrets |
| core contracts | `domain/` | immutable values; no I/O |
| ingestion | `experiments/dataset.py` | strict offline JSONL; not WebSocket |
| analytics | `analytics/` | merged Kaufman/noise features |
| strategies | `simulation/strategy_router.py` | paper plan generation |
| risk/portfolio | `simulation/approval.py` | simulated capacity/reservation/reconciliation |
| execution | `simulation/executor.py` | deterministic paper fills only |
| event loop | `simulation/pipeline.py` | bounded queue orchestration |
| storage | `storage/sqlite_journal.py` | durable local replay evidence |
| backtest/reporting | `experiments/`, `reporting/` | reproducible replay/evidence |
| exchange/broker/wallet adapters | no implementation | `NOT_IMPLEMENTED` |

The PDF is a design basis. The code tree and merged PR history determine implementation truth.

## Repository directory structure

Markers: `[M]` merged, `[P]` planned path not yet implemented.

```text
llm_arbitrage_system/
├── AGENTS.md                                      [M] Agent routing and invariants
├── README.md                                      [M] convergence and traceability index
├── .git-town.toml                                 [M] conservative static Git Town policy
├── Makefile                                       [M] quality and smoke entrypoints
├── pyproject.toml                                 [M] package, CLI and dependencies
├── SECURITY.md                                    [M] paper-only and secret boundary
├── config/README.md                               [M] configuration guidance
├── docs/
│   ├── integration-status.md                      [M] merged/open/planned SSOT
│   ├── state-machines.md                          [M] transition ownership
│   ├── data-flow.md                               [M] end-to-end movement/evidence
│   ├── architecture.md                            [M] runtime/experiment architecture
│   ├── replay-evidence.md                         [M] SQLite/report contract
│   ├── phase3-experiments.md                      [M] reproducible experiment contract
│   ├── phase4-trust-registry.md                   [M] provenance/lineage/OOS registry
│   ├── phase5-campaigns.md                        [M] resumable trusted campaigns
│   ├── phase6-valuation.md                        [M] mark-to-market and OOS statistics
│   ├── phase7-selection-governance.md             [M] preregistered selection governance
│   ├── phase8-separation-of-duties.md             [M] research-review separation of duties
│   ├── git/                                       [M] repository Git Town projection
│   │   ├── README.md
│   │   ├── REPO_PROFILE.md
│   │   ├── GIT_TOWN_ADMISSION.md
│   │   ├── STACKED_PRS.md
│   │   ├── WORKER_PROTOCOL.md
│   │   ├── TASK_PACKET.md
│   │   ├── PUBLICATION.md
│   │   └── EVALS.md
│   └── harness/                                   [M] evidence ladder and mechanism contracts
│       ├── README.md
│       ├── git-town-task-packet.md
│       ├── git-town-doctor.md
│       ├── git-town-sync.md
│       ├── git-town-canaries.md
│       └── git-town-publication.md
├── examples/phase3/ … phase8/                     [M] dataset/config/policy fixtures
├── scripts/
│   ├── phase4_smoke.sh … phase8_smoke.sh          [M] offline per-phase smokes
│   └── git-town/                                  [M] issues #16–#20 delivery mechanisms
│       ├── task_packet.py                         [M] typed packet and path-lease validator
│       ├── doctor.sh, lease.py                    [M] linked-worktree admission and leases
│       ├── sync.sh, receipt.py                    [M] bounded no-push sync and receipts
│       └── publish.sh, github_snapshot.py,
│           remote_verify.py                       [M] publication gate and remote checks
├── src/llm_arbitrage_system/
│   ├── domain/                                    [M] immutable contracts
│   ├── analytics/                                 [M] adaptive feature state
│   ├── config/                                    [M] runtime defaults
│   ├── simulation/                                [M] planner/approval/executor/pipeline
│   ├── storage/                                   [M] replay journal
│   ├── reporting/                                 [M] evidence-bounded metrics
│   └── experiments/                               [M] experiment, trust, campaign, valuation,
│                                                      selection and review control plane
├── tests/                                         [M] runtime/evidence/experiment/trust tests
├── tests/git-town/                                [M] mechanism selftests and controls
├── fixtures/git-town/                             [M] deterministic canary tool
└── receipts/git-town/                             [P] issues #15/#18/#20/#21; written at run time
```

`receipts/git-town/` is the tracked receipt root named by `docs/git/REPO_PROFILE.md`. It is a route, not a claim that receipts exist: the sync adapter writes there when it runs, and it has never run against a real Git Town executable.

## Directory → State Machine → data contract

| Path | State Machine | Input | Output | Persistence | Failure/blocked state |
| --- | --- | --- | --- | --- | --- |
| `domain/` | domain validation | constructor fields | immutable events/plans/approvals/results | none | invalid value rejected before admission |
| `analytics/` | warm-up/advance | ordered `MarketEvent` | `FeatureSnapshot | None` | in memory per `venue:symbol` | analytics error aborts replay |
| `simulation/strategy_router.py` | route planning | event + features | paper `TradePlan | None` | decision via journal | threshold miss produces no plan |
| `experiments/determinism.py` | plan/leg identity | semantic evidence + sequence + plan | deterministic IDs | journal/bundle | noncanonical input fails |
| `simulation/approval.py` | risk/reservation/reconciliation | decision + terminal result | rejection or approved plan; exposure state | risk evidence in journal | reasons reject; residual halts |
| `simulation/executor.py` | execution/compensation | approved paper plan | filled/failed/compensated result | journal | partial outcome reverses confirmed fills |
| `simulation/pipeline.py` | bounded lifecycle | event iterable | replay/performance reports | through journal | cancel siblings → aborted → re-raise |
| `storage/sqlite_journal.py` | evidence lifecycle | causal runtime objects/reports | durable rows/status/integrity | SQLite WAL/FK/FULL sync | running → completed or aborted |
| `reporting/performance.py` | metric evidence | approvals/results + optional PnL | execution metrics; optional drawdown/Sharpe | journal/bundle JSON | unsupported claims remain null |
| `experiments/dataset.py` | dataset compilation | raw JSONL | typed events + source/semantic hashes | bundle inputs | schema/time/float/key failure |
| `experiments/config.py` | config compilation | raw YAML | typed config + source/canonical hashes | bundle inputs | unknown/duplicate/invalid field failure |
| `experiments/manifest.py` | experiment identity | input hashes + revision/version | experiment/run IDs | manifest | missing revision fails |
| `experiments/runner.py` | experiment composition | dataset/config | completed replay + staging evidence | staging SQLite/files | error removes staging |
| `experiments/bundle*.py` | publish/verify | staging evidence | atomic verified bundle | content-addressed directory | mismatch/integrity blocks publication |
| `sweep.py`, `walk_forward.py` | matrix planning | dataset/config/sweep | candidate/window/evaluation IDs | matrix JSON | oversized/invalid plan fails |
| `signing.py` | detached provenance | verified bundle + local Ed25519 key | attestation | external JSON | tamper/key/trust mismatch fails |
| `lineage.py` | lineage DAG | source/derived/slice manifest | lineage node | registry | invalid/missing parent fails |
| `evaluation.py` | OOS execution | matrix item + source inputs | test-slice-only bundle | bundle | candidate/window/hash mismatch fails |
| `registry.py` | trusted import | keys/lineage/signed bundles/evaluations | immutable rows | SQLite registry | trust/parent/identity conflict fails |
| `aggregation.py` | coverage summary | matrix + registrations | none/partial/complete coverage | JSON output | selection/PnL/Sharpe/alpha stay null |
| `docs/git/` | delivery policy | shared Skill + repo/issue/GitHub truth | profile/stack/Worker rules | tracked docs/TOML | missing evidence stays explicit |
| `docs/harness/` | delivery eval contract | packets/mechanisms/subjects | assertions and controls | tracked docs; receipts planned | disagreement blocks/fails |
| `scripts/git-town/` | fixed delivery adapters | admitted tool/packet/worktree/leases | bounded Git operations, gate decisions, receipts | `receipts/git-town/` when run | `MERGED` mechanisms; admitted for `darwin_arm64`, but no live run observed yet (#21) |

Detailed transitions: [`docs/state-machines.md`](docs/state-machines.md).

## Runtime State Machine and queue data flow

```text
Iterable[MarketEvent]
  │ persist event
  ▼
bounded data_queue
  ▼
AnalyticsEngine
  ER + KAMA + Z-score + ATR + Kalman
  │ warm-up may emit no output
  ▼
FeatureSnapshot
  ▼
PaperStrategyRouter
  ├── funding carry
  ├── crowding reversion
  └── RWA lead-lag
  │ persist decision
  ▼
bounded decision_queue
  ▼
StatefulPaperApprover
  freshness + edge + notional + exposure
  + duplicate + balance + slippage
  │ persist accepted/rejected evaluation
  ├── rejected → terminal for decision
  ▼
ApprovedTradePlan + reservation
  ▼
bounded approved_queue
  ▼
DeterministicPaperExecutor
  concurrent legs + failure injection + reversal
  │ persist result
  ▼
Approver reconciliation
  ├── FILLED      → simulated open exposure
  ├── COMPENSATED → reservation released
  └── residual    → halt new approvals
  ▼
ReplayReport + ResearchPerformanceReport
```

Failure path:

```text
any stage raises
  → cancel siblings
  → journal running → aborted
  → preserve causal evidence
  → remove owned experiment staging
  → re-raise
```

Sentinels drain each bounded stage in order; a pipeline instance is single-use.

## Experiment and evidence data flow

```text
market_events.jsonl                experiment.yaml
  → strict parse/canonicalize        → strict parse/canonicalize
  → DatasetSnapshot                  → ExperimentConfigSnapshot
       source/semantic hashes             source/canonical hashes
              └──────────────┬──────────────┘
                             ▼
                 code revision + package version
                             ▼
                     ExperimentManifest
                     experiment_id/run_id
                             ▼
                   hidden staging directory
                             ▼
       ContentAddressedPlanner + PaperReplayPipeline
                             ▼
        evidence.sqlite3 + replay/performance reports
                             ▼
     manifest + raw/canonical inputs + report.md + checksums
                             ▼
            independent verification + atomic rename
                             ▼
                 exp-<semantic-identity>/
```

Verification checks exact file set, checksums, manifest identity, source↔canonical linkage, event metadata, SQLite integrity, one matching run ID, and `completed` status.

## Signed provenance, lineage, and OOS registry flow

```text
verified bundle
  + local Ed25519 private key outside repository
  + optional lineage manifest
  → detached attestation
      signer/public key + experiment/run IDs
      + manifest/checksum/root digests + optional lineage ID
  → signature/trust/lineage verification
  → trusted-key allowlist + parent-complete lineage DAG
  → immutable experiment import

Phase 3 matrix + evaluation_id
  → recompute matrix/candidate/window/train/test identities
  → replay test slice only
  → evaluation.json + checksummed bundle
  → detached signature
  → trusted matrix-bound registration
  → candidate none / partial / complete coverage
```

Signatures prove key possession for captured bytes. Lineage records asserted transformations. Registry trust records a local allowlist decision. None proves market truth, legal identity, realized profit, future performance, or risk-free returns.

## Git Town Worker State Machine

Canonical shared method:

[`ed3c/skills-shared/skills/git-town-stacked-pr-worker`](https://github.com/ed3c/skills-shared/tree/main/skills/git-town-stacked-pr-worker)

Repository pin:

```text
Git Town:       v24.0.0
Tag commit:     0f3e55f5a6bae5b319dd713a0606263d0551af66
Live admission: false
Owner issue:    #15
```

The repository does not copy the shared Skill. It owns `.git-town.toml`, the repository profile, task packets, leases, adapters, CI, receipts, branch/PR graph, cleanup, and rollback.

```text
TASK_PROPOSED
  → complete eval-first task packet
  → exact host tool admission
  → linked worktree + exclusive branch/path leases
  → clean/ancestry/remote/non-interactive preflight
  → dry-run:
      git town sync --stack --dry-run --non-interactive --no-auto-resolve --no-push
  → bounded no-push sync:
      git town sync --stack --non-interactive --no-auto-resolve --no-push
  ├── NO_CHANGE / SYNCED
  ├── BLOCKED_DIRTY / PROMPT / CONFLICT / TIMEOUT / POLICY
  └── FAILED_TOOL
  → independent graph/path/protected-ref verification
  → exact-head repository evals + negative controls
  → append-only local receipt
  → one-intent publication gate
  → post-push remote head/ancestry verification
  → GitHub trusted check
  → Human Admit
  → merge
```

Current mechanism states:

| Lane | State | Issue |
| --- | --- | --- |
| Static profile/config/governance | `MERGED` | #13 / PR #23 |
| Host executable/provenance/SBOM/notices/legal receipt | `NOT_EXERCISED` | #15 |
| Task-packet/path-lease validator | `MERGED` mechanism | #16 / PR #62 |
| Worktree/lease doctor | `MERGED` mechanism | #17 / PR #63 |
| Bounded no-push sync/receipt writer | `MERGED` mechanism | #18 / PR #64 |
| Conflict/prompt/timeout/rollback canaries | `MERGED` mechanism | #19 / PR #65 |
| Publication gate/remote verifier | `MERGED` mechanism | #20 / PR #66 |
| Live Git Town synchronization | `NOT_EXERCISED` | #15, #21 |
| Live adoption audit | `NOT_EXERCISED` | #21 |

`MERGED` mechanism means the adapter and its disagreement-producing controls exist and pass in CI. It does not promote the live lane: every transition above still runs against a fixture or refuses with `BLOCKED_TOOL_ADMISSION`, because no host executable has been admitted.

The branch/PR ancestry in this repository is real GitHub state. It is not a local admitted Git Town sync receipt.

## Historical merged PR index

| Phase | PR | Merge subject | State |
| --- | --- | --- | --- |
| Phase 1 contracts/analytics | [#1](https://github.com/ed3c/llm_arbitrage_system/pull/1) | `0e8ceec3456ad2c74fa77237d3b814520f0213fc` | `MERGED` |
| Phase 2 paper runtime | [#3](https://github.com/ed3c/llm_arbitrage_system/pull/3) | `1a255ad865ce346816bc04ef8680d80477c32cc7` | `MERGED` |
| Phase 2B evidence/reporting/CI | [#4](https://github.com/ed3c/llm_arbitrage_system/pull/4) | `215ca9c7c81bea456a4e358a9d750a7157a9872b` | `MERGED` |
| Phase 3 reproducible experiments | [#6](https://github.com/ed3c/llm_arbitrage_system/pull/6) | `e201e4b012e1596a7c470309cd2af792e009ee17` | `MERGED` |
| Phase 4 provenance/lineage/OOS registry | [#10](https://github.com/ed3c/llm_arbitrage_system/pull/10) | `55ecf0e9a91006f563a080661cb6adf650e2439a` | `MERGED` |
| CI prerequisite | [#26](https://github.com/ed3c/llm_arbitrage_system/pull/26) | `989ee49533bfaef1bbbb1b1462dc58cf71897e6f` | `MERGED` |
| Documentation SSOT 1/3 | [#22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `8a2b955c594dfbd69895d87adc3c2c5700940cee` | `MERGED` |
| Documentation SSOT 2/3 | [#23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `60bb43770041fc5e8f0f619ad730034b8bea3462` | `MERGED` |
| Documentation SSOT 3/3 | [#24](https://github.com/ed3c/llm_arbitrage_system/pull/24) | `b0e1e86ea17b801a3149b9001d32d1fb4ec0d4ee` | `MERGED` |
| Phase 5A/B/C campaigns | [#31](https://github.com/ed3c/llm_arbitrage_system/pull/31), [#32](https://github.com/ed3c/llm_arbitrage_system/pull/32), [#33](https://github.com/ed3c/llm_arbitrage_system/pull/33) | `53b9a8b`, `96d387e`, `f8fe5f8` | `MERGED` |
| Phase 6A/B/C valuation | [#39](https://github.com/ed3c/llm_arbitrage_system/pull/39), [#40](https://github.com/ed3c/llm_arbitrage_system/pull/40), [#41](https://github.com/ed3c/llm_arbitrage_system/pull/41) | `3af5bb5`, `3d96416`, `00b2fd1` | `MERGED` |
| Phase 7A/B/C selection governance | [#50](https://github.com/ed3c/llm_arbitrage_system/pull/50), [#52](https://github.com/ed3c/llm_arbitrage_system/pull/52), [#53](https://github.com/ed3c/llm_arbitrage_system/pull/53) | `ae45c60`, `31e6fc4`, `b54013b` | `MERGED` |
| Phase 8A/B/C separation of duties | [#59](https://github.com/ed3c/llm_arbitrage_system/pull/59), [#60](https://github.com/ed3c/llm_arbitrage_system/pull/60), [#61](https://github.com/ed3c/llm_arbitrage_system/pull/61) | `8bb7459`, `d8a5a01`, `008fb92` | `MERGED` |
| GT-02…GT-06 delivery mechanisms | [#62](https://github.com/ed3c/llm_arbitrage_system/pull/62)–[#66](https://github.com/ed3c/llm_arbitrage_system/pull/66) | `955aa12`, `d38428c`, `f230887`, `dab0908`, `2bcbeae` | `MERGED` |

Every one of these merged with a merge commit. The stack was serial, so squashing a parent would have rewritten commits each child already contained.

## Git Town molecular leaf status

```text
main
└── tooling/git-town-task-packet-validator         #16  MERGED
    └── tooling/git-town-worktree-doctor           #17  MERGED
        └── tooling/git-town-bounded-sync          #18  MERGED
            └── test/git-town-fail-closed-canaries #19  MERGED
                └── tooling/git-town-publication-gate #20  MERGED

infra/git-town-admitted                            #15  PASS (darwin_arm64)
convergence/git-town-adoption-audit                #21  sync lane PASS, publication NOT_EXERCISED
```

| Issue | Molecular owner | Disagreement evidence that exists | State |
| --- | --- | --- | --- |
| [#15](https://github.com/ed3c/llm_arbitrage_system/issues/15) | exact host tool admission | each of 12 lanes planted at `FAIL` and `NOT_EXERCISED`, asserted to block alone | `PASS` for `darwin_arm64`, receipt `eda73fcc` |
| [#16](https://github.com/ed3c/llm_arbitrage_system/issues/16) | typed packet/path lease | removed field (generated per schema field), sibling overlap, wrong parent, arbitrary shell field | `MERGED` |
| [#17](https://github.com/ed3c/llm_arbitrage_system/issues/17) | linked worktree/leases | primary checkout, dirty state, in-progress operation, duplicate/expired lease, credential-bearing remote, missing prompt policy | `MERGED` |
| [#18](https://github.com/ed3c/llm_arbitrage_system/issues/18) | dry-run/no-push sync/receipts | scope mismatch, dropped `--no-push`, timeout, prompt, remote movement, out-of-lease diff, moved perennial ref | `MERGED` |
| [#19](https://github.com/ed3c/llm_arbitrage_system/issues/19) | conflict/cleanup/rollback canaries | planted conflict, **silent conflict on a zero exit**, editor/credential prompt, timeout, orphaned grandchild, residue, ref movement, rollback drift | `MERGED` |
| [#20](https://github.com/ed3c/llm_arbitrage_system/issues/20) | publication/remote verifier | stale receipt, old-SHA CI, repeated feedback, open billing circuit, wrong remote, missing guard, head mismatch, protected-ref rewrite, replayed decision | `MERGED` |
| [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21) | live adoption audit | three defects found only by running it for real | sync lane `PASS`, publication lanes `NOT_EXERCISED` |

`#16` named `infra/git-town-admission` as its parent. That branch was never created because `#15` is blocked on human decisions, so the tooling stack parented onto the documentation stack instead and asserts no `#15` lane.

**A `MERGED` row is mechanism evidence, not live evidence.** Git Town `v24.0.0` is admitted for `darwin_arm64` by receipt `eda73fcc` (#15). Admission makes a live run possible; it does not make one observed. `live_canary` stays `NOT_EXERCISED` until issue #21 runs it, and a host without its own receipt still returns `BLOCKED_TOOL_ADMISSION`. The canaries drive `fixtures/git-town/canary_tool.sh`, which reproduces the conditions the protocol enumerates rather than Git Town's semantics.

See [`docs/git/STACKED_PRS.md`](docs/git/STACKED_PRS.md) for full packets, rollback subjects, dependencies, controls, and evidence lanes.

## Install, test, and smoke

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

make check
make phase3-smoke
make phase4-smoke

make phase5-smoke
make phase6-smoke
make phase7-smoke
make phase8-smoke
```

Delivery-mechanism gates:

```bash
pytest tests/git-town

python scripts/git-town/task_packet.py --selftest
python scripts/git-town/lease.py --selftest
python scripts/git-town/receipt.py --selftest
python scripts/git-town/github_snapshot.py --selftest
python scripts/git-town/remote_verify.py --selftest
bash scripts/git-town/doctor.sh --selftest
bash scripts/git-town/sync.sh --selftest
bash scripts/git-town/publish.sh --selftest
```

Each `--selftest` plants mutations and fails if any of them validates, so the red path is exercised by the same command that reports green.

CI runs three jobs:

```text
Quality gates (Python 3.13)      ruff, strict mypy, pytest + coverage floor, phase 3-8 smokes
Python 3.10 / 3.11 / 3.12        compatibility test run
Git Town delivery mechanisms     every --selftest plus tests/git-town
```

These commands test the offline repository. They do not prove Git Town host admission, a live synchronization, a publication, or a live trading path.

## Phase 3 experiment quick start

```bash
llm-arbitrage validate-dataset examples/phase3/market_events.jsonl
llm-arbitrage validate-config examples/phase3/experiment.yaml

llm-arbitrage run \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --output .phase3-runs \
  --code-revision "$(git rev-parse HEAD)"

BUNDLE="$(find .phase3-runs -mindepth 1 -maxdepth 1 -type d -name 'exp-*' -print -quit)"
llm-arbitrage verify "$BUNDLE"

llm-arbitrage plan-matrix \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --sweep examples/phase3/sweep.yaml \
  --output .phase3-runs/matrix.json
```

`run` refuses silent overwrite. `--force` is for disposable local evidence only.

## Phase 4 trust/OOS commands

```text
validate-lineage
keygen
sign-bundle
verify-attestation
run-evaluation
registry-init
registry-trust-key
registry-import-lineage
registry-import-bundle
registry-register-evaluation
registry-verify
registry-aggregate
```

Use `make phase4-smoke` for the complete credential-free local flow. Generated private provenance keys remain outside Git and evidence bundles.

## Evidence boundaries and non-goals

Supported evidence includes typed offline inputs, deterministic transformations, paper execution outcomes, causal SQLite records, bundle byte integrity, signature validity, local signer allowlist decisions, asserted lineage ancestry, matrix/evaluation identity binding, and registered OOS coverage.

Unsupported claims include original market-data authenticity, legal signer identity, live venue/account state, deposits/withdrawals, realized trading profit, future performance, risk-free arbitrage, automatic candidate selection, release state, and production observation.

Private keys, API secrets, seed phrases, account identifiers, withdrawal authority, browser sessions, credential-bearing URLs, external order endpoints, venue SDKs, network probes, and a live-mode branch are prohibited.

## Human Admit

```text
semantic conflict resolution
git town continue / skip / undo / ship
PR-ready transition and retargeting
merge or merge-queue admission
legal/license acceptance
permission, branch-protection, billing, or secret changes
release promotion and production deployment
destructive or drifted rollback
```

Epic #11's documentation stack merged after the whole stack was reviewed together against current exact-head checks. Each PR in this repository was retargeted to `main`, revalidated at its post-update head, and merged only with every check green on that exact subject. Merge itself was never automated: each one ran under explicit human authorization.
