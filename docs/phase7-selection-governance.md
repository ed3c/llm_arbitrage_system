# Phase 7: Research Selection Governance

Phase 7 adds a fail-closed research-governance plane above the Phase 6 terminal
valuation and chronological out-of-sample evidence path.

It does **not** add live trading, candidate auto-selection, model promotion,
release authority, or deployment authority.

## Scope

Phase 7 binds three pre-existing evidence objects:

```text
Phase 3 matrix family
  → Phase 6 canonical OOS statistics report
  → Phase 7 preregistered selection policy
  → Phase 7 stability and multiple-testing diagnostics
  → Phase 7 immutable human-review dossier
  → detached Ed25519 attestation
```

The output is a review packet. It is not a winner, strategy recommendation, or
production decision.

## Directory ownership

```text
examples/phase7/
└── selection_policy.yaml
    └── example preregistered schema-v1 policy

src/llm_arbitrage_system/experiments/
├── selection_policy.py
│   └── strict policy parsing, semantic identity, and admission declarations
├── selection_diagnostics.py
│   └── candidate stability, exact sign tests, Holm adjustment, and blockers
├── selection_dossier.py
│   └── cross-evidence binding and immutable human-review dossier
├── selection_signing.py
│   └── detached Ed25519 dossier attestation and trusted-key verification
└── cli.py
    └── fixed credential-free Phase 7 operator commands

tests/
├── test_phase7_selection_policy.py
├── test_phase7_selection_diagnostics.py
└── test_phase7_cli.py

scripts/
└── phase7_smoke.sh
    └── deterministic positive and negative end-to-end controls
```

README, AGENTS.md, and the repository-wide integration index are intentionally
not modified in this stack. Those paths remain leased to the existing
repository-documentation stack and require separate convergence after Human
Admit.

## State machine

### SM-7.1: Policy compilation

```text
YAML source
  → strict duplicate-key parsing
  → exact field-set validation
  → matrix digest validation
  → human_review_only admission
  → Decimal-string threshold parsing
  → canonical semantic payload
  → selection-policy-<40 hex>
```

Terminal states:

```text
compiled
rejected_duplicate_key
rejected_unknown_field
rejected_non_decimal_threshold
rejected_invalid_range
rejected_invalid_matrix_digest
rejected_non_human_decision_mode
```

The policy does not name or allowlist candidates. This prevents a policy from
being silently tailored to an already observed candidate ID.

### SM-7.2: Family diagnostics

```text
canonical Phase 6 report
  + compiled policy
  → exact matrix binding
  → deep candidate and observation validation
  → PnL/equity accounting checks
  → window comparability checks
  → candidate stability diagnostics
  → pairwise exact sign tests
  → Holm family adjustment
  → explicit blockers
  → selection-diagnostics-<40 hex>
```

Candidate terminal states:

```text
eligible_for_human_review
blocked
```

Family terminal states:

```text
eligible_for_human_review
blocked
```

`eligible_for_human_review` means only that captured evidence satisfies the
preregistered structural contract. It does not mean selected, approved,
profitable, safe, or deployable.

### SM-7.3: Dossier construction

```text
compiled policy
  + canonical Phase 6 report
  + canonical Phase 7 diagnostics
  → policy ID/hash check
  → statistics ID/hash check
  → diagnostics ID/hash check
  → matrix family check
  → candidate partition extraction
  → immutable review packet
  → selection-dossier-<40 hex>
```

The dossier always contains:

```json
{
  "human_decision": null,
  "selected_candidate_id": null,
  "promotion": null
}
```

A future human decision must be stored as a separate authorized evidence object.
The immutable dossier must not be rewritten to create the appearance that an
earlier automated run made a human decision.

### SM-7.4: Detached dossier attestation

```text
canonical dossier
  + Ed25519 private provenance key
  → exact dossier identity
  → canonical signing payload
  → detached signature
  → attestation JSON outside source evidence
```

Verification checks:

```text
canonical dossier encoding
content-addressed dossier ID
exact dossier SHA-256
matrix SHA-256
policy ID and hash
statistics report ID and hash
diagnostics ID and hash
family state
eligible/blocked candidate counts
code revision
package version
embedded public key
signer key ID
optional trusted public-key equality
Ed25519 signature
null decision fields
```

The private key is not stored in the dossier or attestation.

## Policy contract

Schema-v1 fixes the primary metric to:

```text
total_mark_to_market_pnl_usd
```

with direction:

```text
maximize
```

This does not authorize automatic ranking. It only declares the measurement
whose evidence may be reviewed by a human.

Supported tie-breaker declarations are:

```text
maximum_drawdown_pct
annualized_sharpe_ratio
alpha_decay_bps_per_window
positive_window_fraction
worst_window_pnl_usd
```

Phase 7 stores candidate diagnostics in lexical `candidate_id` order rather than
performance order.

## Stability diagnostics

For each candidate, Phase 7 records:

```text
window count
total terminal mark-to-market PnL
positive-window fraction
worst-window PnL
median-window PnL
leave-one-window-out total-PnL range
maximum drawdown
annualized Sharpe when available
alpha-decay magnitude when available
terminal-mark lag
policy blockers
```

The leave-one-window-out range is a sensitivity diagnostic. It is not a
bootstrap confidence interval and must not be described as one.

## Multiple-testing diagnostics

Schema-v1 uses:

```text
exact two-sided sign test
+ Holm family adjustment
```

The sign test compares matching OOS terminal-window PnL values and ignores ties.
Holm adjustment applies to the exact candidate family captured by the report.

These diagnostics do not remove all model-selection risk. They do not establish
causal alpha, market-data authenticity, or future profitability.

## CLI

```bash
llm-arbitrage validate-selection-policy selection_policy.yaml

llm-arbitrage selection-diagnostics \
  --policy selection_policy.yaml \
  --statistics statistics.json \
  --output diagnostics.json \
  --code-revision "$(git rev-parse HEAD)"

llm-arbitrage build-selection-dossier \
  --policy selection_policy.yaml \
  --statistics statistics.json \
  --diagnostics diagnostics.json \
  --output dossier.json \
  --code-revision "$(git rev-parse HEAD)"

llm-arbitrage sign-selection-dossier \
  --dossier dossier.json \
  --private-key provenance.pem \
  --output dossier.attestation.json

llm-arbitrage verify-selection-dossier \
  --dossier dossier.json \
  --attestation dossier.attestation.json \
  --trusted-public-key provenance.pub.pem
```

All output-producing commands reject silent overwrite unless `--force` is
provided explicitly.

## Data flow

```text
Selection policy YAML
        │
        ▼
Strict policy compiler
        │
        ├── matrix identity
        ├── admission thresholds
        └── multiple-testing contract
        │
        ▼
Canonical Phase 6 OOS report
        │
        ▼
Selection diagnostics
        │
        ├── comparability guards
        ├── stability metrics
        ├── exact sign tests
        ├── Holm adjustment
        └── blockers
        │
        ▼
Immutable review dossier
        │
        ├── exact source IDs and hashes
        ├── eligible candidate IDs
        ├── blocked candidate IDs
        └── null human decision
        │
        ▼
Detached Ed25519 attestation
        │
        ▼
Human review boundary
```

## Failure and negative controls

Phase 7 fails closed on:

```text
duplicate YAML or JSON keys
unknown or missing fields
noncanonical diagnostics or dossier JSON
non-finite values
invalid identifiers or digests
policy/report/diagnostics matrix mismatch
policy ID or hash drift
statistics report ID or hash drift
diagnostics ID or hash drift
candidate partition overlap
non-lexical or duplicate candidate IDs
non-null selection/ranking/promotion fields
non-null human decision
wrong trusted public key
invalid signature
tampered dossier
silent output overwrite
```

## CI smoke contract

`scripts/phase7_smoke.sh` constructs a deterministic family with two candidates
and three comparable windows, then executes:

```text
validate policy
  → build diagnostics
  → build dossier
  → generate provenance key
  → sign dossier
  → verify with trusted public key
  → assert null decision fields
  → assert lexical candidate IDs
  → reject overwrite
  → reject wrong key
  → reject tampered dossier
  → remove generated evidence
```

## Evidence boundary

Phase 7 can establish that:

```text
a policy was captured before review
a canonical report was bound to that policy
candidate evidence met or failed declared structural gates
pairwise sign-test evidence was adjusted for the captured family
an immutable dossier was signed by one provenance key
```

Phase 7 cannot establish that:

```text
terminal marks came from an authentic market source
the model discovered causal alpha
the strategy will remain profitable
a candidate is legally or operationally approved
live execution is safe
release or production promotion is authorized
```

## Human Admit boundary

Only an authorized human may perform:

```text
statistical-method acceptance
selection-policy approval
candidate decision authoring
PR ready transition
parent-first retargeting
merge or merge queue
git town continue / skip / undo / ship
permission changes
legal approval
release promotion
production deployment
destructive rollback
```
