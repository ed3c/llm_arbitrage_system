# Phase 9 independent offline replication evidence

Phase 9 adds a cross-cohort replication control plane on top of the merged Phase 6–8 evidence chain. It remains deterministic, offline, credential-free, and paper-only.

## Source and extension boundary

The supplied *Trading Systems and Methods 資源* defines the runtime direction:

```text
market data
  → adaptive analytics
  → strategy routing
  → risk approval
  → execution simulation
  → asyncio.Queue orchestration
```

The source does not define independent cross-cohort replication, trusted review-quorum aggregation, release admission, or live deployment. Phase 9 is a repository-owned extension around the existing offline evidence plane. It does not alter the market-data, strategy, risk, simulation, or journal State Machines.

## Directory ownership

| Path | Owner | Input | Output | Failure state |
|---|---|---|---|---|
| `experiments/replication_plan.py` | Replication-plan State Machine | Strict schema-v1 YAML | Content-addressed plan snapshot | Invalid schema, decimal, identity, independence, comparability, acceptance, or authority policy |
| `experiments/replication_inputs.py` | Cohort-input State Machine | Strict schema-v1 JSON manifest | Canonical cohort/path snapshot | Duplicate cohort, unsafe path, missing file, path-role collision, or evidence reuse |
| `experiments/replication.py` | Replication-evaluation State Machine | Plan plus signed Phase 6/7/8 cohort evidence | Content-addressed replication report | Trusted-key, signature, binding, candidate, disjointness, comparability, or threshold failure |
| `experiments/replication_signing.py` | Report-integrity and attestation State Machine | Canonical report plus independent Ed25519 key | Detached report attestation | Noncanonical report, aggregate drift, wrong key, participant signer, signature drift, or authority escalation |
| `experiments/replication_cli.py` | Fixed operator boundary | Declared file arguments | JSON summaries and artifacts | Unsupported command, invalid evidence, existing output, or verification failure |
| `scripts/phase9_smoke.sh` | Deterministic integration evidence | Synthetic signed offline cohorts | Green/failed smoke receipt in CI logs | Any positive or negative control mismatch |

The root `README.md`, `AGENTS.md`, integration SSOT, State-Machine index, data-flow index, and Stack PR ledger remain outside this branch’s path lease. They should be converged only after the Phase 9 stack is admitted.

## State Machines

### SM-9.1 — Replication plan

```text
ABSENT
  → PARSED
  → STRICT_SCHEMA_VALIDATED
  → IDENTITY_AND_THRESHOLD_VALIDATED
  → SAFE_AUTHORITY_VALIDATED
  → CONTENT_ADDRESSED
```

The plan fixes:

- one exact candidate ID and configuration SHA-256;
- minimum cohorts and distinct statistics/dossier/quorum signer counts;
- disjoint candidate test-slice semantic hashes;
- distinct matrix, statistics report, dossier, and quorum-envelope evidence;
- equal code revision, package version, periods per year, and terminal-mark lag;
- exact decimal-string acceptance thresholds;
- `human_admit_required = true`;
- automatic promotion, release, deployment, and trading authorization permanently false.

### SM-9.2 — Cohort input admission

```text
ABSENT
  → JSON_PARSED
  → DUPLICATE_KEYS_REJECTED
  → PATHS_NORMALIZED
  → FILES_PRESENT
  → CROSS_COHORT_REUSE_REJECTED
  → ADMITTED
```

Paths must be normalized relative paths. Evidence and attestation files cannot be reused across cohorts. The manifest carries no credential value, host command, network endpoint, wallet, account, order, release, deployment, or trading instruction.

### SM-9.3 — Trusted cohort evaluation

Each cohort follows this chain:

```text
signed Phase 6 statistics
  → exact trusted statistics key
  → canonical candidate observations
  → signed Phase 7 dossier
  → exact statistics ID/SHA and candidate eligibility
  → signed Phase 8 quorum envelope
  → exact dossier ID/SHA and requested candidate
  → cohort state
```

Cohort states:

```text
replication_insufficient
replication_failed
replication_consistent
```

- `replication_insufficient`: authenticated evidence exists, but approval, window-count, signer, disjointness, distinct-artifact, or comparability requirements are missing.
- `replication_failed`: evidence is sufficient and comparable, but the preregistered evidence threshold is not met.
- `replication_consistent`: the captured signed offline cohort satisfies its local preregistered consistency checks.

### SM-9.4 — Aggregate replication report

```text
ADMITTED_COHORTS
  → SIGNER_DIVERSITY_CHECKED
  → TEST_SLICES_CHECKED_FOR_OVERLAP
  → DISTINCT_ARTIFACTS_CHECKED
  → COMPARABILITY_CHECKED
  → COUNTS_AND_FRACTIONS_COMPUTED
  → WORST_CASE_AND_MEDIAN_COMPUTED
  → FINAL_STATE_CLASSIFIED
  → CONTENT_ADDRESSED
```

Report status priority is fail-closed:

1. independence, comparability, or allowed-insufficient evidence shortfall → `replication_insufficient`;
2. sufficient evidence with unmet acceptance checks → `replication_failed`;
3. all preregistered checks satisfied → `replication_consistent`.

The report always contains:

```text
selection = null
promotion = null
human_admit_required = true
automatic_promotion = false
release_authorized = false
deployment_authorized = false
trading_authorized = false
```

### SM-9.5 — Final report attestation

```text
CANONICAL_REPORT
  → AGGREGATES_RECOMPUTED
  → REPORT_ID_RECOMPUTED
  → PARTICIPANT_KEYS_COLLECTED
  → INDEPENDENT_SIGNER_REQUIRED
  → ED25519_SIGNATURE_WRITTEN
  → TRUSTED_KEY_VERIFIED
```

The final signer key must differ from every cohort statistics, dossier, and quorum signer key. Key separation proves only cryptographic separation of captured evidence; it does not prove legal identity or organizational independence.

## Data flow

```text
replication_plan.yaml
        │
        ▼
load_replication_plan
        │ canonical plan ID/SHA
        │
replication_inputs.json
        │
        ▼
load_replication_inputs
        │ admitted cohort paths
        ▼
┌───────────────────────────────────────────────────────────────┐
│ Cohort N                                                      │
│ signed Phase 6 statistics → signed Phase 7 dossier           │
│       → signed Phase 8 research-review quorum envelope        │
└───────────────────────────────────────────────────────────────┘
        │ repeat with distinct signed evidence
        ▼
build_replication_report
        │
        ├── replication_insufficient
        ├── replication_failed
        └── replication_consistent
        │
        ▼
canonical replication-report-<40 hex>
        │
        ▼
independent Ed25519 signer
        │
        ▼
detached attestation + exact trusted-key verification
```

## Fixed CLI

```bash
llm-arbitrage validate-replication-plan PLAN.yaml
llm-arbitrage validate-replication-inputs INPUTS.json
llm-arbitrage replication-report \
  --plan PLAN.yaml \
  --inputs INPUTS.json \
  --output replication-report.json
llm-arbitrage validate-replication-report replication-report.json
llm-arbitrage sign-replication-report \
  --report replication-report.json \
  --private-key independent-report-private.pem \
  --output replication-report.attestation.json
llm-arbitrage verify-replication-report \
  --report replication-report.json \
  --attestation replication-report.attestation.json \
  --trusted-public-key independent-report-public.pem
```

The operator has no arbitrary-shell passthrough and no winner-selection, candidate-promotion, credential, wallet, deposit, withdrawal, venue, order, release, deployment, or trading command. Non-Phase-9 commands delegate to the existing Phase 8 operator and legacy fixed CLI.

## Failure behavior

Phase 9 fails closed on:

- unknown, missing, duplicate, malformed, floating-point, non-finite, or unsafe plan/input values;
- missing files, absolute paths, parent traversal, or reused evidence/attestations;
- wrong trusted public key, invalid signature, or source/attestation drift;
- statistics ↔ dossier or dossier ↔ quorum mismatch;
- candidate/configuration, matrix, code, package, frequency, or mark-lag drift;
- nonchronological observations or repeated test semantic hashes;
- aggregate count, fraction, worst-case, median, state, or report-ID drift;
- noncanonical JSON;
- existing output without explicit `--force`;
- final signer collision with any cohort statistics/dossier/quorum signer;
- any attempt to enable automatic promotion, release, deployment, or trading authority.

## Evidence boundary

A green Phase 9 path proves one deterministic synthetic or caller-supplied offline path through trusted signed cohort evidence, preregistered replication checks, report signing, and trusted verification. It can show that captured evidence is internally consistent with the declared contract.

It does not prove:

- real cohort sampling independence beyond checked identifiers and test-slice hashes;
- source-market authenticity;
- causal alpha or protection from multiple-testing/model-selection bias outside the declared contract;
- live realized profit or future returns;
- legal identity, organizational independence, or regulatory suitability;
- release readiness, production safety, deployment authority, or live-trading authority.

## Human Admit

Human review remains required for replication-policy acceptance, interpretation, candidate choice, PR-ready transition, parent-first retargeting, semantic conflict resolution, merge/queue admission, Git Town `continue|skip|undo|ship`, legal acceptance, permission changes, release, production, and destructive rollback.
