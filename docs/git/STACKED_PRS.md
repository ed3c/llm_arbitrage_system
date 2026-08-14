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
| CI prerequisite | [#26](https://github.com/ed3c/llm_arbitrage_system/pull/26) | `fix/phase4-ci-baseline` | `989ee49533bfaef1bbbb1b1462dc58cf71897e6f` | `MERGED` |
| Docs 1/3 integration SSOT | [#22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `docs/phase4-integration-ssot` | `8a2b955c594dfbd69895d87adc3c2c5700940cee` | `MERGED` |
| Docs 2/3 Git Town governance | [#23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `docs/git-town-governance` | `60bb43770041fc5e8f0f619ad730034b8bea3462` | `MERGED` |
| Docs 3/3 README/state/index | [#24](https://github.com/ed3c/llm_arbitrage_system/pull/24) | `docs/readme-state-flow-index` | `b0e1e86ea17b801a3149b9001d32d1fb4ec0d4ee` | `MERGED` |
| Phase 5A campaign contracts | [#31](https://github.com/ed3c/llm_arbitrage_system/pull/31) | `feat/phase5-campaign-contracts` | `53b9a8b26e0424beda169ac20673f9d46d6b54b8` | `MERGED` |
| Phase 5B campaign runner | [#32](https://github.com/ed3c/llm_arbitrage_system/pull/32) | `feat/phase5-campaign-runner` | `96d387e2fee59aafc8cb8cff935aad467fba67f3` | `MERGED` |
| Phase 5C campaign operator | [#33](https://github.com/ed3c/llm_arbitrage_system/pull/33) | `feat/phase5-campaign-operator` | `f8fe5f8e0f4033c0870f73f96bf04eac1280f63c` | `MERGED` |
| Phase 6A terminal valuation | [#39](https://github.com/ed3c/llm_arbitrage_system/pull/39) | `feat/phase6-terminal-valuation` | `3af5bb515e7f9e45155678b6762be4314558b608` | `MERGED` |
| Phase 6B OOS statistics | [#40](https://github.com/ed3c/llm_arbitrage_system/pull/40) | `feat/phase6-oos-statistics` | `3d96416701c5c19ead194049eb159e212cfd192d` | `MERGED` |
| Phase 6C valuation operator | [#41](https://github.com/ed3c/llm_arbitrage_system/pull/41) | `feat/phase6-operator` | `00b2fd1dc56e3c90a4ff3c8023fa1b5eaa3b1e74` | `MERGED` |
| Phase 7A selection policy | [#50](https://github.com/ed3c/llm_arbitrage_system/pull/50) | `feat/phase7-policy-contracts` | `ae45c601df237b433b65d3eae359cd0fc4388a21` | `MERGED` |
| Phase 7B selection diagnostics | [#52](https://github.com/ed3c/llm_arbitrage_system/pull/52) | `feat/phase7-diagnostics` | `31e6fc42dd9d6ead64ab5ec21f55397be1e54660` | `MERGED` |
| Phase 7C review dossier | [#53](https://github.com/ed3c/llm_arbitrage_system/pull/53) | `feat/phase7-review-dossier` | `b54013b9eeab4875bb3c3ae320d3ba8a25fc812d` | `MERGED` |
| Phase 8A request contracts | [#59](https://github.com/ed3c/llm_arbitrage_system/pull/59) | `feat/phase8-request-contracts` | `8bb74596187af489b2c695e62be22d9604c918af` | `MERGED` |
| Phase 8B reviewer evidence | [#60](https://github.com/ed3c/llm_arbitrage_system/pull/60) | `feat/phase8-review-evidence` | `d8a5a01181fcfa3c541b2308f1c3eed53b1b0513` | `MERGED` |
| Phase 8C quorum envelope | [#61](https://github.com/ed3c/llm_arbitrage_system/pull/61) | `feat/phase8-quorum-envelope` | `008fb92de69b77539ae9db753c553a80cd754dcd` | `MERGED` |
| GT-02 task-packet validator | [#62](https://github.com/ed3c/llm_arbitrage_system/pull/62) | `tooling/git-town-task-packet-validator` | `955aa12143f802a7a8b2d2b57efee4f90ada085e` | `MERGED` |
| GT-03 worktree/lease doctor | [#63](https://github.com/ed3c/llm_arbitrage_system/pull/63) | `tooling/git-town-worktree-doctor` | `d38428cb389e23681cfe71d346fcd4ee578414e4` | `MERGED` |
| GT-04 bounded no-push sync | [#64](https://github.com/ed3c/llm_arbitrage_system/pull/64) | `tooling/git-town-bounded-sync` | `f230887ed9216b3f608f937c4e74326556adf15f` | `MERGED` |
| GT-05 fail-closed canaries | [#65](https://github.com/ed3c/llm_arbitrage_system/pull/65) | `test/git-town-fail-closed-canaries` | `dab0908bae20ae76ebc7a7d5ea77afe008a64be7` | `MERGED` |
| GT-06 publication gate | [#66](https://github.com/ed3c/llm_arbitrage_system/pull/66) | `tooling/git-town-publication-gate` | `2bcbeae05a9ea43497060d4cb61ad0a437c1bdb5` | `MERGED` |

Every row above merged with a merge commit, not a squash: the stack was serial, and rewriting a parent's commits would have made each child conflict against content it already contained.

## Superseded lane

| Issue / PR | Reason | State |
| --- | --- | --- |
| [#42](https://github.com/ed3c/llm_arbitrage_system/issues/42)–[#45](https://github.com/ed3c/llm_arbitrage_system/issues/45), [PR #51](https://github.com/ed3c/llm_arbitrage_system/pull/51), [PR #54](https://github.com/ed3c/llm_arbitrage_system/pull/54) | A second Phase 7 decomposition. Both lanes added `examples/phase7/selection_policy.yaml`, `src/llm_arbitrage_system/experiments/selection_policy.py` and `tests/test_phase7_selection_policy.py`, producing `CONFLICT (add/add)` on all three, so only one could survive. Issues #34 and #46 already named #50/#52/#53 as the implemented stack, and the whole Phase 8 lane was built on #53. | `SKIPPED_BY_POLICY`, branches retained |

## Documentation stack (merged)

Parent epic: [#11](https://github.com/ed3c/llm_arbitrage_system/issues/11).

```text
main@55ecf0e9a91006f563a080661cb6adf650e2439a
└── PR #22 / issue #12 / docs/phase4-integration-ssot
    └── PR #23 / issue #13 / docs/git-town-governance
        └── PR #24 / issue #14 / docs/readme-state-flow-index
```

| Order | Issue / PR | Base → head | Stack class | Path lease | State |
| --- | --- | --- | --- | --- | --- |
| 1 | [#12](https://github.com/ed3c/llm_arbitrage_system/issues/12) / [PR #22](https://github.com/ed3c/llm_arbitrage_system/pull/22) | `main → docs/phase4-integration-ssot` | foundation | `AGENTS.md`, integration/state/data-flow docs | `MERGED` |
| 2 | [#13](https://github.com/ed3c/llm_arbitrage_system/issues/13) / [PR #23](https://github.com/ed3c/llm_arbitrage_system/pull/23) | `docs/phase4-integration-ssot → docs/git-town-governance` | child | `.git-town.toml`, `docs/git/**`, `docs/harness/**`, templates | `MERGED` |
| 3 | [#14](https://github.com/ed3c/llm_arbitrage_system/issues/14) / [PR #24](https://github.com/ed3c/llm_arbitrage_system/pull/24) | `docs/git-town-governance → docs/readme-state-flow-index` | convergence | `README.md`, this index | `MERGED` |

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
pr: 24
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

## Review and merge sequence (executed)

Every PR above was admitted the same way, one at a time, in dependency order:

```text
1. retarget the PR from its parent branch to main
2. mark it ready for review
3. update its branch from main
4. re-read the head SHA AFTER the update
5. wait for that exact SHA's checks and require every one to succeed
6. confirm the head did not move while the checks ran
7. merge with a merge commit
8. assert the PR reports MERGED before starting the next one
```

Step 4 is the load-bearing one. `update-branch` changes the head, so reading checks immediately afterwards can return the *previous* head's verdict — the same old-SHA-CI trap `scripts/git-town/github_snapshot.py` refuses. Binding every verdict to the SHA it describes is what makes this sequence auditable rather than merely successful.

No Worker marked ready, retargeted, merged, entered a queue, or invoked `git town ship` on its own; each step ran under explicit human authorization.

## Git Town delivery mechanisms

```text
main
└── tooling/git-town-task-packet-validator       #16  MERGED
    └── tooling/git-town-worktree-doctor         #17  MERGED
        └── tooling/git-town-bounded-sync        #18  MERGED
            └── test/git-town-fail-closed-canaries #19  MERGED
                └── tooling/git-town-publication-gate #20  MERGED

infra/git-town-admission                         #15  BLOCKED (never created)
convergence/git-town-adoption-audit              #21  PLANNED
```

Issue #16 named `infra/git-town-admission` as its parent. That branch does not exist: #15 is blocked on a host acquisition method and a named legal/transitive review owner, which are human decisions. The tooling stack therefore parented onto the documentation stack instead, and nothing in it asserts any #15 lane.

| Issue | Molecular owner | Delivered | State |
| --- | --- | --- | --- |
| [#15](https://github.com/ed3c/llm_arbitrage_system/issues/15) | exact Git Town v24.0.0 host admission | `docs/git/GIT_TOWN_ADMISSION.md` records the policy pin and every required lane | `BLOCKED` on host acquisition and named legal/transitive owner |
| [#16](https://github.com/ed3c/llm_arbitrage_system/issues/16) | typed task-packet/path-lease validator | `scripts/git-town/task_packet.py`, `tests/git-town/test_task_packet.py`, `docs/harness/git-town-task-packet.md` | `MERGED` |
| [#17](https://github.com/ed3c/llm_arbitrage_system/issues/17) | linked-worktree and lease doctor | `scripts/git-town/doctor.sh`, `lease.py`, `tests/git-town/test_doctor.py`, `docs/harness/git-town-doctor.md` | `MERGED` |
| [#18](https://github.com/ed3c/llm_arbitrage_system/issues/18) | bounded dry-run/no-push sync and receipts | `scripts/git-town/sync.sh`, `receipt.py`, `tests/git-town/test_sync_contract.py`, `docs/harness/git-town-sync.md` | `MERGED` |
| [#19](https://github.com/ed3c/llm_arbitrage_system/issues/19) | fail-closed conflict/cleanup/rollback canaries | `fixtures/git-town/canary_tool.sh`, `tests/git-town/test_fail_closed_canaries.py`, `docs/harness/git-town-canaries.md` | `MERGED` |
| [#20](https://github.com/ed3c/llm_arbitrage_system/issues/20) | publication gate and remote verifier | `scripts/git-town/publish.sh`, `github_snapshot.py`, `remote_verify.py`, `tests/git-town/test_publication_gate.py`, `docs/git/PUBLICATION.md`, `docs/harness/git-town-publication.md`, CI job | `MERGED` |
| [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21) | live convergence/adoption audit | three defects found only by a real run | sync lane `PASS`, publication lanes `NOT_EXERCISED` |

### What `MERGED` does and does not mean here

Each mechanism above ships with its selftest and its disagreement-producing controls, and the `Git Town delivery mechanisms` CI job runs all of them on every push. That is `mechanism_selftest` and `negative_or_mutation_control` evidence.

It is **not** live-lane evidence. Git Town `v24.0.0` is admitted for `darwin_arm64` by receipt `eda73fcc` (#15), so `scripts/git-town/receipt.py` can now reach the tool on that host — but no mechanism has yet been observed driving a real Git Town run, and any other host still returns `BLOCKED_TOOL_ADMISSION`. The canaries drive `fixtures/git-town/canary_tool.sh`, which reproduces the *conditions* the protocol enumerates, not Git Town's semantics.

`live_canary` therefore remains `NOT_EXERCISED` for every row, and issue #21 owns closing that gap.

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
