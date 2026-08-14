# Phase 5 — Resumable trusted experiment campaigns

Phase 5 turns one Phase 3 walk-forward matrix into a bounded local campaign over the Phase 4 test-evaluation, signing, and trusted-registry contracts. It remains offline and paper-only.

## Source and extension boundary

The supplied design describes the market-data, adaptive analytics, strategy routing, risk, execution, and backtest/reporting data plane. Campaign scheduling, durable orchestration, detached signing, and trusted evaluation registration are repository control-plane extensions around that data plane.

## Directory ownership

```text
src/llm_arbitrage_system/experiments/
├── campaign.py          strict YAML, selection, and campaign identity
├── campaign_store.py    durable campaign/evaluation state journal
└── campaign_runner.py   bounded execution, signing, registry reconciliation,
                         aggregation, and resumable operator state

examples/phase5/
└── campaign.yaml        permissive all-evaluation example

scripts/
└── phase5_smoke.sh      fixed, credential-free local/CI verification path
```

## Campaign state machine

```text
campaign YAML + matrix + dataset/config + signer + code revision
  -> strict validation
  -> deterministic evaluation selection
  -> content-addressed CampaignManifest
  -> workspace identity and input-drift checks
  -> SQLite campaign initialization
  -> interrupted running rows recovered to pending
  -> trusted registry reconciliation
  -> bounded evaluation batches
  -> Phase 4 test-slice replay
  -> detached Ed25519 attestation
  -> trusted matrix-bound registry registration
  -> cross-window aggregate
  -> completed | partial | failed | aborted
```

Campaign transitions:

```text
planned
  -> running
  -> completed   all selected evaluations are registered or safely skipped
  -> partial     at least one evaluation failed, no evaluation remains pending
  -> failed      the failure policy stopped with unattempted or failed rows
  -> aborted     an orchestration-level exception escaped the bounded loop
```

Evaluation transitions:

```text
pending
  -> running
  -> registered
  -> skipped_existing
  -> failed

interrupted running
  -> pending
```

`registered` and `skipped_existing` are immutable evidence states. An exact duplicate may be replayed idempotently; conflicting experiment, signer, lineage, matrix, or evaluation evidence fails closed.

## Content identity

The campaign identity binds:

```text
matrix semantic SHA-256
dataset semantic SHA-256
base configuration SHA-256
canonical campaign policy SHA-256
ordered selected evaluation-set SHA-256
code revision
package version
Ed25519 signer key ID
optional lineage ID
```

Operational timestamps, absolute workspace paths, SQLite WAL state, and retry timing do not enter the semantic campaign identity.

## Workspace

```text
campaign-<identity>/
├── manifest.json
├── campaign.sqlite3
├── aggregate.json
├── report.json
├── inputs/
│   ├── campaign.source.yaml
│   ├── campaign.canonical.json
│   └── matrix.canonical.json
├── evaluations/
│   └── exp-*/
└── attestations/
    └── evaluation-*.attestation.json
```

The private provenance key and trusted experiment registry must stay outside this workspace. The runner rejects either path when it is located inside the campaign directory.

## Operator commands

```bash
llm-arbitrage validate-campaign examples/phase5/campaign.yaml

llm-arbitrage run-campaign \
  --dataset examples/phase3/market_events.jsonl \
  --config examples/phase3/experiment.yaml \
  --matrix experiment-runs/matrix.json \
  --campaign examples/phase5/campaign.yaml \
  --registry state/experiments.registry.sqlite3 \
  --private-key /secure/provenance.pem \
  --output experiment-runs/campaigns \
  --code-revision "$(git rev-parse HEAD)"

llm-arbitrage campaign-status \
  experiment-runs/campaigns/campaign-<identity>
```

`--retry-failed` explicitly admits failed rows for another attempt. Interrupted `running` rows are recovered automatically. Existing trusted registry evidence may be skipped only when signer and lineage match the campaign identity.

## Failure policy

```yaml
execution:
  maximum_parallel_evaluations: 2
  maximum_failures: 2
  stop_on_failure: false
```

The runner executes complete bounded batches. Once the policy stops the campaign, unattempted rows remain `pending`; they are not reported as completed or silently dropped.

## Evidence and claim boundary

A completed campaign proves that the selected deterministic test evaluations were present in the trusted local registry under the declared signer and matrix contract. It does not prove:

- source-market authenticity;
- legal signer identity;
- live execution capability;
- realized or future profitability;
- winner selection;
- Sharpe ratio;
- realized PnL;
- alpha decay;
- release or production readiness.

`report.json` therefore leaves `selection`, `realized_pnl`, `sharpe_ratio`, and `alpha_decay` as `null`.

## Verification

```bash
make check
make phase3-smoke
make phase4-smoke
make phase5-smoke
```

The Phase 5 smoke path creates only synthetic local keys and deterministic paper evidence, verifies two matrix-bound test slices, checks trusted registry integrity, inspects withheld claims, and removes its generated workspace.
