## Issue and goal

- Canonical issue:
- Parent issue:
- Goal:
- Non-goals:
- Evidence boundary:

## Stack graph

```text
base
└── parent
    └── this head
        └── child PRs, if any
```

```yaml
base_branch: main
parent_branch: main
head_branch: exact-head-branch
stack_class: foundation
child_prs: []
```

- [ ] PR base equals the declared parent branch.
- [ ] Branch ancestry equals the declared stack.
- [ ] Independent path-disjoint work is modeled as siblings rather than artificial children.

## Path lease

```yaml
allowed_paths:
  - exact/path/or/bounded-glob
excluded_paths:
  - explicit/protected/path
```

- Changed paths:
- Sibling lease check:
- Out-of-lease diff result:

## Implementation

Describe only behavior present in this PR. Distinguish `MERGED`, `OPEN`, `PLANNED`, `BLOCKED`, `NOT_IMPLEMENTED`, and `NOT_EXERCISED`.

## State Machine and data flow

- State Machine owner:
- Input contract:
- Output contract:
- Persistence/evidence:
- Failure/blocked transitions:
- Cross-layer invariants preserved:

## Exact tool / worktree admission

- Git Town required version: `v24.0.0`
- Admission receipt or state:
- Linked worktree identity or state:
- Branch/path lease receipt or state:
- Local Git Town sync state:

Use `NOT_EXERCISED` when a live lane was not run. Static config is not a live admission receipt.

## Verification

### Positive evals

```text
command or typed entrypoint → result → exact commit/tree subject
```

### Negative or mutation controls

```text
planted disagreement → expected blocked/fail state → result → exact subject
```

### Repository gates

- [ ] `make check`
- [ ] `make phase3-smoke` when affected
- [ ] `make phase4-smoke` when affected
- [ ] current PR-head CI, not an older SHA

## Evidence lanes

| Lane | Result | Subject / receipt |
| --- | --- | --- |
| Requirements review |  |  |
| Static contract |  |  |
| Mechanism selftest |  |  |
| Negative/mutation control |  |  |
| Live Git Town canary |  |  |
| Local exact-head verification |  |  |
| Publication decision |  |  |
| Remote publication |  |  |
| Remote head/ancestry |  |  |
| GitHub trusted check |  |  |
| Cleanup/residue |  |  |
| Human Admit |  |  |

Allowed states: `PASS`, `FAIL`, `ABSENT`, `NOT_IMPLEMENTED`, `NOT_EXERCISED`, `SKIPPED_BY_POLICY`.

## Publication contract

```yaml
intent: none
expected_pr_base: exact-base
expected_pr_head: exact-head
draft: true
post_push_fetch: required
remote_head_verification: required
remote_ancestry_verification: required
```

- [ ] A gate `ALLOW` authorizes one operation only.
- [ ] Background push, PR-ready transition, workflow rerun and merge remain denied unless explicitly admitted.
- [ ] This PR remains Draft until the stack checkpoint says otherwise.

## Cleanup and rollback

- Cleanup contract:
- Residue:
- Immutable rollback subject:
- Drift check:
- Blocked evidence preserved:

## Security and non-claims

- [ ] No exchange/broker credential, wallet/provenance private key, seed phrase, account identifier, withdrawal authority, browser session, credential URL, or secret value is included.
- [ ] No live trading, source-authenticity, profitability, risk-free, release, production, or Human Admit claim is inferred from lower evidence.
- [ ] No automatic semantic conflict resolution, `continue`, `skip`, `undo`, `ship`, merge, force push, permission change, or destructive rollback is introduced.

## Human Admit

Name every remaining human-owned action, including merge order and any semantic conflict, legal, permission, billing, release, production, or rollback decision.
