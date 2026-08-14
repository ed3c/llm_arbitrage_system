# LLM Arbitrage System

A credential-free, deterministic, paper-only research harness derived from the supplied *Trading Systems and Methods 資源* architecture.

The merged data plane studies three offline scenarios—funding carry, overcrowding reversion, and RWA lead-lag—through Kaufman/noise analytics, central approval, compensated paper execution, durable evidence, reproducible experiments, signed provenance, dataset lineage, and a trusted local OOS registry.

It does **not** connect to exchanges, brokers, wallets, accounts, deposits, withdrawals, market WebSockets, or live order endpoints.

## Status vocabulary

This repository never collapses implementation, evidence, or delivery states:

```text
MERGED            bytes are reachable from the stated main subject
OPEN_DRAFT        issue/PR exists and is intentionally Draft
OPEN_READY        issue/PR exists and is admitted for review, not merge
PLANNED           decomposed work with no available implementation
BLOCKED           policy or missing precondition prevents progress

PASS
FAIL
ABSENT
NOT_IMPLEMENTED
NOT_EXERCISED
SKIPPED_BY_POLICY
```

Static documentation or config is not a live-tool `PASS`. Local sync is not publication, CI, review, merge, release, production, market truth, or profitability `PASS`.

## Agent entrypoint

Agents must read in this order before editing:

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
7. the canonical issue/task packet, nearest directory `README.md`, current branch/PR graph, exact heads, and workflow evidence.

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
| Domain | immutable typed contracts, timezone-aware timestamps, exact `Decimal` money/rates | `MERGED` |
| Analytics | Kaufman ER/KAMA, rolling Z-score, ATR percentage, Kalman filter | `MERGED` |
| Strategy | paper-only funding, crowding, and RWA lead-lag routing | `MERGED` |
| Approval | freshness, edge, notional, exposure, duplicate, balance, slippage gates | `MERGED` |
| Simulation | deterministic concurrent fills, failure injection, partial-outcome reversal | `MERGED` |
| Replay evidence | append-only SQLite lifecycle/events/decisions/risk/results/reports | `MERGED` |
| Reporting | execution quality and evidence-bounded optional risk metrics | `MERGED` |
| Phase 3 experiments | strict inputs, semantic IDs, atomic bundles, verification, sweeps, walk-forward plans | `MERGED` |
| Phase 4 trust/OOS | Ed25519 attestations, lineage DAG, test-only evaluation, trusted registry, coverage aggregation | `MERGED` |
| Agent/integration SSOT | issues #11–#12, PR #22 | `OPEN_DRAFT` |
| Git Town governance/profile | issue #13, PR #23 | `OPEN_DRAFT` |
| README convergence/index | issue #14, convergence PR | `OPEN_DRAFT` after publication |
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

| Source directory/concept | Actual repository owner | Boundary |
| --- | --- | --- |
| `config/` | `src/llm_arbitrage_system/config/`, `experiments/config.py`, examples | behavior config only; no secrets |
| `core` contracts | `domain/` | immutable values, no I/O |
| data ingestion | `experiments/dataset.py` | strict offline JSONL, not live WebSocket |
| analytics | `analytics/` | merged Kaufman/noise features |
| strategies | `simulation/strategy_router.py` | paper-only route generation |
| risk/portfolio | `simulation/approval.py` | simulated capacity/reservations/reconciliation |
| execution | `simulation/executor.py` | deterministic paper fills only |
| event loop | `simulation/pipeline.py` | bounded queue pipeline |
| storage | `storage/sqlite_journal.py` | durable local replay evidence |
| backtest/reporting | `experiments/`, `reporting/` | reproducible replay/evidence, not a live venue |
| external adapters | no implementation | `NOT_IMPLEMENTED` |

The PDF is a design basis. The code tree and merged PR history determine implementation truth.

## Repository directory structure

Markers:

```text
[M] merged on main baseline
[D] open Draft documentation stack
[P] planned future leaf; path may not exist yet
[X] prohibited
```

```text
llm_arbitrage_system/
├── AGENTS.md                                      [D] Agent routing and invariants
├── README.md                                      [D] convergence and traceability index
├── .git-town.toml                                 [D] conservative static Git Town policy
├── Makefile                                       [M] quality and smoke entrypoints
├── pyproject.toml                                 [M] package, CLI and dev dependencies
├── SECURITY.md                                    [M] paper-only and secret boundary
├── config/
│   └── README.md                                  [M] configuration guidance
├── docs/
│   ├── integration-status.md                      [D] merged/open/planned SSOT
│   ├── state-machines.md                          [D] transition ownership
│   ├── data-flow.md                               [D] end-to-end movement/evidence
│   ├── architecture.md                            [M] runtime/experiment architecture
│   ├── replay-evidence.md                         [M] SQLite/report contract
│   ├── phase3-experiments.md                      [M] reproducible experiment contract
│   ├── phase4-trust-registry.md                   [M] provenance/lineage/OOS registry
│   ├── git/                                       [D] repository Git Town projection
│   │   ├── README.md                              ownership/read order/adoption state
│   │   ├── REPO_PROFILE.md                        exact repository/tool/worker profile
│   │   ├── GIT_TOWN_ADMISSION.md                  exact-tool admission gaps
│   │   ├── STACKED_PRS.md                         branch/issue/PR/merge index
│   │   ├── WORKER_PROTOCOL.md                     fail-closed Worker algorithm
│   │   ├── TASK_PACKET.md                         eval-first packet schema
│   │   └── EVALS.md                               assertions and controls
│   └── harness/
│       └── README.md                              [D] evidence ladder/fixed entrypoints
├── examples/
│   ├── phase3/                                    [M] dataset/config/sweep fixtures
│   └── phase4/                                    [M] lineage fixture
├── scripts/
│   └── phase4_smoke.sh                            [M] complete offline trust/OOS smoke
├── src/llm_arbitrage_system/
│   ├── domain/                                    [M] immutable cross-layer contracts
│   ├── analytics/                                 [M] adaptive feature state
│   ├── config/                                    [M] analytics runtime defaults
│   ├── simulation/                                [M] planner/approval/executor/pipeline
│   ├── storage/                                   [M] append-only replay journal
│   ├── reporting/                                 [M] evidence-bounded metrics
│   └── experiments/                               [M] Phase 3/4 control and trust plane
├── tests/                                         [M] runtime, evidence, experiment, trust tests
├── scripts/git-town/                              [P] issues #16–#20; NOT_IMPLEMENTED
├── tests/git-town/                                [P] issues #16–#20; NOT_IMPLEMENTED
├── fixtures/git-town/                             [P] issue #19; NOT_IMPLEMENTED
└── receipts/git-town/                             [P] issues #15/#18/#20/#21; NOT_IMPLEMENTED
```

Planned paths are shown for ownership routing only. Their absence is intentional until the owning issue implements them.

## Directory → State Machine → data contract

| Path | State Machine owner | Input | Output | Persistence | Fail/blocked transition |
| --- | --- | --- | --- | --- | --- |
| `domain/` | domain validation | constructor fields | immutable `MarketEvent`, plan, approval, fill/result contracts | none | invalid value raises before admission |
| `analytics/` | feature warm-up/advance | ordered `MarketEvent` | `FeatureSnapshot | None` | in-memory per `venue:symbol` | indicator error aborts replay |
| `simulation/strategy_router.py` | route planning | event + features | paper `TradePlan | None` | decision via journal | no threshold → no plan |
| `experiments/determinism.py` | plan/leg identity | semantic dataset/event/features/sequence/plan | deterministic IDs | bundle/journal | noncanonical value fails |
| `simulation/approval.py` | risk/reservation/reconciliation | `StrategyDecision`, terminal result | rejection or `ApprovedTradePlan`; open/residual exposure | in-memory, risk evidence in journal | reasons reject; residual halts |
| `simulation/executor.py` | deterministic execution/compensation | approved paper plan | `FILLED`, `FAILED`, `COMPENSATED` result | journal | partial legs reverse confirmed fills |
| `simulation/pipeline.py` | bounded orchestration lifecycle | event iterable | replay/performance reports | through journal | cancel siblings → aborted → re-raise |
| `storage/sqlite_journal.py` | replay evidence lifecycle | events/decisions/risk/results/reports | durable rows, status, integrity result | SQLite WAL/FK/FULL sync | running → aborted or completed only |
| `reporting/performance.py` | evidence-bounded metrics | approved plans + results + optional PnL evidence | execution metrics, optional drawdown/Sharpe | journal/bundle JSON | unsupported fields remain null |
| `experiments/dataset.py` | dataset compilation | raw JSONL | typed events, source/semantic/event hashes, canonical JSONL | bundle inputs | schema/time/float/key errors fail closed |
| `experiments/config.py` | configuration compilation | raw YAML | typed config, source/canonical hashes | bundle inputs | unknown/duplicate/invalid fields fail closed |
| `experiments/manifest.py` | experiment identity | dataset/config hashes + revision/version | experiment/run IDs | `manifest.json` | missing revision fails |
| `experiments/runner.py` | experiment composition | validated dataset/config | completed pipeline and staging evidence | staging SQLite/files | any error deletes staging |
| `experiments/bundle*.py` | bundle publication/verification | staging inputs/evidence/reports | atomically published verified bundle | content-addressed directory | mismatch/extra/missing/integrity failure blocks publish |
| `experiments/sweep.py`, `walk_forward.py` | matrix planning | base dataset/config + strict sweep | candidate/window/evaluation identities | `matrix.json` | oversized grid/window contract fails |
| `experiments/signing.py` | detached provenance | verified bundle + local Ed25519 key + optional lineage | signed attestation | external JSON | tamper/key/trust/lineage mismatch fails |
| `experiments/lineage.py` | lineage DAG | source/derived/slice manifest | content-addressed lineage node | registry | source parent or missing child parent fails |
| `experiments/evaluation.py` | planned OOS execution | matrix item + source dataset/config | test-slice-only evaluation bundle | bundle | candidate/window/hash mismatch fails |
| `experiments/registry.py` | local trust/import state | keys, lineage, signed bundles/evaluations | immutable trusted/untrusted rows | SQLite registry | missing trust/parent or identity conflict fails |
| `experiments/aggregation.py` | coverage summary | matrix + registered evaluations | none/partial/complete coverage and supported averages | JSON output | no automatic selection/PnL/Sharpe/alpha |
| `docs/git/` | repository delivery policy | shared Skill + repo/issue/GitHub truth | profile, stack graph, Worker/publication rules | tracked docs/TOML | missing evidence remains explicit |
| `docs/harness/` | delivery eval contract | task packet/mechanism/subjects | assertions, controls, evidence requirements | tracked docs; receipts planned | disagreement must block/fail |
| `scripts/git-town/` | future fixed adapters | admitted packet/tool/worktree/leases | bounded Git operations and receipts | planned receipt store | `NOT_IMPLEMENTED` until #16–#20 |

Full transition details: [`docs/state-machines.md`](docs/state-machines.md).

## Runtime State Machine and queue data flow

```text
Iterable[MarketEvent]
  │ persist event
  ▼
┌─────────────────────┐
│ bounded data_queue  │
└──────────┬──────────┘
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
┌─────────────────────────┐
│ bounded decision_queue  │
└──────────┬──────────────┘
           ▼
StatefulPaperApprover
  freshness + edge + notional + exposure
  + duplicate + balance + slippage
           │ persist accepted/rejected evaluation
           ├── rejected → counter, terminal for decision
           ▼
ApprovedTradePlan + reservation
           ▼
┌─────────────────────────┐
│ bounded approved_queue  │
└──────────┬──────────────┘
           ▼
DeterministicPaperExecutor
  concurrent legs + failure injection + reversal
           │ persist result
           ▼
Approver reconciliation
  ├── FILLED       → simulated open exposure
  ├── COMPENSATED  → reservation released
  └── residual     → halt new approval
           ▼
ReplayReport + ResearchPerformanceReport
```

Failure path:

```text
any stage raises
  → cancel siblings
  → journal running → aborted
  → preserve causal evidence
  → remove experiment staging if owned by runner
  → re-raise
```

The pipeline is single-use; sentinels drain each bounded stage in order.

## Experiment and evidence data flow

```text
market_events.jsonl                  experiment.yaml
       │ strict parse/canonicalize          │ strict parse/canonicalize
       ▼                                    ▼
DatasetSnapshot                       ExperimentConfigSnapshot
source + semantic hashes              source + canonical hashes
       └───────────────┬────────────────────┘
                       ▼
              code revision + package version
                       ▼
                ExperimentManifest
             experiment_id + run_id
                       ▼
             hidden staging directory
                       ▼
     ContentAddressedPlanner + PaperReplayPipeline
                       ▼
 evidence.sqlite3 + replay/performance reports
                       ▼
 manifest + source/canonical inputs + report.md
                       ▼
 checksums.sha256 + independent verification
                       ▼
 atomic `exp-<semantic-identity>/` publication
```

Bundle verification checks exact file set, checksums, manifest identity, source↔canonical linkage, event metadata, SQLite integrity, one matching run ID, and `completed` status.

## Signed provenance, lineage, and OOS registry flow

```text
verified bundle
  + local Ed25519 private key outside repository
  + optional lineage manifest
        ▼
detached attestation
  signer key ID + embedded public key
  + experiment/run IDs
  + manifest/checksum/root digests
  + optional lineage ID
        ▼
attestation verification
        ▼
trusted key allowlist + parent-complete lineage DAG
        ▼
immutable experiment import

Phase 3 matrix + evaluation_id
  → recompute matrix/candidate/window/train/test identities
  → replay test slice only
  → evaluation.json + checksummed bundle
  → detached signature
  → trusted matrix-bound evaluation registration
  → per-candidate none / partial / complete coverage
```

A signature proves key possession for captured bytes. Lineage records asserted transformation ancestry. Registry trust records a local allowlist decision. None proves original market truth, legal identity, realized profit, future performance, or risk-free returns.

## Git Town Worker State Machine and evidence lanes

Canonical shared method:

[`ed3c/skills-shared/skills/git-town-stacked-pr-worker`](https://github.com/ed3c/skills-shared/tree/main/skills/git-town-stacked-pr-worker)

Repository policy pin:

```text
Git Town:       v24.0.0
Tag commit:     0f3e55f5a6bae5b319dd713a0606263d0551af66
Live admission: false
Owner issue:    #15
```

The repository does not copy the shared Skill. It owns `.git-town.toml`, [`docs/git/REPO_PROFILE.md`](docs/git/REPO_PROFILE.md), task packets, leases, adapters, CI, receipts, branch/PR graph, cleanup and rollback.

Specified Worker flow:

```text
TASK_PROPOSED
  → complete eval-first task packet
  → exact Git Town host admission
  → linked worktree + exclusive branch/path leases
  → clean/ancestry/remote/non-interactive preflight
  → bounded dry-run
      git town sync --stack --dry-run --non-interactive --no-auto-resolve --no-push
  → bounded no-push sync
      git town sync --stack --non-interactive --no-auto-resolve --no-push
  ├── NO_CHANGE / SYNCED
  ├── BLOCKED_DIRTY / PROMPT / CONFLICT / TIMEOUT / POLICY
  └── FAILED_TOOL
  → independent graph/path/protected-ref verification
  → exact-head repository evals + negative controls
  → append-only local receipt
  → trusted GitHub snapshot + one publication intent
  → publication gate ALLOW/BLOCK
  → remote fetch + exact head/ancestry verification
  → GitHub trusted check
  → Human Admit
  → merge
```

Current mechanism states:

| Lane | State | Issue |
| --- | --- | --- |
| Static profile/config/governance | `OPEN_DRAFT` | #13 / PR #23 |
| Host executable/provenance/SBOM/notices/legal receipt | `NOT_EXERCISED` | #15 |
| Typed task packet/path lease | `NOT_IMPLEMENTED` | #16 |
| Linked-worktree/lease doctor | `NOT_IMPLEMENTED` | #17 |
| Bounded no-push sync/receipt writer | `NOT_IMPLEMENTED` | #18 |
| Conflict/prompt/timeout/rollback canaries | `NOT_IMPLEMENTED` | #19 |
| Publication gate/remote verifier | `NOT_IMPLEMENTED` | #20 |
| Live convergence/adoption audit | `NOT_EXERCISED` | #21 |

The active documentation PR ancestry proves the Git object and PR dependency graph after GitHub publication. It does not prove a local admitted Git Town run.

## Historical merged PR index

| Phase | PR | Merge subject | Result |
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
        └── convergence PR / issue #14 / docs/readme-state-flow-index
```

| Slice | PR | Base → head | Path lease | Exact-head eval owner | State |
| --- | --- | --- | --- | --- | --- |
| Agent/integration SSOT | [#22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `main → docs/phase4-integration-ssot` | `AGENTS.md`, integration/state/data-flow docs | PR #22 CI + #12 audits | `OPEN_DRAFT` |
| Git Town governance | [#23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `docs/phase4-integration-ssot → docs/git-town-governance` | `.git-town.toml`, `docs/git/**`, `docs/harness/**`, templates | PR #23 CI + #13 audits | `OPEN_DRAFT` |
| README convergence | assigned after publication | `docs/git-town-governance → docs/readme-state-flow-index` | `README.md`, `docs/git/STACKED_PRS.md` | convergence CI + #14 audits | `OPEN_DRAFT` after PR creation |

Merge order is parent first, followed by retarget and exact-head recheck of each child. Every ready/retarget/merge action is Human Admit. No Agent invokes `git town ship`.

## Planned molecular leaf Stack PRs

These leaves are tracked issues, not available code. Their serial order is a safety dependency chain.

```text
main after documentation convergence
└── infra/git-town-admission                         #15
    └── tooling/git-town-task-packet-validator       #16
        └── tooling/git-town-worktree-doctor         #17
            └── tooling/git-town-bounded-sync        #18
                └── test/git-town-fail-closed-canaries #19
                    └── tooling/git-town-publication-gate #20
                        └── convergence/git-town-adoption-audit #21
```

| Issue | Branch / parent | Molecular owner | Narrow path lease | Required disagreement evidence | State |
| --- | --- | --- | --- | --- | --- |
| [#15](https://github.com/ed3c/llm_arbitrage_system/issues/15) | `infra/git-town-admission ← main` | exact host tool admission | admission doc + admission receipts | wrong version/digest/architecture; missing legal/transitive state | `PLANNED`, blocked on host/legal owner |
| [#16](https://github.com/ed3c/llm_arbitrage_system/issues/16) | `tooling/git-town-task-packet-validator ← #15` | typed packet/path lease | validator/tests/task Harness docs | remove every field; overlap; wrong ancestry; arbitrary shell | `PLANNED` |
| [#17](https://github.com/ed3c/llm_arbitrage_system/issues/17) | `tooling/git-town-worktree-doctor ← #16` | linked worktree/leases | doctor/lease/tests/docs | primary checkout; dirty tree; duplicate/expired/overlap lease; bad remote | `PLANNED` |
| [#18](https://github.com/ed3c/llm_arbitrage_system/issues/18) | `tooling/git-town-bounded-sync ← #17` | dry-run/no-push sync + receipts | fixed sync/receipt adapters/tests/docs | scope mismatch; timeout; prompt; remote movement; out-of-lease diff | `PLANNED` |
| [#19](https://github.com/ed3c/llm_arbitrage_system/issues/19) | `test/git-town-fail-closed-canaries ← #18` | conflict/cleanup/rollback canaries | tests/fixtures/canary docs | planted conflict, prompt, timeout, residue, ref movement, rollback drift | `PLANNED` |
| [#20](https://github.com/ed3c/llm_arbitrage_system/issues/20) | `tooling/git-town-publication-gate ← #19` | one-intent publication and remote verifier | fixed publication/snapshot/remote adapters + CI | stale receipt, old SHA, feedback, billing, wrong remote/head/parent | `PLANNED` |
| [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21) | `convergence/git-town-adoption-audit ← #20` | live convergence audit | convergence docs/receipts | missing evidence lane; `NOT_EXERCISED` promoted to `PASS` | `PLANNED` |

See [`docs/git/STACKED_PRS.md`](docs/git/STACKED_PRS.md) for task-packet detail, rollback subjects, path leases, dependencies, and evidence lanes.

## Install, test, and smoke

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

make check
make phase3-smoke
make phase4-smoke
```

Repository CI runs Ruff, strict Mypy, pytest with coverage, Python 3.10–3.13 compatibility, Phase 3 smoke, and Phase 4 trust/registry smoke.

These commands test the offline repository. They do not prove Git Town admission or a live trading path.

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

`run` refuses silent overwrite. `--force` is explicit and is appropriate only for disposable local evidence.

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

The repository can support claims about:

```text
typed offline inputs
deterministic transformations
paper execution outcomes
causal SQLite records
bundle byte integrity
signature validity
local signer allowlist decisions
asserted lineage ancestry
matrix/evaluation identity binding
registered OOS coverage
```

It cannot support claims about:

```text
source market-data authenticity
legal identity of a signer
live exchange/broker state
account registration or funding
withdrawals
realized trading profit
future performance
risk-free arbitrage
automatic candidate selection
release or production observation
```

Private keys, API secrets, seed phrases, account identifiers, withdrawal authority, browser sessions, credential-bearing URLs, external order endpoints, venue SDKs, network probes, and a live-mode branch are prohibited.

## Human Admit

The following remain human or separately trusted-operator actions:

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
