# Agent instructions

## Purpose

This repository is a credential-free, paper-only research harness. It implements the market-data → adaptive analytics → strategy routing → central approval → deterministic execution pipeline derived from the supplied *Trading Systems and Methods 資源*, then wraps that data plane with reproducible experiment evidence, signed provenance, dataset lineage, and a trusted local out-of-sample registry.

Do not infer a live-trading capability from names, comments, examples, or the source PDF. The repository contains no exchange or broker adapter, account access, withdrawal path, network probe, or live-mode branch.

## Current truth

The implementation baseline for this documentation stack is:

```text
main@55ecf0e9a91006f563a080661cb6adf650e2439a
```

Merged implementation history:

```text
PR #1   Phase 1  typed contracts and adaptive analytics
PR #3   Phase 2  deterministic offline paper runtime
PR #4   Phase 2B durable SQLite evidence, reports, and CI
PR #6   Phase 3  reproducible content-addressed experiments
PR #10  Phase 4  signed provenance, lineage, and OOS registry
```

Current documentation/Git-governance work is tracked by epic #11. Issues #12–#14 form one serial documentation stack. Issues #15–#21 are planned molecular Git Town adoption leaves; they are not merged implementation.

## Mandatory read order

Before changing any file, read in this order:

1. root `AGENTS.md`;
2. root `README.md`;
3. `docs/integration-status.md`;
4. `docs/state-machines.md` and `docs/data-flow.md`;
5. the domain-specific architecture documents that own the requested path:
   - `docs/architecture.md`;
   - `docs/replay-evidence.md`;
   - `docs/phase3-experiments.md`;
   - `docs/phase4-trust-registry.md`;
6. for branch, worktree, Stack PR, synchronization, or publication work, every file under `docs/git/` and `docs/harness/` that exists on the current branch;
7. the nearest `README.md` for every writable directory;
8. the canonical issue/task packet and its parent issue;
9. the current Git branch/PR graph, exact local and remote heads, and current workflow evidence.

A required document that does not exist is `ABSENT`; do not replace it with assumptions from another repository or from a branch name.

Authority precedence is:

```text
repository policy and merged code
  > canonical issue/task packet
  > shared Skill contract
  > tool defaults
  > conversational summaries
```

When two authorities disagree, stop and report `BLOCKED_POLICY`; name both sources.

## Evidence vocabulary

Use these states exactly and keep them separate:

```text
PASS
FAIL
ABSENT
NOT_IMPLEMENTED
NOT_EXERCISED
SKIPPED_BY_POLICY
```

Repository planning views may additionally use:

```text
MERGED
OPEN
PLANNED
BLOCKED
```

Examples:

- a tracked `.git-town.toml` is not a live Git Town `PASS`;
- an executable on `PATH` is not checksum, provenance, SBOM, notices, or legal-admission `PASS`;
- a successful `git town sync` is not implementation correctness, publication, CI, review, merge, release, or production `PASS`;
- an intentionally suppressed workflow is `SKIPPED_BY_POLICY`, not `PASS`;
- an implemented but unrun canary is `NOT_EXERCISED`;
- a planned issue is not `NOT_IMPLEMENTED` code that may be described as available.

## Directory and State Machine ownership

| Path | Owner | Owned transition | Must not own |
| --- | --- | --- | --- |
| `src/llm_arbitrage_system/domain/` | immutable contracts | typed value creation and validation | I/O, strategy choice, execution |
| `src/llm_arbitrage_system/analytics/` | feature state | `MarketEvent → FeatureSnapshot` after warm-up | plan approval or persistence |
| `src/llm_arbitrage_system/simulation/strategy_router.py` | paper planner | `FeatureSnapshot + MarketEvent → TradePlan | None` | execution or account access |
| `src/llm_arbitrage_system/simulation/approval.py` | paper risk state | `StrategyDecision → RiskEvaluation`, reservation, reconciliation | venue I/O or metric claims |
| `src/llm_arbitrage_system/simulation/executor.py` | deterministic simulator | `ApprovedTradePlan → ExecutionResult` and compensation | network calls or live orders |
| `src/llm_arbitrage_system/simulation/pipeline.py` | orchestration lifecycle | queue admission, cancellation, terminal report | bypassing planner/approver boundaries |
| `src/llm_arbitrage_system/storage/` | replay evidence | append-only run/event/decision/risk/result persistence | strategy selection |
| `src/llm_arbitrage_system/reporting/` | evidence-bounded metrics | stored execution evidence → report | inventing realized PnL, Sharpe, or alpha decay |
| `src/llm_arbitrage_system/experiments/dataset.py` | input contract | source JSONL → validated/canonical dataset identity | source authenticity claims |
| `src/llm_arbitrage_system/experiments/config.py` | behavior contract | source YAML → validated/canonical configuration | secret loading |
| `src/llm_arbitrage_system/experiments/manifest.py` | experiment identity | semantic inputs + revision → experiment/run ID | operational timestamps in identity |
| `src/llm_arbitrage_system/experiments/bundle*.py` | evidence publication | staging → verified atomic bundle | signing-key custody |
| `src/llm_arbitrage_system/experiments/signing.py` | provenance | verified bundle → detached Ed25519 attestation | market-truth or legal-identity claims |
| `src/llm_arbitrage_system/experiments/lineage.py` | lineage DAG | source/derived/slice manifest → lineage ID | accepting an unregistered parent |
| `src/llm_arbitrage_system/experiments/evaluation.py` | OOS binding | matrix item → test-slice-only experiment | training on or selecting from test data |
| `src/llm_arbitrage_system/experiments/registry.py` | local trust registry | trusted key/lineage/bundle/evaluation import | mutating an existing identity |
| `src/llm_arbitrage_system/experiments/aggregation.py` | coverage summary | registered evaluations → coverage/execution summary | automatic winner selection |
| `docs/git/` | repository Git policy | branch graph, profile, task packet, worker evidence rules | portable Skill ownership or merge authority |
| `docs/harness/` | eval contract | assertion/control/evidence routing | arbitrary shell execution |
| `scripts/git-town/` | planned repository adapter | fixed Git/worktree/process operations only | semantic conflict resolution or `ship` |

Detailed transitions live in `docs/state-machines.md`. Cross-layer movement lives in `docs/data-flow.md`.

## Required runtime invariants

- Use timezone-aware timestamps and `Decimal` for prices, notionals, fees, rates, and limits.
- Keep cross-layer domain contracts immutable.
- Reject unknown fields, duplicate JSON/YAML keys, naive timestamps, non-finite values, chronological reversal, and floating-point monetary inputs.
- The runtime is paper-only and performs no external network I/O.
- Strategy code cannot bypass central approval or call the executor directly.
- The bounded pipeline is single-use. A stage failure cancels siblings and marks durable evidence `aborted` when a journal exists.
- Persist evidence in causal order: event before queue admission, decision before approval, risk result before execution admission, execution result before reconciliation.
- Deterministic identifiers derive from semantic evidence, not UUID defaults.
- A bundle is published only after reports persist, SQLite integrity is `ok`, the run is `completed`, and independent bundle verification passes.
- Private provenance keys never enter Git, bundles, registries, journals, tests, logs, or receipts. Generated key files use mode `0600` and refuse silent overwrite.
- A valid signature proves possession of one provenance key for captured bytes. It does not prove market-data truth, legal identity, profitability, or safety.
- Matrix evaluations replay the planned test slice only and must match candidate, configuration, window, train/test hashes, matrix identity, and evaluation ID.
- Registry identities are immutable. Exact duplicates may be idempotent; conflicting bytes fail closed.
- Execution cost, settlement cash flow, and expected edge are not realized strategy PnL. Do not populate drawdown, Sharpe, selection, or alpha-decay fields without their explicit evidence contracts.

## Git Town and Stacked PR work

The canonical portable method is the shared [`git-town-stacked-pr-worker`](https://github.com/ed3c/skills-shared/tree/main/skills/git-town-stacked-pr-worker) Skill. Do not copy that Skill into this repository; a local same-name body would shadow the shared source and is a governance failure.

The repository owns only its profile, `.git-town.toml`, task packets, path leases, wrappers, evals, CI, receipts, branch names, PR bases, and rollback subjects.

Until `docs/git/REPO_PROFILE.md` and `docs/git/GIT_TOWN_ADMISSION.md` exist on the working branch and the required host evidence is `PASS`, live Git Town execution is blocked. Static configuration is not admission.

The intended unattended sync posture is the exact-version-supported equivalent of:

```bash
git town sync --stack --dry-run --non-interactive --no-auto-resolve --no-push
git town sync --stack --non-interactive --no-auto-resolve --no-push
```

Additional laws:

- one Worker owns one linked worktree, one branch lease, and one disjoint writable path set;
- branch creation starts only after an eval-first task packet is valid;
- independent path-disjoint work is sibling work, not an artificial serial stack;
- semantic conflicts stop the Worker and preserve evidence;
- no unattended `continue`, `skip`, `undo`, `ship`, merge, force push, permission change, secret setup, release promotion, or production rollback;
- background synchronization is bounded and no-push;
- publication requires a separately admitted exact-HEAD gate and post-push remote ancestry verification;
- merge order is a Human Admit decision.

## Change procedure

1. Resolve the task packet, branch parent, path lease, required evals, controls, cleanup, rollback subject, and human-owned operations.
2. Confirm the current branch and PR base match the declared graph.
3. Read every owner document for the writable paths.
4. Make only path-leased changes.
5. Run positive evals and disagreement-producing controls on the exact changed subject.
6. Keep local sync, local verification, publication decision, remote publication, remote ancestry, GitHub trusted check, and Human Admit as separate evidence lanes.
7. Update the relevant integration/status and stack index documents in the convergence owner only.

## Commands

```bash
python -m pip install -e ".[dev]"
make check
make phase3-smoke
make phase4-smoke
```

These commands verify repository behavior. They do not prove Git Town admission, a remote publication, or Human Admit.

## Prohibited changes

Do not add exchange or broker credentials, wallet keys, seed phrases, account access, withdrawal functions, external order endpoints, venue SDKs, network probes, or a live-mode branch. Do not weaken validation, CI, overwrite protection, trust checks, exact identity binding, or evidence boundaries.

## Human-owned operations

The following remain human or separately trusted-operator actions:

```text
semantic conflict resolution
git town continue / skip / undo / ship
merge or merge-queue admission
legal or license acceptance
branch protection, permission, billing, or secret changes
release promotion and production deployment
destructive or drifted rollback
```

## Completion report

Every Agent completion report must state independently:

```text
repository and exact subject
issue / task packet
branch / parent / PR base
allowed and changed paths
local sync state
local verification state
publication decision
remote publication state
remote ancestry state
GitHub trusted-check state
cleanup/residue state
rollback subject
remaining ABSENT / NOT_IMPLEMENTED / NOT_EXERCISED / SKIPPED_BY_POLICY
Human Admit required
```
