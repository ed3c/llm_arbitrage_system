# End-to-end data flow

## Purpose and source boundary

The supplied *Trading Systems and Methods 資源* defines, on pages 15–20, a market system that moves data through ingestion/storage, Kaufman/noise analytics, three strategy routes, central risk control, smart execution, and an `asyncio.Queue` producer-consumer loop.

This repository implements that shape as a deterministic offline paper harness. It replaces external venue adapters and live orders with strict JSONL input and simulated paper fills, then adds reproducible evidence, signed provenance, lineage, and a trusted OOS registry.

```text
PDF design plane
external markets → adapters → analytics → strategies → risk → smart execution

Merged repository data plane
strict JSONL → analytics → paper planner → paper approval → deterministic simulator

Merged repository control/evidence plane
configuration + code revision → manifest → SQLite evidence → reports → verified bundle

Merged repository trust plane
verified bundle → Ed25519 attestation → lineage → trusted registry → OOS coverage
```

No arrow in this document represents a live exchange, broker, wallet, deposit, withdrawal, or production trading path.

## 1. Runtime data plane

### Components

```text
src/llm_arbitrage_system/
├── domain/                         immutable wire contracts
├── analytics/                      feature windows and filters
├── simulation/
│   ├── strategy_router.py          paper plan generation
│   ├── approval.py                 risk gates and reservations
│   ├── executor.py                 deterministic fills/compensation
│   ├── pipeline.py                 bounded queues and lifecycle
│   └── protocols.py                typed boundaries
├── storage/sqlite_journal.py       causal replay evidence
└── reporting/performance.py        evidence-bounded metrics
```

### Queue topology

```text
Iterable[MarketEvent]
        │
        │ producer: validate domain object, persist event
        ▼
┌──────────────────────────────┐
│ bounded data_queue           │
│ MarketEvent | sentinel       │
└──────────────┬───────────────┘
               │ analytics loop
               ▼
        AnalyticsEngine
        ├── Kaufman ER
        ├── KAMA
        ├── rolling Z-score
        ├── ATR percentage
        └── Kalman filtered price
               │
               ├── warm-up incomplete → no downstream object
               ▼
        FeatureSnapshot
               │ planner
               ▼
        PaperStrategyRouter
        ├── Funding carry
        ├── Crowding reversion
        └── RWA lead-lag
               │
               ├── no threshold crossed → no downstream object
               ▼
        StrategyDecision
               │ persist decision
               ▼
┌──────────────────────────────┐
│ bounded decision_queue       │
│ StrategyDecision | sentinel  │
└──────────────┬───────────────┘
               │ approval loop
               ▼
        StatefulPaperApprover
        ├── freshness
        ├── expected edge
        ├── per-leg notional
        ├── gross exposure
        ├── duplicate position/reservation
        ├── quantity balance
        └── slippage cap
               │ persist RiskEvaluation
               ├── rejected → rejection counter, no execution admission
               ▼
        ApprovedTradePlan + reservation
               │
               ▼
┌──────────────────────────────┐
│ bounded approved_queue       │
│ ApprovedTradePlan | sentinel │
└──────────────┬───────────────┘
               │ execution loop
               ▼
        DeterministicPaperExecutor
        ├── concurrent leg tasks
        ├── deterministic slippage/fees
        ├── failure injection
        └── reverse confirmed partial fills
               │ persist ExecutionResult
               ▼
        Result reconciliation
        ├── filled → open simulated exposure
        ├── compensated → release reservation
        └── residual → halt new approvals
               │
               ▼
        ReplayReport
        + ResearchPerformanceReport
```

### Backpressure and shutdown

Each queue has a configured maximum size. Producers await queue capacity rather than silently dropping objects. Sentinels close stages in causal order:

```text
data sentinel
  → analytics loop stops and emits decision sentinel
  → approval loop stops and emits approved sentinel
  → execution loop stops
  → reports are built
```

Any task failure:

```text
cancel sibling tasks
  → await cancellation
  → mark journal aborted when available
  → propagate the original error
```

### Causal evidence points

```text
1. record MarketEvent       before data_queue.put
2. record StrategyDecision  before decision_queue.put
3. record RiskEvaluation    before approved_queue.put
4. record ExecutionResult   before result reconciliation
5. persist reports          before completed state
```

This ordering allows an auditor to distinguish a missing downstream transition from an input that was never admitted.

## 2. Strategy-route flow

### Funding carry

```text
perp/RWA-perp MarketEvent
  + funding APY above threshold
  + paper hedge symbol/price metadata
  → quantity-balanced plan
      leg 1: SELL paper perp
      leg 2: BUY paper spot
  → approval gates
  → concurrent deterministic fills
```

### Crowding reversion

```text
FeatureSnapshot
  + abs(Z-score) above threshold
  + Efficiency Ratio below ceiling
  + optional sentiment agreement
  → one paper reversion probe
      positive Z-score → SELL
      negative Z-score → BUY
  → approval gates
  → deterministic fill
```

### RWA lead-lag

```text
RWA-perp MarketEvent
  + reference market explicitly closed
  + reference price present
  + absolute premium above threshold
  → paper convergence plan
      positive premium → SELL
      negative premium → BUY
  → approval gates
  → deterministic fill
```

These routes research the three opportunities described in the source architecture, but they operate only on supplied offline events and paper venues.

## 3. Experiment and evidence plane

### Directory ownership

```text
src/llm_arbitrage_system/experiments/
├── dataset.py              source JSONL validation/canonicalization
├── config.py               source YAML validation/canonicalization
├── canonical.py            stable JSON, Decimal, and datetime encoding
├── strict_yaml.py          duplicate-key rejection
├── manifest.py             content-addressed experiment/run identity
├── determinism.py          evidence-derived plan/leg identifiers
├── runner.py               one experiment composition root
├── bundle.py               staging and atomic publication
├── bundle_io.py            inputs/reports/checksum serialization
├── bundle_validation.py    manifest and source/canonical validation
├── bundle_verify.py        independent bundle verification
├── sweep.py                strict bounded sweep specification
├── walk_forward.py         candidate/window/evaluation planning
└── cli.py                  fixed operator commands
```

### Input compilation

```text
market_events.jsonl                      experiment.yaml
        │                                      │
        ▼                                      ▼
strict JSONL parser                      strict YAML parser
├── duplicate keys                       ├── duplicate keys
├── schema/enum validation               ├── schema/field validation
├── timezone/order validation            ├── Decimal encoding rules
└── monetary float rejection             └── parameter invariants
        │                                      │
        ▼                                      ▼
DatasetSnapshot                         ExperimentConfigSnapshot
├── source bytes/hash                    ├── source bytes/hash
├── canonical JSONL                      ├── canonical JSON
├── semantic hash                        └── canonical hash
└── event hashes
        └───────────────────────┬──────────────┘
                                ▼
                     code revision + package version
                                │
                                ▼
                       ExperimentManifest
                       ├── experiment_id
                       └── run_id
```

### Experiment execution and atomic publication

```text
manifest identity
  → hidden .<experiment_id>.staging/
  → copy raw and canonical inputs
  → create evidence.sqlite3
  → run PaperReplayPipeline with ContentAddressedPlanner
  → require run_status == completed
  → require SQLite integrity == ok
  → checkpoint/truncate WAL
  → write replay_report.json
  → write performance_report.json
  → write report.md
  → write manifest.json
  → write checksums.sha256
  → independently verify staging bundle
  → atomic rename to exp-<identity>/
```

Published bundle:

```text
exp-<semantic-identity>/
├── checksums.sha256
├── evidence.sqlite3
├── manifest.json
├── replay_report.json
├── performance_report.json
├── report.md
└── inputs/
    ├── dataset.source.jsonl
    ├── dataset.canonical.jsonl
    ├── config.source.yaml
    └── config.canonical.json
```

A failed run deletes staging. An existing target is preserved unless the caller explicitly supplies `--force`.

### Independent verification

```text
bundle path
  → reject symlinks and unsafe checksum paths
  → compare exact file set with checksums manifest
  → hash every file
  → recompute manifest experiment identity
  → reparse raw dataset and compare canonical dataset
  → reparse raw configuration and compare canonical configuration
  → verify event count and first/last timestamps
  → SQLite PRAGMA integrity_check
  → require exactly one matching run_id
  → require completed status
  → BundleVerificationResult
```

This proves internal consistency of captured evidence, not authenticity of the original market source.

## 4. Walk-forward planning and OOS execution

### Phase 3 planning

```text
base dataset + base configuration + strict sweep
  → sort parameter names and values canonically
  → reject grid larger than maximum_candidates
  → build rolling or anchored windows
      train [start, end)
      purge [train_end, test_start)
      test  [test_start, test_end)
  → derive candidate configuration hash and candidate_id
  → derive train/test semantic hashes
  → derive evaluation_id
  → matrix.json
```

### Phase 4 execution

```text
matrix.json + evaluation_id
  → strict matrix parsing
  → recompute matrix, candidate, and evaluation identities
  → verify source dataset semantic hash
  → apply planned candidate overrides
  → verify candidate configuration hash
  → verify train/test indexes and semantic hashes
  → materialize only dataset[test_start:test_end]
  → run one content-addressed experiment
  → add evaluation.json
  → rebuild checksums and independently verify
  → signed evaluation bundle
```

The train slice is not replayed by the evaluation runner. Test results do not mutate candidate configuration or choose a winner.

## 5. Signed provenance and lineage flow

### Detached attestation

```text
verified bundle
  + local Ed25519 private key outside repository
  + optional lineage manifest
  → canonical attestation payload
      signer key ID
      embedded public key
      experiment/run IDs
      manifest SHA-256
      checksums-file SHA-256
      bundle-root SHA-256
      optional lineage ID
  → detached signature
  → *.attestation.json outside bundle
```

Verification:

```text
bundle verification
  + strict attestation parsing
  + key-ID/public-key derivation
  + Ed25519 signature verification
  + optional trusted-public-key equality
  + optional lineage-ID equality
  → verified attestation
```

Private provenance keys are local signing secrets, not trading credentials. They never enter evidence bundles, the registry, logs, tests, or receipts.

### Dataset lineage DAG

```text
source lineage manifest
  dataset hash + operation metadata + zero parents
  → lineage_id
  → register source node

derived/slice lineage manifest
  dataset hash + operation metadata + parent lineage IDs
  → require every parent already registered
  → register child node and edges
```

Lineage records the asserted transformation history. It does not independently authenticate a `source_uri`.

## 6. Trusted local registry flow

```text
registry-init
  → SQLite foreign_keys=ON, WAL, synchronous=FULL

public provenance key
  → registry-trust-key
  → trusted_keys

lineage manifest
  → identity/parent validation
  → lineage_nodes + lineage_edges

verified bundle + verified attestation
  → trusted-key lookup by ID and raw public key
  → optional lineage lookup
  → immutable experiments row

matrix-bound evaluation bundle + attestation
  → verify bundle/signature/trust
  → verify matrix/evaluation/candidate/test binding
  → immutable evaluations row
```

Identity behavior:

```text
exact duplicate import          → idempotent already_registered
same identity, changed binding  → conflict rejected
missing lineage parent          → rejected
untrusted key without override  → rejected
explicit untrusted override     → recorded as untrusted, never upgraded implicitly
```

Aggregation:

```text
matrix expected evaluations
  + registry registered evaluations
  → per-candidate none / partial / complete coverage
  → averages of supported execution evidence
  → selection = null
  → realized_pnl = null
  → sharpe_ratio = null
  → alpha_decay = null
```

## 7. Repository delivery and Git Town flow

Canonical portable method:

```text
ed3c/skills-shared/skills/git-town-stacked-pr-worker
```

Repository-owned control files are introduced by issues #12–#14. Live worker adapters and receipts are decomposed into issues #15–#21.

### Intended delivery flow

```text
Issue / eval-first task packet
  ├── goal and non-goals
  ├── base / parent / head
  ├── stack class and dependency graph
  ├── allowed and excluded paths
  ├── branch/path/worktree leases
  ├── required evals and negative controls
  ├── cleanup contract
  ├── evidence boundary
  ├── rollback subject
  └── human-owned operations
        │
        ▼
Task-packet validator                       NOT_IMPLEMENTED (#16)
        │
        ▼
Exact Git Town host admission               NOT_EXERCISED (#15)
        │
        ▼
Linked worktree + branch/path leases        NOT_IMPLEMENTED (#17)
        │
        ▼
Dry-run bounded stack sync                  NOT_IMPLEMENTED (#18)
`--stack --dry-run --non-interactive --no-auto-resolve --no-push`
        │
        ▼
Bounded no-push sync                        NOT_IMPLEMENTED (#18)
        │
        ├── semantic conflict → stop/preserve evidence (#19)
        ▼
Independent ancestry/path verification
+ exact-head evals + controls               NOT_IMPLEMENTED (#18/#19)
        │
        ▼
Publication gate for one intent             NOT_IMPLEMENTED (#20)
        │
        ▼
Remote fetch/head/ancestry verification     NOT_IMPLEMENTED (#20)
        │
        ▼
GitHub trusted check
        │
        ▼
Human Admit → merge                         human-owned
```

### Documentation bootstrap stack

The current documentation work uses actual GitHub branch ancestry and PR bases compatible with a serial stack:

```text
main
└── docs/phase4-integration-ssot
    └── docs/git-town-governance
        └── docs/readme-state-flow-index
```

This proves the Git object/PR dependency graph after publication. It does not claim that a local admitted Git Town executable synchronized the stack; that lane remains `NOT_EXERCISED` until issue #21.

## 8. Directory-to-data contract index

| Directory | Consumes | Produces | Durable output |
| --- | --- | --- | --- |
| `domain/` | constructor fields | validated immutable objects | none |
| `analytics/` | `MarketEvent` stream | `FeatureSnapshot` | none |
| `simulation/` | events, features, plans, approvals | decisions, evaluations, results, replay counters | via journal |
| `storage/` | causal replay objects | persisted rows and reports | SQLite |
| `reporting/` | approved plans and results | evidence-bounded metrics | JSON in journal/bundle |
| `experiments/` Phase 3 | raw dataset/config/revision | identities, bundle, matrix | bundle directory / matrix JSON |
| `experiments/` Phase 4 | bundle, keys, lineage, matrix | attestations, evaluation bundles, registry rows, aggregate | detached JSON / SQLite registry |
| `docs/git/` | shared Skill + repo policy + issue graph | profile, stack plan, worker/publication rules | tracked Markdown/TOML |
| `docs/harness/` | task packet and mechanisms | assertions, controls, evidence requirements | tracked Markdown; receipts planned |
| `scripts/git-town/` | admitted tool + task packet + leases | bounded Git operations and receipts | `NOT_IMPLEMENTED` at baseline |

## 9. Evidence lanes that must remain separate

```text
requirements review
static contract
mechanism selftest
negative or mutation control
live Git Town canary
local exact-head repository evals
publication decision
remote publication
post-push remote ancestry
GitHub trusted check
Human Admit
release / production observation
```

A lower lane never proxies a higher lane. This separation applies equally to trading research: a deterministic replay, verified bundle, signed attestation, and trusted registry entry remain distinct from authentic market data and realized performance.
