# Phase 8: Research-only separation of duties

Phase 8 extends the signed Phase 7 review dossier with explicit request,
independent reviewer, and quorum evidence. It never authorizes release,
deployment, credentials, withdrawals, or live trading.

## Directory ownership

```text
examples/phase8/
├── review_request.yaml       strict research-review request example
├── reviewer_record.yaml      independent reviewer-record example
└── review_quorum.yaml        signed-evidence input manifest example

src/llm_arbitrage_system/experiments/
├── decision_request.py           request schema, canonical identity, expiry
├── decision_request_signing.py   detached proposer attestation
├── review_evidence.py            independent reviewer record and attestation
├── review_quorum.py              quorum verification and immutable envelope
├── review_quorum_signing.py      detached envelope attestation
└── operator_cli.py               fixed Phase 8 commands; legacy CLI delegation

scripts/phase8_smoke.sh           deterministic end-to-end positive/negative path
tests/test_phase8_*.py            contracts, signer separation, tamper controls
```

README and AGENTS.md are not changed here because those paths remain leased to
the existing documentation stack.

## State machines

### SM-8.1 Request

```text
YAML request
  → exact field set
  → signed dossier ID/hash reference
  → explicit human-supplied candidate
  → research_review_only scope
  → aware request/expiry interval
  → complete risk acknowledgements
  → null decision and false authorization flags
  → decision-request-<40 hex>
```

### SM-8.2 Independent review

```text
signed dossier + signed request + external review record
  → trusted dossier/request key checks
  → candidate eligible and not blocked
  → review authored inside request lifetime
  → reviewer subject differs from proposer subject
  → reviewer key differs from proposer and dossier keys
  → approve_research_only | defer | reject
  → review-record-<40 hex>
  → detached reviewer attestation
```

### SM-8.3 Quorum

```text
signed request
  + signed dossier
  + independently signed reviews
  → unique review IDs
  → unique reviewer subjects
  → unique reviewer keys
  → deterministic veto/hold/quorum rule
  → review-quorum-<40 hex>
```

Terminal states:

```text
rejected                     any reject is a veto
deferred                     no reject, at least one defer
approved_for_research_only   all approve and distinct-key minimum is met
blocked                      insufficient all-approve quorum
```

Every state preserves:

```json
{
  "deployment_authorized": false,
  "trading_authorized": false,
  "release_authorized": false
}
```

### SM-8.4 Envelope attestation

```text
canonical quorum envelope
  + provenance key distinct from every participant key
  → exact envelope identity
  → detached Ed25519 signature
  → trusted-key verification
```

## Data flow

```text
Phase 7 immutable dossier
        │
        ├── detached dossier attestation
        ▼
Human-authored review request
        │
        ├── detached proposer attestation
        ▼
Independent reviewer records
        │
        ├── exact request/dossier/candidate binding
        ├── distinct subjects
        ├── distinct signer keys
        └── detached reviewer attestations
        ▼
Quorum input manifest
        │
        ├── verify every trusted signature
        ├── reject duplicate records/subjects/keys
        ├── apply veto/hold/quorum rule
        └── keep all operational authorizations false
        ▼
Immutable quorum envelope
        │
        └── independent detached attestation
        ▼
Human Admit boundary
```

## Fixed CLI

```bash
llm-arbitrage validate-decision-request request.yaml
llm-arbitrage sign-decision-request --request request.yaml --private-key proposer.pem --output request.attestation.json
llm-arbitrage verify-decision-request --request request.yaml --attestation request.attestation.json --trusted-public-key proposer.pub.pem

llm-arbitrage validate-review-record review.yaml
llm-arbitrage sign-review-record ...
llm-arbitrage verify-review-record ...

llm-arbitrage validate-review-quorum-inputs quorum.yaml
llm-arbitrage build-review-quorum --inputs quorum.yaml --output quorum.json
llm-arbitrage validate-review-quorum quorum.json
llm-arbitrage sign-review-quorum --envelope quorum.json --private-key quorum.pem --output quorum.attestation.json
llm-arbitrage verify-review-quorum --envelope quorum.json --attestation quorum.attestation.json --trusted-public-key quorum.pub.pem
```

The Phase 8 wrapper delegates all older commands to the existing Phase 3–7 CLI.
It exposes no arbitrary shell, winner selection, deployment, or trading command.

## Failure controls

Phase 8 fails closed on duplicate or unknown fields, malformed IDs and digests,
missing acknowledgements, unsafe scope, expired requests, ineligible candidates,
reviewer/requester subject collision, signer-key collision, duplicate reviews,
duplicate reviewer subjects or keys, wrong trusted keys, noncanonical envelopes,
identity drift, tampering, and silent output overwrite.

## Evidence boundary

Phase 8 can establish internal binding and cryptographic separation between one
request, one dossier, multiple reviewer records, and one quorum envelope. Key
separation alone does not prove legal identity or organizational independence.
The system does not establish market-data truth, causal alpha, future profit,
legal approval, release readiness, deployment safety, or live-trading safety.

## Human Admit

Candidate-for-review authoring, rationale, reviewer assignment, reviewer
decisions, quorum-policy acceptance, PR ready, parent-first retargeting, merge or
merge queue, Git Town continue/skip/undo/ship, permissions, legal approval,
release, production, and destructive rollback remain human-owned.
