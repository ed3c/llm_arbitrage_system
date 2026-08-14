# Git Town Worker protocol

## Scope

This protocol governs repository-local branch hierarchy and synchronization work. It consumes the canonical shared `git-town-stacked-pr-worker` Skill and the repository profile; it does not redefine the portable Skill.

Current live-adapter state:

```text
host admission:          PASS for darwin_arm64 (#15), receipt eda73fcc
task-packet validator:   IMPLEMENTED (#16)   scripts/git-town/task_packet.py
worktree/lease doctor:   IMPLEMENTED (#17)   scripts/git-town/doctor.sh, lease.py
bounded sync/receipts:   IMPLEMENTED (#18)   scripts/git-town/sync.sh, receipt.py
fail-closed canaries:    NOT_IMPLEMENTED (#19)
publication gate:        NOT_IMPLEMENTED (#20)
live adoption audit:     NOT_EXERCISED (#21)
```

`IMPLEMENTED` means the mechanism and its mutation controls exist and pass; it does not mean the lane was exercised against a live Git Town run. Until the remaining owner issues merge and their exact-subject receipts pass, live Worker execution still returns `BLOCKED_TOOL_ADMISSION` — host admission (#15) is unexercised, so `live_execution_admitted` remains `false` in `docs/git/REPO_PROFILE.md`.

## Worker identity

One Worker owns exactly:

```text
one canonical issue/task packet
one linked worktree
one head branch
one branch lease
one disjoint writable path set
one bounded execution window
one append-only receipt namespace
```

The Worker must not mutate the primary checkout, another Worker branch, a sibling path lease, a perennial/protected branch, or an undeclared submodule/worktree.

## Preflight

The Worker evaluates every check before any mutating command:

1. **Task packet**
   - all required fields exist;
   - issue, parent issue and dependency issues resolve;
   - base, parent and head branch names are exact;
   - allowed and excluded paths are explicit;
   - evals, negative controls, cleanup, rollback and human-owned operations exist;
   - canonical packet digest is recorded.
2. **Tool admission**
   - exact Git Town version and executable digest match an admitted host receipt;
   - repository identity and remote match `REPO_PROFILE.md`;
   - direct license, provenance, SBOM/transitive, notices and legal lanes meet repository policy.
3. **Worktree and leases**
   - current directory is the admitted linked worktree, not the primary checkout;
   - current branch equals the task packet head;
   - branch lease is exclusive and live;
   - path lease is disjoint from live sibling leases;
   - lease expiry/renewal rules are satisfied.
4. **Repository state**
   - worktree/index are clean before synchronization;
   - no merge/rebase/cherry-pick/revert/bisect operation is in progress;
   - parent and base refs exist and match the declared graph;
   - remote URL is credential-free and admitted;
   - protected/perennial refs are captured as immutable before subjects.
5. **Non-interactive environment**
   - editor, pager and credential prompts are disabled through named environment policy;
   - a hard timeout and maximum background iteration count exist;
   - stdout/stderr capture is bounded and redacted before receipt storage.

Failure maps to one stable blocked result and performs no synchronization.

Steps 1 and 2's packet fields are enforced by `scripts/git-town/task_packet.py` (#16). Steps 3 to 5 are enforced by `scripts/git-town/doctor.sh` (#17), which collects repository facts with fixed Git commands and hands them to `scripts/git-town/lease.py` for typed judgment and the branch/path lease. Both emit one canonical receipt on stdout and keep the reason on stderr; both exit non-zero on any blocked result.

```bash
python scripts/git-town/task_packet.py --packet PACKET.yaml --emit-lease LEASE.json
scripts/git-town/doctor.sh --head-branch B --allowed-path P [--allowed-path P]...
scripts/git-town/sync.sh   --head-branch B --allowed-path P [--allowed-path P]... [--dry-run-only]
```

Steps 2 to 7 below are performed by `scripts/git-town/sync.sh` (#18), which sequences the typed operations in `scripts/git-town/receipt.py`: `capture`, `sync`, `verify`, `append`. The Git Town executable is resolved from the logical selector `HOST_GIT_TOWN_BIN`. Issue #15 admitted `v24.0.0` for `darwin_arm64` (receipt `eda73fcc`); on any other host, or with the selector unset, a real invocation returns `BLOCKED_TOOL_ADMISSION`.

The doctor resolves its lease store from the logical selector `HOST_LLM_ARBITRAGE_LEASES`; an unresolved selector is `BLOCKED_POLICY`, never a default path. The origin URL is passed on stdin so a credential-bearing remote is not published to the process table by the very check that rejects it.

## Task execution

### Step 1 — capture before evidence

Record:

```text
repository identity
issue/task packet digest
branch/parent/base
exact local and remote refs
current branch
worktree identity
branch/path leases
porcelain status
graph/ancestry snapshot
protected/perennial refs
Git Town executable digest/version
command shape and timeout
```

### Step 2 — dry-run

Run through the fixed adapter:

```bash
git town sync --stack --dry-run --non-interactive --no-auto-resolve --no-push
```

The adapter must prove that the dry-run scope equals the task packet's owned stack. Unexpected branches, prompts, global scope, protected-ref edits, or unsupported flags block execution.

### Step 3 — bounded no-push sync

Only after the dry-run passes:

```bash
git town sync --stack --non-interactive --no-auto-resolve --no-push
```

The live command uses the same admitted executable, worktree, branch, stack scope, environment and timeout as the dry-run.

### Step 4 — classify tool outcome

Tool exit status alone is not the repository result. Inspect:

```text
conflict markers and Git operation state
prompt/timeout indicators
current branch
worktree dirtiness
before/after graph
perennial/protected ref movement
path-lease diff
residue and child processes
```

Possible interim states:

```text
NO_CHANGE
SYNCED
BLOCKED_PROMPT
BLOCKED_CONFLICT
BLOCKED_TIMEOUT
FAILED_TOOL
```

On semantic conflict, preserve the worktree and emit a conflict receipt. Do not edit conflict markers, continue, skip, undo, ship, reset, delete the branch, or force push.

### Step 5 — independent postconditions

A separate verifier, not the mutating shell path, must assert:

```text
current branch remained the declared head
head is still based on the declared parent relation
stack order matches the task packet
protected/perennial refs did not move unexpectedly
only leased paths changed relative to the allowed comparison base
no unexpected worktree or branch was created
no remote ref changed during no-push sync
cleanup contract holds or residue is explicitly blocked
```

Failure becomes `FAILED_EVAL` even when Git Town exited zero.

### Step 6 — exact-head repository evals

Run every task-packet eval and negative/mutation control against the exact post-sync head. Bind each result to:

```text
commit SHA
tree SHA
command or typed entrypoint
input/control digest
start/end time
bounded output digest
result state
```

The core repository gates are:

```bash
make check
make phase3-smoke
make phase4-smoke
```

Task-specific checks may add more assertions but cannot weaken these when they apply.

### Step 7 — local receipt

Append one immutable receipt with separate lanes:

```text
preflight
local dry-run
local sync
post-sync graph/path verification
repository evals
negative controls
cleanup/residue
rollback subject
```

Never write secrets, private keys, credential URLs, cookies, tokens, full environment dumps, or unbounded raw command streams.

## Background behavior

Background operation is disabled until issues #15–#19 merge and issue #21 exercises the live canary.

After admission, background mode remains:

```text
bounded iterations
bounded wall-clock timeout
one owned stack only
no push
no PR-ready transition
no workflow rerun
no merge/ship
stop on conflict, prompt, dirty state, lease loss or policy drift
```

A background Worker may prepare a publication proposal and trusted-state snapshot for issue #20's gate; it cannot perform the publication without one `ALLOW` decision for one intent.

## Publication handoff

Publication is a different evidence lane. The Worker hands off:

```text
exact local head
local sync/verification receipt digest
PR number and expected base/head
draft/ready intent
trusted GitHub state snapshot
feedback cursor and billing/circuit state
```

The publication gate may return one of:

```text
ALLOW_INITIAL_PR
ALLOW_READY_FOR_REVIEW
ALLOW_BATCHED_REPAIR
BLOCKED_POLICY
BLOCKED_STALE_EVIDENCE
BLOCKED_BILLING
BLOCKED_FEEDBACK
```

An `ALLOW` result authorizes only the named operation. After a push, issue #20 must fetch the remote, verify exact remote head and parent ancestry, and record remote evidence separately. Merge remains Human Admit.

## Rollback

Every mutating run records immutable before refs. Rollback policy:

1. compare current refs with the receipt's expected after refs;
2. refuse if unrelated drift exists (`ROLLBACK_REFUSED_DRIFT`);
3. propose a bounded ref restoration for human review;
4. never run `git town undo`, raw destructive reset/delete, or force push unattended — `scripts/git-town/receipt.py propose-rollback --receipt RECEIPT.json` returns a bounded proposal with `requires_human_admit`, or `ROLLBACK_REFUSED_DRIFT`, and executes nothing;
5. record cleanup and remaining residue independently.

## Stable result mapping

| Condition | Result |
| --- | --- |
| missing required task field | `BLOCKED_TASK_PACKET` |
| tool/admission lane absent or not passing | `BLOCKED_TOOL_ADMISSION` |
| dirty tree or in-progress Git operation | `BLOCKED_DIRTY` |
| branch/path lease unavailable | `BLOCKED_BRANCH_LEASE` |
| parent/base/stack mismatch | `BLOCKED_ANCESTRY` |
| unexpected interactive request | `BLOCKED_PROMPT` |
| semantic conflict | `BLOCKED_CONFLICT` |
| hard timeout | `BLOCKED_TIMEOUT` |
| repository policy forbids requested scope/action | `BLOCKED_POLICY` |
| tool process fails without a more specific blocked state | `FAILED_TOOL` |
| postcondition, repository eval or control fails | `FAILED_EVAL` |
| no ref/tree change and all checks pass | `NO_CHANGE` |
| expected sync change and all checks pass | `SYNCED` |
| rollback subject drifted | `ROLLBACK_REFUSED_DRIFT` |

## Completion packet

A Worker response is incomplete unless it reports:

```text
issue and task-packet digest
repository/worktree/branch/parent/base
before and after heads
changed paths versus lease
local sync state
local verification/eval/control states
publication decision state
remote publication and ancestry states
GitHub trusted-check state
cleanup/residue
rollback subject
remaining evidence gaps
Human Admit state
```
