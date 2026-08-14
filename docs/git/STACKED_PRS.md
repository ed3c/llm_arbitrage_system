# Stacked PR and traceability index

## Evidence and delivery states

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

Git Town branch lineage, GitHub PR bases, path leases and exact-head evidence must agree. One does not proxy another.

## Merged implementation history

| Phase | PR | Branch | Merge subject | State |
| --- | --- | --- | --- | --- |
| Phase 1 contracts/analytics | [#1](https://github.com/ed3c/llm_arbitrage_system/pull/1) | `feat/pdf-architecture-v2` | `0e8ceec3456ad2c74fa77237d3b814520f0213fc` | `MERGED` |
| Phase 2 paper runtime | [#3](https://github.com/ed3c/llm_arbitrage_system/pull/3) | `feat/research-harness-phase2` | `1a255ad865ce346816bc04ef8680d80477c32cc7` | `MERGED` |
| Phase 2B evidence/reporting | [#4](https://github.com/ed3c/llm_arbitrage_system/pull/4) | `feat/replay-evidence-phase2b` | `215ca9c7c81bea456a4e358a9d750a7157a9872b` | `MERGED` |
| Phase 3 experiments | [#6](https://github.com/ed3c/llm_arbitrage_system/pull/6) | `feat/reproducible-experiments-phase3` | `e201e4b012e1596a7c470309cd2af792e009ee17` | `MERGED` |
| Phase 4 trust/OOS registry | [#10](https://github.com/ed3c/llm_arbitrage_system/pull/10) | `feat/signed-provenance-phase4-v3` | `55ecf0e9a91006f563a080661cb6adf650e2439a` | `MERGED` |

## Active documentation stack

Parent epic: [#11](https://github.com/ed3c/llm_arbitrage_system/issues/11).

```text
main@55ecf0e9a91006f563a080661cb6adf650e2439a
└── PR #22 / issue #12 / docs/phase4-integration-ssot
    └── PR #23 / issue #13 / docs/git-town-governance
        └── convergence PR / issue #14 / docs/readme-state-flow-index
```

| Order | Issue / PR | Base → head | Stack class | Path lease | State |
| --- | --- | --- | --- | --- | --- |
| 1 | [#12](https://github.com/ed3c/llm_arbitrage_system/issues/12) / [PR #22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `main → docs/phase4-integration-ssot` | foundation | `AGENTS.md`, integration/state/data-flow docs | `OPEN_DRAFT` |
| 2 | [#13](https://github.com/ed3c/llm_arbitrage_system/issues/13) / [PR #23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `docs/phase4-integration-ssot → docs/git-town-governance` | child | `.git-town.toml`, `docs/git/**`, `docs/harness/**`, templates | `OPEN_DRAFT` |
| 3 | [#14](https://github.com/ed3c/llm_arbitrage_system/issues/14) / PR assigned after publication | `docs/git-town-governance → docs/readme-state-flow-index` | convergence | `README.md`, this index | `OPEN_DRAFT` after publication |

### Slice #12 packet summary

```yaml
branch: docs/phase4-integration-ssot
parent: main
base: main
required_evals:
  - make check
  - repository-tree-reference-audit
  - merged-open-planned-lineage-audit
  - Agent-read-order-audit
negative_controls:
  - missing referenced path
  - planned mechanism described as merged
  - removed evidence vocabulary
rollback_subject: main@55ecf0e9a91006f563a080661cb6adf650e2439a
live_git_town_sync: NOT_EXERCISED
human_admit: required
```

### Slice #13 packet summary

```yaml
branch: docs/git-town-governance
parent: docs/phase4-integration-ssot
base: docs/phase4-integration-ssot
required_evals:
  - make check
  - git-town-config-static-audit
  - repository-profile-completeness-audit
  - canonical-shared-Skill-ownership-audit
  - task-packet-and-template-audit
negative_controls:
  - unresolved required profile field
  - push or auto-resolve enabled
  - local Skill shadow copy
  - tool presence used as legal/provenance proof
rollback_subject: docs/phase4-integration-ssot@3e4b1f455518a3813be0251cb1d8c1c1879cd9e9
live_git_town_sync: NOT_EXERCISED
human_admit: required
```

### Slice #14 packet summary

```yaml
branch: docs/readme-state-flow-index
parent: docs/git-town-governance
base: docs/git-town-governance
required_evals:
  - make check
  - README-path-link-audit
  - directory-to-State-Machine-audit
  - stack-ancestry-and-PR-base-audit
  - historical-PR-phase-audit
negative_controls:
  - absent module path
  - wrong PR base
  - collapsed merged-open-planned state
  - future leaf missing owner-dependency-path-eval-state
rollback_subject: docs/git-town-governance@225ad8b3d803add97d57628ab90e722b185632c6
live_git_town_sync: NOT_EXERCISED
human_admit: required
```

## Review and merge sequence

All three PRs stay Draft while reviewed as one stack. After explicit Human Admit and current exact-head gates:

```text
1. admit PR #22 into main
2. retarget PR #23 to main and rerun every required check on its new exact head/base
3. admit PR #23
4. retarget convergence PR to main and rerun every required check
5. admit convergence PR
```

No Worker marks ready, retargets, merges, enters a queue, or invokes `git town ship` automatically.

## Planned molecular Git Town stack

These issues are implementation contracts, not available code. Branches are created only after task-packet validation, exact tool admission and path leasing.

```text
main after docs convergence
└── infra/git-town-admission                         #15
    └── tooling/git-town-task-packet-validator       #16
        └── tooling/git-town-worktree-doctor         #17
            └── tooling/git-town-bounded-sync        #18
                └── test/git-town-fail-closed-canaries #19
                    └── tooling/git-town-publication-gate #20
                        └── convergence/git-town-adoption-audit #21
```

| Issue | Parent/dependencies | Molecular owner | Allowed-path summary | Required assertion and disagreement evidence | State |
| --- | --- | --- | --- | --- | --- |
| [#15](https://github.com/ed3c/llm_arbitrage_system/issues/15) | docs convergence | exact Git Town v24.0.0 host admission | admission doc + admission receipts | exact artifact/version/license/provenance/SBOM/notices/legal; wrong digest/version/architecture controls | `PLANNED`, blocked on host/legal owners |
| [#16](https://github.com/ed3c/llm_arbitrage_system/issues/16) | #15 | typed task-packet/path-lease validator | validator/tests/task Harness docs | every required field; removal/overlap/wrong-parent/arbitrary-shell controls | `PLANNED` |
| [#17](https://github.com/ed3c/llm_arbitrage_system/issues/17) | #16 | linked-worktree and lease doctor | doctor/lease/tests/docs | isolated worktree/exclusive lease; primary/dirty/duplicate/expired/bad-remote controls | `PLANNED` |
| [#18](https://github.com/ed3c/llm_arbitrage_system/issues/18) | #15–#17 | bounded dry-run/no-push sync and receipts | fixed sync/receipt adapters/tests/docs | dry-run scope, timeout, no-push, graph/path/exact-head checks; prompt/remote movement controls | `PLANNED` |
| [#19](https://github.com/ed3c/llm_arbitrage_system/issues/19) | #18 | fail-closed conflict/cleanup/rollback canaries | canary tests/fixtures/docs | planted conflict/prompt/timeout/residue/ref-movement/rollback-drift | `PLANNED` |
| [#20](https://github.com/ed3c/llm_arbitrage_system/issues/20) | #18–#19 | publication gate and remote verifier | publication/snapshot/remote adapters/tests/CI/docs | one intent, exact head, remote ancestry; stale/old-SHA/feedback/billing/wrong-remote controls | `PLANNED` |
| [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21) | #15–#20 | live convergence/adoption audit | convergence docs/receipts | all evidence lanes; missing-lane and false-PASS controls | `PLANNED` |

## Safety dependency rationale

```text
exact tool before live Worker
  → valid packet before branch/path mutation
  → isolated worktree and leases before sync
  → bounded no-push sync before local verification
  → fail-closed canaries before trust in the mechanism
  → exact local evidence before publication
  → remote verification and trusted checks before Human Admit
  → convergence audit before an adoption claim
```

Independent runtime features must use sibling branches with disjoint path leases instead of nesting under this delivery-governance chain.

## Required PR traceability fields

Every future PR records:

```text
issue/parent issue and packet digest
branch/parent/base and stack class
child PRs and parallel-safe siblings
allowed/excluded paths and lease receipt
exact before/after commit and tree subjects
positive evals and negative/mutation controls
local sync state
local exact-head verification state
publication decision
remote publication
post-push remote head/ancestry
GitHub trusted check
cleanup/residue
rollback subject and drift check
remaining ABSENT / NOT_IMPLEMENTED / NOT_EXERCISED / SKIPPED_BY_POLICY
Human Admit state
```
