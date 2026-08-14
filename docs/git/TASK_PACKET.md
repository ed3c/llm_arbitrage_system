# Eval-first task packet contract

## Rule

No branch creation, linked worktree mutation, Git Town command, publication proposal, or rollback begins without a complete task packet. Natural-language intent is not a substitute.

Issue #16 owns the typed validator. It is implemented at `scripts/git-town/task_packet.py`; see `docs/harness/git-town-task-packet.md` for the mechanism contract. A validator `PASS` is a precondition for branch work, not an admission to act: live Worker execution stays blocked until the host-admission (#15), doctor (#17) and sync (#18) lanes exist.

## Required schema

```yaml
schema: llm-arbitrage/task-packet/v1

identity:
  issue_number: 0
  parent_issue_number: 0
  title: non-empty string
  repository: ed3c/llm_arbitrage_system
  requested_by: human or trusted-controller identity

objective:
  goal: non-empty string
  non_goals:
    - at least one explicit exclusion
  evidence_boundary: non-empty string

stack:
  base_branch: existing branch
  parent_branch: existing branch
  head_branch: unique branch
  stack_class: foundation | child | sibling | convergence
  dependencies:
    - issue number or empty list
  parallel_safe_siblings:
    - issue number or empty list

leases:
  branch_lease: exact head branch
  worktree_selector: logical host selector
  allowed_paths:
    - at least one exact path or bounded glob
  excluded_paths:
    - explicit protected paths
  lease_ttl_seconds: positive bounded integer
  renewal_policy: explicit string

execution:
  required_tool_profile: docs/git/REPO_PROFILE.md
  exact_tool_admission_required: true
  dry_run_first: true
  non_interactive: true
  automatic_conflict_resolution: false
  push_allowed: false
  timeout_seconds: positive bounded integer
  max_background_iterations: positive bounded integer

evals:
  positive:
    - assertion ID with fixed entrypoint and expected result
  negative_or_mutation:
    - control ID, planted disagreement and expected blocked/fail result
  exact_subject_binding: true

publication:
  requested_intent: none | initial-pr | ready-for-review | batched-repair
  expected_pr_number: integer or null
  expected_pr_base: exact branch or null
  expected_pr_head: exact branch or null
  draft_required: boolean
  trusted_snapshot_required: true

cleanup:
  contract: non-empty string
  safe_to_remove_on_success:
    - bounded resource classes
  preserve_on_block:
    - conflict worktree or other evidence

rollback:
  subject: immutable ref or SHA
  drift_policy: refuse
  unattended_undo_or_force: false

human_owned_operations:
  - semantic conflict resolution
  - merge or merge-queue admission
  - legal acceptance
  - permission, billing or secret changes
  - release and production promotion
```

The numeric `0` and descriptive values above define field types; they are not a valid admitted packet. A real issue must supply exact values and no unresolved template markers.

## Validation laws

### Identity and graph

- repository must equal `ed3c/llm_arbitrage_system`;
- issue and parent issue must exist unless the packet is the root epic;
- head branch must be unique and cannot equal main/perennial branches;
- base, parent and head must match GitHub PR lineage;
- dependencies must be satisfiable before the action;
- sibling classification requires path-disjoint work and no artificial parent dependency;
- convergence requires every integrated leaf dependency.

### Path leases

- allowed paths cannot be empty;
- excluded paths override allowed globs;
- a live sibling lease may not overlap an allowed path;
- repository policy, secret locations, protected refs and primary checkout remain excluded even if omitted;
- the diff after the operation must be a subset of the lease.

### Execution

- `exact_tool_admission_required` must remain true for Git Town work;
- `dry_run_first`, `non_interactive` and hard timeout must remain enabled;
- `automatic_conflict_resolution`, default push and unattended undo/ship must remain false;
- generic shell command fields are rejected; task packets select typed entrypoints only.

### Evals and controls

Every important claim needs:

```text
positive assertion
+ at least one disagreement-producing negative or mutation control
+ exact subject binding
```

Examples:

- version assertion + wrong-version mutation;
- ancestry assertion + wrong-parent mutation;
- allowed-path assertion + planted out-of-lease change;
- no-push assertion + fake remote-ref movement;
- conflict stop assertion + planted semantic conflict;
- cleanup assertion + planted residue;
- rollback assertion + drifted target.

### Publication

`requested_intent: none` is the default. A publication intent requires the exact PR base/head, local receipt and trusted GitHub snapshot. One gate decision authorizes one operation only.

### Cleanup and rollback

Cleanup cannot destroy blocked semantic-conflict evidence. Rollback uses immutable recorded refs and refuses unrelated drift. `git town undo`, raw reset/delete and force push are not unattended rollback mechanisms.

## Stable rejection mapping

| Invalid packet condition | Result |
| --- | --- |
| missing/empty required field | `BLOCKED_TASK_PACKET` |
| branch/base/parent/dependency mismatch | `BLOCKED_ANCESTRY` |
| overlapping branch/path lease | `BLOCKED_BRANCH_LEASE` |
| unsafe command/push/conflict/rollback request | `BLOCKED_POLICY` |
| admission evidence missing | `BLOCKED_TOOL_ADMISSION` |

## Documentation stack packets

The current documentation stack is tracked in:

```text
#11 epic
#12 Agent/integration SSOT
#13 Git Town governance
#14 README convergence
```

Their issue bodies declare goal, non-goals, base/parent/head, stack class, allowed/excluded paths, dependencies, evals, controls, cleanup, evidence boundary, rollback subject and human-owned operations. Their Draft PRs are a trusted-operator bootstrap; they do not satisfy the future live Worker packet-validation receipt.

## Future leaf packets

Issues #15–#21 each own one molecular mechanism and one narrow path lease. A future implementation PR must copy the canonical issue fields into its PR body, bind them to exact heads, and update `STACKED_PRS.md` only through the designated convergence owner.

## Validator entrypoint

```bash
python scripts/git-town/task_packet.py --packet PACKET.yaml \
  [--sibling-lease LEASE.json ...] \
  [--emit-canonical CANONICAL.json] [--emit-lease LEASE.json]
python scripts/git-town/task_packet.py --selftest
```

Stdout carries exactly one canonical receipt; the rejection reason goes to stderr so the receipt stays byte-stable. Exit status is `0` only for `PASS`.

`--emit-lease` writes this packet's path-lease manifest, which is the same format `--sibling-lease` consumes. One admitted Worker's manifest is therefore the input that blocks the next Worker from claiming overlapping paths.

The validator is offline. It never resolves issues or branches against GitHub or the local repository: issue resolution belongs to the publication gate (#20) and branch/worktree reality belongs to the doctor (#17). This file's identity and graph laws are checked for internal consistency only.

## Receipt payload

Canonical output:

```json
{
  "schema": "llm-arbitrage/task-packet-receipt/v1",
  "packet_sha256": "64 lowercase hex characters",
  "repository": "ed3c/llm_arbitrage_system",
  "issue_number": 0,
  "head_branch": "branch name",
  "parent_branch": "branch name",
  "allowed_paths_sha256": "64 lowercase hex characters",
  "dependencies_sha256": "64 lowercase hex characters",
  "result": "PASS or stable blocked result"
}
```

On a rejection the same keys are emitted with every packet-derived field set to `null`, so a blocked receipt can never be mistaken for a thin `PASS`.

`packet_sha256` is taken over the normalized packet, not the source bytes. Key order, list order and comments do not change it; a changed allowed path does.

No task packet or receipt may contain secret values, private keys, account identifiers, credential-bearing URLs, browser sessions, or unbounded command output. The validator enforces the credential-URL and host-path rules mechanically and returns `BLOCKED_POLICY`.
