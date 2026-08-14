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
6. for Git/Stack PR work:
   - [`docs/git/README.md`](docs/git/README.md);
   - [`docs/git/REPO_PROFILE.md`](docs/git/REPO_PROFILE.md);
   - [`docs/git/GIT_TOWN_ADMISSION.md`](docs/git/GIT_TOWN_ADMISSION.md);
   - [`docs/git/STACKED_PRS.md`](docs/git/STACKED_PRS.md);
   - [`docs/git/WORKER_PROTOCOL.md`](docs/git/WORKER_PROTOCOL.md);
   - [`docs/git/TASK_PACKET.md`](docs/git/TASK_PACKET.md);
   - [`docs/git/EVALS.md`](docs/git/EVALS.md);
   - [`docs/harness/README.md`](docs/harness/README.md);
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
main@55ecf0e9a91006f563a080661cb6adf650e2439a
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
| Agent/integration SSOT | issue #12 / [PR #22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `OPEN_DRAFT` |
| Git Town governance/profile | issue #13 / [PR #23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `OPEN_DRAFT` |
| README convergence/index | issue #14 / [PR #24](https://github.com/ed3c/llm_arbitrage_system/pull/24) | `OPEN_DRAFT` |
| Git Town host admission and adapters | issues #15–#21 | `PLANNED` / `NOT_IMPLEMENTED` / `NOT_EXERCISED` |
| Live exchange/broker execution | prohibited | `BLOCKED` |

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

Markers: `[M]` merged, `[D]` Draft documentation stack, `[P]` planned path not yet implemented.

```text
llm_arbitrage_system/
├── AGENTS.md                                      [D] Agent routing and invariants
├── README.md                                      [D] convergence and traceability index
├── .git-town.toml                                 [D] conservative static Git Town policy
├── Makefile                                       [M] quality and smoke entrypoints
├── pyproject.toml                                 [M] package, CLI and dependencies
├── SECURITY.md                                    [M] paper-only and secret boundary
├── config/README.md                               [M] configuration guidance
├── docs/
│   ├── integration-status.md                      [D] merged/open/planned SSOT
│   ├── state-machines.md                          [D] transition ownership
│   ├── data-flow.md                               [D] end-to-end movement/evidence
│   ├── architecture.md                            [M] runtime/experiment architecture
│   ├── replay-evidence.md                         [M] SQLite/report contract
│   ├── phase3-experiments.md                      [M] reproducible experiment contract
│   ├── phase4-trust-registry.md                   [M] provenance/lineage/OOS registry
│   ├── git/                                       [D] repository Git Town projection
│   │   ├── README.md
│   │   ├── REPO_PROFILE.md
│   │   ├── GIT_TOWN_ADMISSION.md
│   │   ├── STACKED_PRS.md
│   │   ├── WORKER_PROTOCOL.md
│   │   ├── TASK_PACKET.md
│   │   └── EVALS.md
│   └── harness/README.md                          [D] evidence ladder and controls
├── examples/phase3/                               [M] dataset/config/sweep fixtures
├── examples/phase4/                               [M] lineage fixture
├── scripts/phase4_smoke.sh                        [M] offline trust/OOS smoke
├── src/llm_arbitrage_system/
│   ├── domain/                                    [M] immutable contracts
│   ├── analytics/                                 [M] adaptive feature state
│   ├── config/                                    [M] runtime defaults
│   ├── simulation/                                [M] planner/approval/executor/pipeline
│   ├── storage/                                   [M] replay journal
│   ├── reporting/                                 [M] evidence-bounded metrics
│   └── experiments/                               [M] experiment and trust control plane
├── tests/                                         [M] runtime/evidence/experiment/trust tests
├── scripts/git-town/                              [P] issues #16–#20; `NOT_IMPLEMENTED`
├── tests/git-town/                                [P] issues #16–#20; `NOT_IMPLEMENTED`
├── fixtures/git-town/                             [P] issue #19; `NOT_IMPLEMENTED`
└── receipts/git-town/                             [P] issues #15/#18/#20/#21; `NOT_IMPLEMENTED`
```

Planned paths are ownership routes, not claims that empty or hidden implementations exist.

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
| `scripts/git-town/` | future fixed adapters | admitted tool/packet/worktree/leases | bounded Git operations/receipts | planned receipt store | `NOT_IMPLEMENTED` until #16–#20 |

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
| Static profile/config/governance | `OPEN_DRAFT` | #13 / PR #23 |
| Host executable/provenance/SBOM/notices/legal receipt | `NOT_EXERCISED` | #15 |
| Task-packet/path-lease validator | `NOT_IMPLEMENTED` | #16 |
| Worktree/lease doctor | `NOT_IMPLEMENTED` | #17 |
| Bounded no-push sync/receipt writer | `NOT_IMPLEMENTED` | #18 |
| Conflict/prompt/timeout/rollback canaries | `NOT_IMPLEMENTED` | #19 |
| Publication gate/remote verifier | `NOT_IMPLEMENTED` | #20 |
| Live adoption audit | `NOT_EXERCISED` | #21 |

The documentation branch/PR ancestry is real GitHub state. It is not a local admitted Git Town sync receipt.

## Historical merged PR index

| Phase | PR | Merge subject | State |
| --- | --- | --- | --- |
| Phase 1 contracts/analytics | [#1](https://github.com/ed3c/llm_arbitrage_system/pull/1) | `0e8ceec3456ad2c74fa77237d3b814520f0213fc` | `MERGED` |
| Phase 2 paper runtime | [#3](https://github.com/ed3c/llm_arbitrage_system/pull/3) | `1a255ad865ce346816bc04ef8680d80477c32cc7` | `MERGED` |
| Phase 2B evidence/reporting/CI | [#4](https://github.com/ed3c/llm_arbitrage_system/pull/4) | `215ca9c7c81bea456a4e358a9d750a7157a9872b` | `MERGED` |
| Phase 3 reproducible experiments | [#6](https://github.com/ed3c/llm_arbitrage_system/pull/6) | `e201e4b012e1596a7c470309cd2af792e009ee17` | `MERGED` |
| Phase 4 provenance/lineage/OOS registry | [#10](https://github.com/ed3c/llm_arbitrage_system/pull/10) | `55ecf0e9a91006f563a080661cb6adf650e2439a` | `MERGED` |

## Active documentation Stack PRs

Epic: [#11](https://github.com/ed3c/llm_arbitrage_system/issues/11).

```text
main@55ecf0e9a91006f563a080661cb6adf650e2439a
└── PR #22 / issue #12 / docs/phase4-integration-ssot
    └── PR #23 / issue #13 / docs/git-town-governance
        └── PR #24 / issue #14 / docs/readme-state-flow-index
```

| Order | PR | Base → head | Path lease | State |
| --- | --- | --- | --- | --- |
| 1 | [#22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `main → docs/phase4-integration-ssot` | `AGENTS.md`, integration/state/data-flow docs | `OPEN_DRAFT` |
| 2 | [#23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `docs/phase4-integration-ssot → docs/git-town-governance` | `.git-town.toml`, `docs/git/**`, `docs/harness/**`, templates | `OPEN_DRAFT` |
| 3 | [#24](https://github.com/ed3c/llm_arbitrage_system/pull/24) | `docs/git-town-governance → docs/readme-state-flow-index` | `README.md`, `docs/git/STACKED_PRS.md` | `OPEN_DRAFT` |

Parent-first merge order requires explicit Human Admit. After each parent merge, retarget the child and rerun exact-head/base checks. No Agent marks ready, retargets, merges, enters a queue, or invokes `git town ship` automatically.

## Planned molecular leaf Stack PRs

```text
main after documentation convergence
└── infra/git-town-admission                           #15
    └── tooling/git-town-task-packet-validator         #16
        └── tooling/git-town-worktree-doctor           #17
            └── tooling/git-town-bounded-sync          #18
                └── test/git-town-fail-closed-canaries #19
                    └── tooling/git-town-publication-gate #20
                        └── convergence/git-town-adoption-audit #21
```

| Issue | Branch/parent | Molecular owner | Path lease summary | Required disagreement evidence | State |
| --- | --- | --- | --- | --- | --- |
| [#15](https://github.com/ed3c/llm_arbitrage_system/issues/15) | `infra/git-town-admission ← main` | exact host tool admission | admission doc/receipts | wrong version/digest/architecture; missing legal/transitive state | `PLANNED`, blocked on host/legal owners |
| [#16](https://github.com/ed3c/llm_arbitrage_system/issues/16) | `tooling/git-town-task-packet-validator ← #15` | typed packet/path lease | validator/tests/Harness | removed field, overlap, wrong parent, arbitrary shell | `PLANNED` |
| [#17](https://github.com/ed3c/llm_arbitrage_system/issues/17) | `tooling/git-town-worktree-doctor ← #16` | linked worktree/leases | doctor/lease/tests/docs | primary checkout, dirty state, duplicate/expired lease, bad remote | `PLANNED` |
| [#18](https://github.com/ed3c/llm_arbitrage_system/issues/18) | `tooling/git-town-bounded-sync ← #17` | dry-run/no-push sync/receipts | fixed adapters/tests/docs | scope mismatch, timeout, prompt, remote movement, path drift | `PLANNED` |
| [#19](https://github.com/ed3c/llm_arbitrage_system/issues/19) | `test/git-town-fail-closed-canaries ← #18` | conflict/cleanup/rollback canaries | tests/fixtures/docs | conflict, prompt, timeout, residue, ref movement, rollback drift | `PLANNED` |
| [#20](https://github.com/ed3c/llm_arbitrage_system/issues/20) | `tooling/git-town-publication-gate ← #19` | publication/remote verifier | adapters/tests/CI/docs | stale receipt, old SHA, feedback, billing, wrong remote/head/parent | `PLANNED` |
| [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21) | `convergence/git-town-adoption-audit ← #20` | live adoption audit | convergence docs/receipts | missing evidence lane; false promotion of `NOT_EXERCISED` | `PLANNED` |

See [`docs/git/STACKED_PRS.md`](docs/git/STACKED_PRS.md) for full packets, rollback subjects, dependencies, controls, and evidence lanes.

## Install, test, and smoke

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

make check
make phase3-smoke
make phase4-smoke
```

CI runs Ruff, strict Mypy, pytest with coverage, Python 3.10–3.13 compatibility, Phase 3 smoke, and Phase 4 trust/registry smoke. These commands test the offline repository; they do not prove Git Town admission or a live trading path.

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

All documentation PRs under epic #11 remain Draft until the complete stack and current exact-head checks are reviewed together.
