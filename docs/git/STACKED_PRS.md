# Stacked PR and traceability index

## State vocabulary

```text
MERGED
OPEN_DRAFT
OPEN_READY
PLANNED
BLOCKED
NOT_IMPLEMENTED
NOT_EXERCISED
SKIPPED_BY_POLICY
```

This index records dependency, branch parent, PR base, path lease, eval owner, evidence state, cleanup and rollback. Git Town lineage does not replace GitHub PR lineage; both must agree.

## Historical merged implementation

| Phase | PR | Branch | Base at review | Merge subject | State |
| --- | --- | --- | --- | --- | --- |
| Phase 1 contracts/analytics | [#1](https://github.com/ed3c/llm_arbitrage_system/pull/1) | `feat/pdf-architecture-v2` | `main` | `0e8ceec3456ad2c74fa77237d3b814520f0213fc` | `MERGED` |
| Phase 2 paper runtime | [#3](https://github.com/ed3c/llm_arbitrage_system/pull/3) | `feat/research-harness-phase2` | `main` after Phase 1 | `1a255ad865ce346816bc04ef8680d80477c32cc7` | `MERGED` |
| Phase 2B evidence/reporting | [#4](https://github.com/ed3c/llm_arbitrage_system/pull/4) | `feat/replay-evidence-phase2b` | `main` after Phase 2 | `215ca9c7c81bea456a4e358a9d750a7157a9872b` | `MERGED` |
| Phase 3 experiments | [#6](https://github.com/ed3c/llm_arbitrage_system/pull/6) | `feat/reproducible-experiments-phase3` | `main` after Phase 2B | `e201e4b012e1596a7c470309cd2af792e009ee17` | `MERGED` |
| Phase 4 trust/registry | [#10](https://github.com/ed3c/llm_arbitrage_system/pull/10) | `feat/signed-provenance-phase4-v3` | `main` after Phase 3 | `55ecf0e9a91006f563a080661cb6adf650e2439a` | `MERGED` |

Historical merge subjects prove ancestry on `main`; they do not automatically prove current CI, current dependency versions, or live trading.

## Active documentation stack

Parent epic: [#11](https://github.com/ed3c/llm_arbitrage_system/issues/11).

```text
main@55ecf0e9a91006f563a080661cb6adf650e2439a
└── docs/phase4-integration-ssot          issue #12 / PR #22
    └── docs/git-town-governance          issue #13 / PR created after this commit
        └── docs/readme-state-flow-index  issue #14 / convergence PR follows
```

### Slice 1 — Agent and integration SSOT

```yaml
issue: 12
pr: 22
branch: docs/phase4-integration-ssot
parent: main
pr_base: main
stack_class: foundation
path_lease:
  - AGENTS.md
  - docs/integration-status.md
  - docs/state-machines.md
  - docs/data-flow.md
state: OPEN_DRAFT
required_evals:
  - make check
  - repository-tree-reference-audit
  - merged-open-planned-lineage-audit
  - Agent-read-order-audit
live_git_town_sync: NOT_EXERCISED
rollback_subject: main@55ecf0e9a91006f563a080661cb6adf650e2439a
human_admit: required
```

### Slice 2 — Git Town governance

```yaml
issue: 13
pr: assigned after branch publication
branch: docs/git-town-governance
parent: docs/phase4-integration-ssot
pr_base: docs/phase4-integration-ssot
stack_class: child
path_lease:
  - .git-town.toml
  - docs/git/**
  - docs/harness/**
  - .github/ISSUE_TEMPLATE/stacked-pr-worker.md
  - .github/PULL_REQUEST_TEMPLATE.md
state: OPEN_DRAFT_after_PR_creation
required_evals:
  - make check
  - git-town-config-static-audit
  - repo-profile-placeholder-audit
  - task-packet-required-field-audit
  - PR-template-stack-contract-audit
live_git_town_sync: NOT_EXERCISED
rollback_subject: exact parent head at branch creation
human_admit: required
```

### Slice 3 — README convergence

```yaml
issue: 14
pr: assigned after branch publication
branch: docs/readme-state-flow-index
parent: docs/git-town-governance
pr_base: docs/git-town-governance
stack_class: convergence
path_lease:
  - README.md
  - docs/git/STACKED_PRS.md
state: PLANNED_until_branch_publication
required_evals:
  - make check
  - README-path-link-audit
  - directory-to-State-Machine-audit
  - stack-ancestry-and-PR-base-audit
  - historical-PR-phase-audit
live_git_town_sync: NOT_EXERCISED
rollback_subject: exact parent head at branch creation
human_admit: required
```

## Merge order

After all Draft PRs are reviewed together and exact-head gates are green:

```text
1. Human Admit PR #22 into main
2. retarget/recheck Slice 2 onto main, then Human Admit
3. retarget/recheck Slice 3 onto main, then Human Admit
```

No Agent may mark a PR ready, retarget it, merge it, enter a merge queue, or invoke `git town ship` without explicit Human Admit.

## Planned molecular Git Town implementation stack

These are future issues, not current implementation. Branches are not created until their task packet, exact tool admission and path lease are valid.

```text
main after docs convergence
└── infra/git-town-admission                    #15
    └── tooling/git-town-task-packet-validator  #16
        └── tooling/git-town-worktree-doctor    #17
            └── tooling/git-town-bounded-sync   #18
                └── test/git-town-fail-closed-canaries #19
                    └── tooling/git-town-publication-gate #20
                        └── convergence/git-town-adoption-audit #21
```

| Issue | Leaf owner | Dependencies | Path lease summary | Required evidence/control | State |
| --- | --- | --- | --- | --- | --- |
| [#15](https://github.com/ed3c/llm_arbitrage_system/issues/15) | exact tool admission | docs governance | admission doc + admission receipts | artifact/version/license/provenance/SBOM/notices/legal; wrong artifact/version mutations | `PLANNED`, host/legal owner required |
| [#16](https://github.com/ed3c/llm_arbitrage_system/issues/16) | task packet and path lease | #15 | typed validator + tests + task-packet Harness | remove each required field; overlap; ancestry mismatch; arbitrary shell rejection | `PLANNED` |
| [#17](https://github.com/ed3c/llm_arbitrage_system/issues/17) | worktree and lease doctor | #16 | doctor/lease scripts + tests | primary checkout, dirty tree, duplicate/overlap/expired lease, remote identity controls | `PLANNED` |
| [#18](https://github.com/ed3c/llm_arbitrage_system/issues/18) | bounded no-push sync/receipts | #15–#17 | sync/receipt adapters + tests | dry-run scope match, timeout, graph/path verification, exact-head eval replay | `PLANNED` |
| [#19](https://github.com/ed3c/llm_arbitrage_system/issues/19) | fail-closed canaries | #18 | fixture repos, canary tests, Harness doc | semantic conflict, prompt, timeout, residue, ref movement, rollback drift | `PLANNED` |
| [#20](https://github.com/ed3c/llm_arbitrage_system/issues/20) | publication gate | #18–#19 | typed snapshot/gate/remote verifier + CI | stale receipt, old-SHA CI, repeated feedback, billing, wrong remote, head mismatch | `PLANNED` |
| [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21) | convergence/live audit | #15–#20 | convergence docs + receipts | all evidence lanes separate; first live no-push and publication canaries | `PLANNED` |

## Why the future stack is serial

The leaves form a safety dependency chain, not merely a feature list:

```text
no live Worker without exact tool admission
no owned worktree without a valid task packet
no sync without a worktree/lease doctor
no confidence in sync without fail-closed canaries
no publication without verified local evidence
no adoption claim without convergence/live audit
```

Independent future runtime work must use sibling branches with disjoint path leases rather than nesting under this Git-governance chain.

## Traceability fields required for every future PR

```text
issue and parent issue
branch, parent branch and PR base
stack class and child PRs
allowed/excluded paths
branch/path/worktree leases
exact before/after subjects
required evals and negative controls
local sync state
local verification state
publication decision
remote publication state
remote ancestry state
GitHub trusted-check state
cleanup and residue
rollback subject
Human Admit state
remaining ABSENT / NOT_IMPLEMENTED / NOT_EXERCISED / SKIPPED_BY_POLICY
```
