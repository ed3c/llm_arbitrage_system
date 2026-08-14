# Git and Stacked-PR governance

## Ownership

This directory is the repository-owned projection of the shared [`git-town-stacked-pr-worker`](https://github.com/ed3c/skills-shared/tree/main/skills/git-town-stacked-pr-worker) method.

Ownership is intentionally split:

```text
skills-shared
  owns portable method, canonical Skill, system prompt, generic eval language

llm_arbitrage_system
  owns repository profile, branch graph, task packets, path leases,
  Git Town config, wrappers, CI, receipts, PR bases, cleanup, rollback

host/runtime
  owns executable acquisition, platform artifact, checksum/provenance,
  SBOM/transitive review, credentials and logical worktree roots

human/trusted operator
  owns legal acceptance, semantic conflicts, merge/ship, permission changes,
  promotion, production and destructive rollback
```

Do not create `.agents/skills/git-town-stacked-pr-worker` or another repository-local copy of the shared Skill. Shadowing the canonical Skill is a policy failure.

## Mandatory read order for Git work

1. root `AGENTS.md`;
2. root `README.md`;
3. `docs/integration-status.md`;
4. `docs/state-machines.md` and `docs/data-flow.md`;
5. this `README.md`;
6. `REPO_PROFILE.md`;
7. `GIT_TOWN_ADMISSION.md`;
8. `STACKED_PRS.md`;
9. `WORKER_PROTOCOL.md`;
10. `TASK_PACKET.md`;
11. `EVALS.md` and the applicable `docs/harness/` contract;
12. the canonical issue/task packet, current Git graph, PR bases and workflow evidence.

Missing required evidence is `ABSENT`. A planned mechanism is `NOT_IMPLEMENTED`. An available mechanism that was not run on the exact subject is `NOT_EXERCISED`.

## Directory index

| File | Owner question |
| --- | --- |
| `REPO_PROFILE.md` | What exact repository, remote, tool version, strategies, leases, evidence roots and human boundaries are admitted? |
| `GIT_TOWN_ADMISSION.md` | Which Git Town release is pinned, and which executable/legal/provenance evidence lanes are still blocked? |
| `STACKED_PRS.md` | What is the historical and current branch/issue/PR dependency graph and merge order? |
| `WORKER_PROTOCOL.md` | What preflight, sync, verification, cleanup and stop conditions must a Worker follow? |
| `TASK_PACKET.md` | Which fields must exist before a branch or Worker action is admitted? |
| `EVALS.md` | Which positive assertions and disagreement-producing controls are required? |

`docs/harness/` owns fixed eval entrypoints and evidence-lane definitions. Future `scripts/git-town/` files own only fixed Git/worktree/process orchestration and cannot become arbitrary command runners.

## Current adoption state

| Lane | State | Owner |
| --- | --- | --- |
| Shared canonical Skill reference | `PASS` for tracked pointer; runtime resolution is host-dependent | this directory / `AGENTS.md` |
| Repository profile and static config | `OPEN` in issue #13 | PR stack child |
| Exact upstream release pin | `OPEN` in issue #13 | `GIT_TOWN_ADMISSION.md` |
| Host executable digest/provenance/SBOM/notices/legal receipt | `NOT_EXERCISED` | issue #15 |
| Task-packet/path-lease validator | `NOT_IMPLEMENTED` | issue #16 |
| Linked-worktree and lease doctor | `NOT_IMPLEMENTED` | issue #17 |
| Bounded dry-run/no-push sync and receipts | `NOT_IMPLEMENTED` | issue #18 |
| Conflict/prompt/timeout/rollback canaries | `NOT_IMPLEMENTED` | issue #19 |
| GitHub publication gate | `NOT_IMPLEMENTED` | issue #20 |
| Live adoption audit | `NOT_EXERCISED` | issue #21 |

Static policy does not authorize live Git Town execution. A Worker must block until the repository profile is complete for the current branch and issue #15 has produced an admitted host receipt.

## Safe synchronization posture

After admission, the repository requires an exact-version-supported equivalent of:

```bash
git town sync --stack --dry-run --non-interactive --no-auto-resolve --no-push
git town sync --stack --non-interactive --no-auto-resolve --no-push
```

The matching dry-run and live command must cover the same owned stack. Default all-stack or global synchronization is denied unless every branch/path lease is held and the task packet explicitly authorizes that scope.

The tracked `.git-town.toml` also disables automatic resolution, automatic synchronization, push, push hooks, tags and upstream updates. Main uses a non-rewriting `ff-only` perennial strategy; feature branches use `merge` until repository policy explicitly admits history rewriting.

## Result vocabulary

```text
PASS
FAIL
ABSENT
NOT_IMPLEMENTED
NOT_EXERCISED
SKIPPED_BY_POLICY

NO_CHANGE
SYNCED
BLOCKED_TASK_PACKET
BLOCKED_TOOL_ADMISSION
BLOCKED_DIRTY
BLOCKED_BRANCH_LEASE
BLOCKED_ANCESTRY
BLOCKED_PROMPT
BLOCKED_CONFLICT
BLOCKED_TIMEOUT
BLOCKED_POLICY
FAILED_TOOL
FAILED_EVAL
ROLLBACK_REFUSED_DRIFT
```

A Git Town exit code is one input. Postconditions decide the repository result.

## Human Admit boundary

Workers cannot:

```text
resolve semantic conflicts
run git town continue / skip / undo / ship
merge or enter a merge queue
change branch protection or permissions
accept legal/license terms
configure secrets or credentials
promote releases or deploy production
perform destructive or drifted rollback
```

## Bootstrap note

The documentation branches and Draft PRs created under epic #11 are a trusted-operator bootstrap that establishes Git-object ancestry and PR bases. They are not evidence of a local admitted Git Town run. The live lane remains `NOT_EXERCISED` until issue #21 records it.
