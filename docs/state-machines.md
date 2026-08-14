# State Machines and module ownership

## Purpose

This document maps repository directories to the State Machines they own. A State Machine owner is the only layer allowed to decide the named transition. Adjacent modules exchange immutable contracts; they do not silently mutate another layer's state.

Status baseline:

```text
main@2bcbeae05a9ea43497060d4cb61ad0a437c1bdb5
```

SM-01 through SM-13 and SM-15 through SM-18 are merged behavior. SM-14, the Git delivery machine, has merged adapters and controls but no live lane: its transitions have never been driven by a real Git Town executable.

## Cross-layer contract graph

```text
MarketEvent
  │ analytics.process
  ▼
FeatureSnapshot
  │ planner.plan
  ▼
TradePlan
  │ compose
  ▼
StrategyDecision
  │ approver.approve
  ├─────────────► RiskEvaluation(rejected)
  ▼
ApprovedTradePlan
  │ executor.execute
  ▼
ExecutionResult
  │ reconciler + journal
  ▼
ReplayReport + ResearchPerformanceReport
  │ bundle publisher
  ▼
Verified evidence bundle
  │ signer / lineage / registry
  ▼
Attestation + lineage node + experiment/evaluation registration
  │ campaign runner (SM-15)
  ▼
Registered campaign evaluations
  │ terminal marks + valuation (SM-16)
  ▼
Signed OOS statistics report
  │ preregistered policy + diagnostics (SM-17)
  ▼
Signed human-review dossier
  │ decision request + reviewer quorum (SM-18)
  ▼
Research-only review quorum envelope
```

The graph is directional. Strategy planning cannot call execution; execution cannot approve itself; reporting cannot change stored evidence; signing cannot change bundle bytes; aggregation cannot choose a candidate; diagnostics cannot select; and a sealed review envelope cannot authorize deployment, trading or release.

Machine index:

```text
SM-01 … SM-07   runtime, evidence and reporting
SM-08 … SM-13   experiments, provenance, lineage, trusted registry
SM-14           Git Town Worker delivery
SM-15 … SM-18   campaigns, valuation, selection governance, separation of duties
```

## SM-01 — Analytics feature state

Owner:

```text
src/llm_arbitrage_system/analytics/engine.py
src/llm_arbitrage_system/analytics/{kaufman,kalman,zscore,volatility}.py
```

Keyed state:

```text
venue:symbol → price/high/low windows + KalmanFilter1D
```

| State | Input | Transition owner | Output | Failure / no-output behavior |
| --- | --- | --- | --- | --- |
| `UNSEEN` | first valid `MarketEvent` | `AnalyticsEngine._state` | initialized series state | invalid domain event is rejected before this layer |
| `WARMING` | valid ordered events below required window | `AnalyticsEngine.process` | `None` | no strategy call is allowed |
| `READY` | event count reaches `max(efficiency_period + 1, zscore_window)` | `AnalyticsEngine.process` | `FeatureSnapshot` | indicator validation errors propagate and abort the replay |
| `ADVANCING` | subsequent events | `AnalyticsEngine.process` | one new `FeatureSnapshot` per event | state remains isolated by venue and symbol |

Owned calculations:

```text
Kaufman Efficiency Ratio
Kaufman Adaptive Moving Average
rolling Z-score
ATR percentage
one-dimensional Kalman-filtered price
```

Persistence: in-memory for one pipeline instance. Durable evidence begins at the replay journal, not inside the analytics state.

## SM-02 — Strategy planning

Owner:

```text
src/llm_arbitrage_system/simulation/strategy_router.py
src/llm_arbitrage_system/experiments/determinism.py
```

| State | Guard | Output | Position key |
| --- | --- | --- | --- |
| `NO_PLAN` | no route crosses its research threshold | `None` | none |
| `FUNDING_CARRY_PLANNED` | perp/RWA perp, APY threshold crossed, paper hedge metadata present | short paper perp + long paper spot | `funding:<symbol>` |
| `CROWDING_REVERSION_PLANNED` | absolute Z-score high, efficiency ratio low, optional sentiment agreement | one paper reversion leg | `crowding:<symbol>` |
| `LEAD_LAG_PLANNED` | RWA perp, reference market closed, reference price present, premium threshold crossed | one paper convergence leg | `lead-lag:<symbol>` |
| `CONTENT_ADDRESSED` | a plan exists inside a Phase 3/4 experiment | deterministic plan and client-order IDs replace random defaults | derived from dataset, event/features, sequence, and plan semantics |

The router returns the first matching route in its configured order. It creates paper plans only. Venue SDKs, balances, credentials, and network calls are outside this machine.

## SM-03 — Approval, reservation, and portfolio state

Owner:

```text
src/llm_arbitrage_system/simulation/approval.py
```

### Approval transition

```text
StrategyDecision
  → evaluate gates
      ├── any reason → REJECTED
      └── all pass   → RESERVED / APPROVED
```

Gates:

```text
runtime halt
market-event age / future timestamp
minimum expected edge
maximum per-leg notional
existing position key
existing reservation
projected gross exposure
multi-leg quantity balance
maximum slippage cap
```

| State | Stored state | Allowed next transition |
| --- | --- | --- |
| `AVAILABLE` | no matching reservation or open position | `REJECTED` or `RESERVED` |
| `REJECTED` | reasons only; no capacity mutation | terminal for this decision |
| `RESERVED` | `plan_id → (position_key, gross_notional)` | execution result reconciliation |
| `OPEN` | filled notional stored by position key | duplicate entry rejected |
| `RELEASED` | reservation removed after compensated/non-residual terminal result | future position may be approved |
| `RESIDUAL_OPEN` | unmatched simulated notional stored under `residual:<plan_id>` | `HALTED` |
| `HALTED` | halt reason set | all new approvals rejected until explicit reconciliation acknowledgement |

### Result reconciliation

| `ExecutionStatus` | Approval-state action |
| --- | --- |
| `FILLED` | remove reservation; add open exposure for the position key |
| `COMPENSATED` | remove reservation; do not add open exposure |
| `FAILED` with no residual | remove reservation |
| `PARTIALLY_FILLED` or failed compensation with residual | record residual exposure and halt new approvals |

`acknowledge_reconciliation` clears simulated residual keys and the halt reason. That method is an explicit operator/testing action; it is not proof of real-market reconciliation.

## SM-04 — Deterministic multi-leg execution

Owner:

```text
src/llm_arbitrage_system/simulation/executor.py
```

```text
ApprovedTradePlan
  → schedule every paper leg concurrently
  → gather outcomes
      ├── all fills      → FILLED
      ├── no fills       → FAILED
      └── some fills     → reverse each confirmed fill
                              ├── reversals represented → COMPENSATED
                              └── residual in another executor implementation → PARTIALLY_FILLED
```

| State | Evidence | Terminal result |
| --- | --- | --- |
| `PENDING` | approved plan | none |
| `EXECUTING` | one async task per leg | none |
| `FILLED` | deterministic paper fills for every leg | `ExecutionStatus.FILLED` |
| `FAILED` | exceptions and zero confirmed fills | `ExecutionStatus.FAILED` |
| `COMPENSATING` | at least one confirmed fill plus at least one failed leg | reverse paper fills |
| `COMPENSATED` | every confirmed fill has a reverse fill | `ExecutionStatus.COMPENSATED` |

Fill prices derive from configured deterministic slippage; fees derive from configured deterministic fee basis points. Order IDs derive from the plan ID and leg index. No external acknowledgement or venue state exists.

## SM-05 — Replay pipeline lifecycle

Owner:

```text
src/llm_arbitrage_system/simulation/pipeline.py
```

Queue ownership:

```text
producer        owns data_queue admission
analytics loop  owns decision_queue admission
approval loop   owns approved_queue admission
execution loop  owns terminal result collection
```

Lifecycle:

```text
NEW
  → start_run (when journal exists)
  → RUNNING
      ├── producer → analytics/planning → approval → execution
      ├── sentinel drains each downstream stage in order
      └── all tasks complete
  → REPORTING
  → COMPLETED
```

Failure lifecycle:

```text
any task raises
  → cancel sibling tasks
  → await cancellation results
  → journal.abort_run(error)
  → ABORTED
  → re-raise original error
```

| Pipeline state | Invariant |
| --- | --- |
| `NEW` | `_started` is false; queues are empty |
| `RUNNING` | exactly one call to `run`; bounded queues enforce backpressure |
| `DRAINING` | sentinels propagate data → decision → approval queues |
| `REPORTING` | replay counters and performance report are built after all tasks finish |
| `COMPLETED` | journal has both reports and terminal completed state |
| `ABORTED` | sibling tasks were cancelled and durable status records the error when possible |
| `REUSE_REJECTED` | a second `run` call raises because the pipeline is single-use |

## SM-06 — SQLite replay evidence

Owner:

```text
src/llm_arbitrage_system/storage/sqlite_journal.py
```

Database controls:

```text
foreign_keys = ON
journal_mode = WAL
synchronous = FULL
stable sorted JSON
Decimal encoded as exact strings
timezone-aware ISO-8601 timestamps
```

Run state:

```text
ABSENT
  → start_run
RUNNING
  ├── append market_events
  ├── append strategy_decisions
  ├── append risk_evaluations
  ├── append execution_results
  ├── complete_run(replay_report, performance_report) → COMPLETED
  └── abort_run(error)                                → ABORTED
```

Only a row currently in `running` can become `completed`. Completion occurs after the replay and performance reports are available. `PRAGMA integrity_check` is a separate verification lane, not a state mutation.

Causal persistence order:

```text
MarketEvent persisted before data_queue admission
StrategyDecision persisted before approval
RiskEvaluation persisted before approved_queue admission
ExecutionResult persisted before approver reconciliation
```

## SM-07 — Performance evidence

Owner:

```text
src/llm_arbitrage_system/reporting/performance.py
```

| Evidence available | Fields allowed | Fields withheld |
| --- | --- | --- |
| approved plans + execution results | counts, rates, turnover, fees, settlement cash flow, expected edge, execution cost, edge after cost | realized PnL, drawdown, Sharpe, alpha decay |
| plus realized PnL series + positive initial equity | maximum drawdown | Sharpe without frequency; alpha decay |
| plus observation frequency | annualized Sharpe when statistically computable | alpha decay |
| repeated reviewed OOS windows with a separate policy | not implemented in this reporter | alpha decay remains unset here |

The reporter has no transition that converts settlement cash flow into realized profit.

## SM-08 — Dataset and configuration compilation

Owners:

```text
src/llm_arbitrage_system/experiments/dataset.py
src/llm_arbitrage_system/experiments/config.py
src/llm_arbitrage_system/experiments/canonical.py
src/llm_arbitrage_system/experiments/strict_yaml.py
```

```text
SOURCE_BYTES
  → UTF-8 / duplicate-key / schema validation
  → TYPED_INPUT
  → canonical JSON/JSONL
  → source SHA-256 + semantic/canonical SHA-256
  → VALIDATED_SNAPSHOT
```

Fail-closed inputs include unknown fields, missing fields, duplicate keys, blank JSONL records, BOM, unsupported enums, naive timestamps, chronological reversal, non-finite values, and floats in monetary fields.

Raw-source hashes preserve byte provenance. Semantic hashes intentionally ignore irrelevant source formatting and mapping order.

## SM-09 — Experiment identity and bundle publication

Owners:

```text
experiments/manifest.py
experiments/runner.py
experiments/bundle.py
experiments/bundle_io.py
experiments/bundle_validation.py
experiments/bundle_verify.py
```

Experiment identity:

```text
bundle schema version
+ dataset semantic SHA-256
+ configuration canonical SHA-256
+ code revision
+ package version
  → experiment_id / run_id
```

Bundle state:

```text
IDENTIFIED
  → prepare hidden staging directory
STAGING
  → write source/canonical inputs
  → run deterministic replay into evidence.sqlite3
  → checkpoint WAL
  → write manifest/reports/Markdown
  → write checksums
VERIFYING
  ├── exact file set
  ├── SHA-256 values
  ├── manifest identity
  ├── raw/canonical linkage
  ├── event metadata
  ├── SQLite integrity
  ├── one matching run_id
  └── completed status
VERIFIED
  → atomic rename staging → exp-<identity>
PUBLISHED
```

Any error removes staging and publishes nothing. Existing target bundles are not overwritten without explicit `--force`.

## SM-10 — Walk-forward matrix planning

Owners:

```text
experiments/sweep.py
experiments/walk_forward.py
```

```text
strict sweep YAML
  → bounded deterministic parameter grid
  × rolling/anchored train-purge-test windows
  → candidate IDs + evaluation IDs
  → matrix.json
```

Window invariant:

```text
0 ≤ train_start < train_end ≤ test_start < test_end ≤ event_count
purge_size = test_start - train_end
```

Matrix creation plans evaluations; it does not train a model, execute test windows, rank candidates, or prove alpha decay.

## SM-11 — Signed provenance and lineage

Owners:

```text
experiments/signing.py
experiments/lineage.py
```

### Attestation

```text
VERIFIED_BUNDLE
  → derive manifest/checksum/root digests
  → sign canonical payload with local Ed25519 private key
  → DETACHED_ATTESTATION
  → verify signature + embedded key + optional trusted key + optional lineage
  → VERIFIED_ATTESTATION
```

Private keys remain outside the repository and evidence bundle. A signature binds captured bytes and signer-key possession; it does not authenticate original market data or legal identity.

### Lineage

```text
source manifest (zero parents)
  → content-addressed source node

derived/slice manifest (one or more parent IDs)
  → validate every parent reference
  → content-addressed child node
```

The registry requires parent nodes before child import. The lineage ID binds dataset hash, kind, operation name/version/parameters, parents, source URI, and notes.

## SM-12 — Matrix-bound OOS evaluation

Owner:

```text
experiments/evaluation.py
```

```text
MATRIX_ITEM
  → recompute matrix/evaluation/candidate identities
  → verify source dataset and base configuration
  → derive candidate configuration
  → verify train/test slice hashes and indexes
  → replay test slice only
  → write evaluation.json into checksummed bundle
  → VERIFIED_EVALUATION_BUNDLE
```

The train slice remains planning evidence. The evaluator has no transition that selects a candidate based on the test result.

## SM-13 — Trusted registry and aggregation

Owners:

```text
experiments/registry.py
experiments/aggregation.py
```

Registry states:

```text
REGISTRY_INITIALIZED
  ├── public key → TRUSTED_KEY
  ├── parent-complete lineage manifest → LINEAGE_REGISTERED
  ├── verified signed bundle → EXPERIMENT_REGISTERED
  └── matrix-bound signed evaluation → EVALUATION_REGISTERED
```

Default import policy requires a trusted public key. An explicit untrusted override may record untrusted evidence without upgrading it to trusted.

Identity rows are immutable:

```text
exact repeat → IDEMPOTENT_ALREADY_REGISTERED
same identity, different bytes/binding → CONFLICT_REJECTED
```

Aggregation states per candidate:

| Coverage | Meaning |
| --- | --- |
| `none` | no planned evaluation is registered |
| `partial` | some but not all planned evaluations are registered |
| `complete` | every planned evaluation is registered |

Aggregation may summarize supported execution fields. Candidate selection, realized PnL, Sharpe, and alpha decay remain `null`.

## SM-14 — Git Town Worker delivery state

Policy owners when present:

```text
shared skills-shared/git-town-stacked-pr-worker  portable method
docs/git/                                     repository profile and governance
docs/harness/                                 eval/control contract
scripts/git-town/                             fixed repository adapters
receipts/git-town/                            append-only evidence
```

Current implementation state at the baseline:

```text
tracked policy/configuration: MERGED (#12-#14)
host admission receipt:       NOT_EXERCISED (#15)
task-packet validator:        MERGED mechanism (#16)
worktree/lease doctor:        MERGED mechanism (#17)
bounded sync/receipts:        MERGED mechanism (#18)
fail-closed canaries:         MERGED mechanism (#19)
publication gate:             MERGED mechanism (#20)
live Git Town synchronization: NOT_EXERCISED (#15, #21)
live adoption audit:          NOT_EXERCISED (#21)
```

Specified transition graph:

```text
TASK_PROPOSED
  → task-packet validation
TASK_ADMITTED
  → exact tool admission + linked worktree + branch/path leases
WORKER_ADMITTED
  → dry-run, bounded no-push stack sync
  ├── NO_CHANGE / SYNCED
  ├── BLOCKED_DIRTY / BLOCKED_PROMPT / BLOCKED_CONFLICT / BLOCKED_TIMEOUT
  └── FAILED_TOOL
  → independent ancestry/path verification
  → exact-head evals + negative controls
LOCAL_VERIFIED
  → trusted GitHub snapshot + publication gate intent
  ├── BLOCKED_POLICY / billing-open
  └── ALLOW one operation
  → remote fetch/head/ancestry verification
REMOTE_VERIFIED
  → GitHub trusted check
  → HUMAN_ADMIT
  → merge
```

A successful local sync never skips local verification, publication admission, remote verification, CI, or Human Admit.

Mechanism state as of `main@2bcbeae`: the adapters in `scripts/git-town/` exist and their controls pass in CI, but no transition above has ever been driven by a real Git Town executable. `HOST_GIT_TOWN_BIN` is unresolved, so `run_sync` returns `BLOCKED_TOOL_ADMISSION` before reaching `LOCAL_SYNCED`.

## SM-15 — Campaign execution and durable recovery

Owners:

```text
experiments/campaign.py
experiments/campaign_store.py
experiments/campaign_runner.py
```

```text
CAMPAIGN_DECLARED
  → content-addressed manifest bound to matrix, policy, code revision, signer
CAMPAIGN_REGISTERED
  ├── bounded batch of planned evaluations → EVALUATION_RUNNING
  ├── interruption → recovered from the durable journal, never restarted blind
  └── failure policy exceeded → CAMPAIGN_STOPPED
EVALUATION_COMPLETED
  → detached signature + trusted registry registration
CAMPAIGN_TERMINAL
```

Terminal evidence is immutable. Re-running an already registered evaluation reuses the existing trusted evidence instead of producing a second identity. Selection, realized PnL, Sharpe and alpha decay stay unset.

## SM-16 — Terminal marks and OOS valuation

Owners:

```text
experiments/valuation.py
experiments/oos_statistics.py
```

```text
MARKS_DECLARED
  → strict Decimal prices, one timezone-aware as_of, exact open-position coverage
MARKS_ADMITTED
  ├── missing position coverage → BLOCKED
  └── float-encoded money → BLOCKED
BUNDLE_VALUED
  → chronological ordering across the campaign
OOS_STATISTICS_REPORTED
  → signed statistical report
```

A mark is an observation, not a realizable price. The report never asserts that a valued position could have been closed at that mark.

## SM-17 — Preregistered selection governance

Owners:

```text
experiments/selection_policy.py
experiments/selection_diagnostics.py
experiments/selection_dossier.py
experiments/selection_signing.py
```

```text
POLICY_PREREGISTERED
  → content-addressed identity bound to an exact matrix family
CANDIDATES_DIAGNOSED
  ├── cross-window stability
  └── Holm family multiple-testing correction
DOSSIER_BUILT
  → signed, immutable, human-review-only
HUMAN_REVIEW_PENDING
```

The machine has no `SELECTED` state. It diagnoses and presents; a human decides. A policy registered after seeing the diagnostics is not preregistered, and the content-addressed identity is what makes that checkable.

## SM-18 — Separation of duties for a research decision

Owners:

```text
experiments/decision_request.py
experiments/review_evidence.py
experiments/review_quorum.py
```

```text
REQUEST_ISSUED
  → exact signed-dossier reference, fixed proposer role, time bound
REVIEWS_COLLECTED
  → each an independently signed record from a distinct reviewer identity
QUORUM_EVALUATED
  ├── insufficient distinct reviewers → BLOCKED
  └── quorum met → ENVELOPE_SEALED
```

`ENVELOPE_SEALED` is research-only, and the machine fails closed in both directions:

- an incoming request that sets `deployment_authorized` or `trading_authorized` is **rejected**, not silently downgraded (`decision_request.py` raises `cannot authorize deployment` / `cannot authorize trading`);
- a request must carry a null `decision`, so the request cannot pre-decide its own outcome;
- the emitted quorum envelope reports `deployment_authorized`, `trading_authorized` and `release_authorized` as `false`.

There is no transition anywhere in this machine that sets an authorization flag true. Promotion is a human act outside the repository.

## Forbidden cross-machine shortcuts

```text
analytics → execution
strategy → direct approval bypass
approval → venue/network I/O
executor → account or wallet access
journal → strategy mutation
reporter → unsupported metric fabrication
bundle signer → private-key persistence in evidence
lineage child → missing parent import
matrix planner → automatic winner selection
Git Town Worker → semantic conflict resolution or merge/ship
local PASS → remote/CI/Human Admit PASS by implication
```
