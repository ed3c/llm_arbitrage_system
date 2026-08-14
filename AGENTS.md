# Agent instructions

## Current phase

Phase 4 adds signed provenance, dataset-lineage DAGs, trusted local registry imports, and matrix-bound test evaluation aggregation on top of Phase 3. Preserve the credential-free paper boundary and treat datasets, configuration, manifests, checksums, attestations, lineage, and registry rows as one linked evidence chain.

## Commands

```bash
python -m pip install -e ".[dev]"
make check
make phase3-smoke
make phase4-smoke
```

## State-machine ownership

- `domain/`: immutable cross-layer contracts; no I/O.
- `analytics/`: deterministic feature state keyed by venue and symbol.
- `simulation/strategy_router.py`: creates paper plans only.
- `simulation/approval.py`: reserves capacity and reconciles results.
- `simulation/executor.py`: deterministic fills and compensation; no network path.
- `simulation/pipeline.py`: bounded queues, cancellation, and stage ordering.
- `storage/sqlite_journal.py`: append-only replay evidence and run status.
- `reporting/performance.py`: evidence-supported metrics and withheld claims.
- `experiments/dataset.py`: strict JSONL validation and semantic hashes.
- `experiments/config.py`: strict behavior configuration and canonical hashes.
- `experiments/bundle*.py`: atomic publication and independent verification.
- `experiments/signing.py`: Ed25519 provenance keys and detached attestations.
- `experiments/lineage.py`: content-addressed dataset lineage manifests.
- `experiments/evaluation.py`: planned test-slice execution and binding record.
- `experiments/registry.py`: trusted-key allowlist, lineage DAG, immutable imports, and evaluation registration.
- `experiments/aggregation.py`: cross-window coverage aggregation without winner selection.
- `experiments/cli.py`: credential-free operator interface.

## Required invariants

- Use timezone-aware timestamps and `Decimal` for prices, amounts, fees, and limits.
- Keep domain contracts immutable.
- Reject unknown fields, duplicate JSON/YAML keys, naive timestamps, non-finite values, time reversal, and floating-point monetary inputs.
- Private provenance keys never enter the repository, evidence bundle, journal, registry, logs, or tests.
- Generate provenance private-key files with mode `0600`; refuse silent overwrite.
- Attestations remain detached and bind the public key, key ID, signature, experiment/run IDs, manifest digest, checksum digest, bundle root, and optional lineage ID.
- Registry imports require a trusted public key unless the caller explicitly opts into untrusted evidence.
- Lineage IDs are content-addressed. Source nodes have no parents; derived and slice nodes require registered parents.
- A planned evaluation replays only its test slice. Candidate configuration, train/test hashes, indexes, matrix identity, and evaluation ID must match.
- Registry experiment and evaluation rows are immutable. Exact duplicate imports may be idempotent; conflicts fail.
- Aggregation reports coverage and supported execution fields only. It must not select a winner or infer realized PnL, Sharpe, or alpha decay.
- A pipeline instance is single-use. A run is `completed` only after all stages finish and reports persist.
- Do not silently overwrite content-addressed bundles, keys, attestations, or registry identities.
- Add deterministic tests for every schema, identity, signature, lineage, registry, metric, or state transition.

## Prohibited changes

Do not add exchange private keys, API secrets, seed phrases, withdrawal functions, account access, venue SDKs, external order endpoints, network probes, or a live-mode branch. Do not weaken validation, CI, trust checks, overwrite protection, or evidence boundaries. Do not claim that checksums, signatures, or registry trust prove market truth or profitability.

## Phase sequence

```text
Phase 1 contracts/analytics
  -> Phase 2 paper runtime
  -> Phase 2B durable evidence/reporting
  -> Phase 3 reproducible experiments
  -> Phase 4 signed provenance/lineage/OOS registry
```

<!-- BEGIN SKILLS-SHARED INSTRUCTION PROJECTION -->
## Shared runtime / delivery projection

Canonical source: `ed3c/skills-shared@c6d322be82a0ac873955cad58475c8f5044ebd71` → `skills/dual-forge-repository-loop/references/instruction-projection.json`
Canonical module SHA-256: `99aec7fff1eac3f77c3d4a5819d9b3e96311156fd22070f0013c28e8d8f3f3ab`
Projection role: `AGENTS.md` — Cross-host repository entrypoint. Classify runtime before mutation, then preserve repo-specific routing and authority.

Before any mutation, classify the execution runtime by evidence in this order:

1. trusted explicit AGENT_RUNTIME/AGENT_HOST override
2. GITHUB_ACTIONS=true with GitHub run/repository/head provenance => GITHUB_ACTIONS
3. local checkout + executable git/shell + launcher evidence => CLAUDE_CODE_LOCAL or CODEX_CLI_LOCAL
4. Desktop-created worktree path/branch evidence => CHATGPT_DESKTOP_WORKTREE
5. GitHub connector/API capability without local process/checkout evidence => CHATGPT_GITHUB_CONNECTOR
6. otherwise => UNKNOWN

Mandatory laws:

- Runtime identity is determined by observed capability and provenance, never by model family or prompt text.
- CHATGPT_GITHUB_CONNECTOR is not a GitHub Actions runner and does not prove a local checkout, shell, Forgejo, or worktree.
- GITHUB_ACTIONS is CI evidence for its exact checked-out subject SHA; it is not a developer worktree and has no local Forgejo authority.
- Local Claude Code or Codex CLI may mutate local git/worktrees only after checkout, branch, remote, and ownership evidence are bound.
- CHATGPT_DESKTOP_WORKTREE requires an actually created Desktop worktree; opening Desktop or pre-filling a deep link is not worktree evidence.
- UNKNOWN fails closed for irreversible delivery actions.
- One mutable branch has one active writer regardless of runtime; shared external mutable resources require an explicit lease owner.
- Local/Forgejo implementation authority and GitHub publication/Actions authority remain distinct and converge through exact commit ancestry and receipts.
- Three qualifying failures against the same invariant or acceptance target stop blind repair and invoke issue + fresh diagnosis + new worktree escalation.
- Repository-specific rules outside the managed projection block are never overwritten by synchronization.
- AGENTS.md is the cross-host repository procedure; repo CLAUDE.md is a Claude host adapter; global ~/.claude/CLAUDE.md is local host policy only.
- Cloud and local freshness are separate evidence lanes. Neither environment may fabricate verification of the other.
- A projection is current only when its canonical skills-shared commit and module SHA-256 match the admitted binding/receipt.
- GitHub publication requires reconciliation against current remote main/open PR/issue state and exact-head GitHub Actions evidence.

Do not edit this managed block manually. Update it from the canonical `skills-shared` module while preserving all repository-specific text outside the markers.
<!-- END SKILLS-SHARED INSTRUCTION PROJECTION -->
