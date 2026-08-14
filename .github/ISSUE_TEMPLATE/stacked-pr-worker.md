---
name: Stacked PR worker task
description: Eval-first packet for one branch, path lease, and evidence-bounded Stack PR slice
title: "[Stack] "
labels: []
assignees: []
---

## Parent and objective

- Parent epic/issue:
- Goal:
- Non-goals:
- Evidence boundary:

## Stack graph

```yaml
repository: ed3c/llm_arbitrage_system
base_branch: main
parent_branch: main
head_branch: issue-specific-branch
stack_class: foundation
child_issues: []
parallel_safe_siblings: []
```

Replace every example value with the exact proposed graph. `stack_class` is one of `foundation`, `child`, `sibling`, or `convergence`.

## Path lease

```yaml
allowed_paths:
  - exact/path/or/bounded-glob
excluded_paths:
  - explicit/protected/path
branch_lease: issue-specific-branch
worktree_selector: logical-host-selector
lease_ttl_seconds: 1800
renewal_policy: renew only while the owning process and packet digest still match
```

- [ ] Writable paths are disjoint from live siblings.
- [ ] Exclusions override allowed globs.
- [ ] No primary checkout, secret path, protected branch, or unowned submodule/worktree is writable.

## Dependencies

```yaml
depends_on_issues: []
required_parent_heads: []
```

Explain why each dependency is semantic rather than merely chronological.

## Exact tool and environment admission

- Required profile: `docs/git/REPO_PROFILE.md`
- Required admission receipt:
- Required Git Town version: `v24.0.0`
- Expected repository/remote:
- Expected linked worktree:
- Hard timeout seconds:
- Maximum background iterations:

- [ ] Tool, artifact digest, version, provenance, license/transitive/notices/legal lanes meet policy.
- [ ] Non-interactive prompt suppression is named without logging values.
- [ ] Automatic conflict resolution, push, continue, skip, undo and ship are disabled.

## Positive evals

List fixed typed entrypoints and exact expected results.

```yaml
positive_evals:
  - id: repository-quality
    entrypoint: make check
    expected: PASS
```

## Negative or mutation controls

Every important claim requires disagreement-producing controls.

```yaml
controls:
  - id: example-control
    planted_disagreement: describe the changed input or state
    expected: stable blocked or FAIL result
```

## Publication

```yaml
requested_intent: none
expected_pr_number: null
expected_pr_base: null
expected_pr_head: null
draft_required: true
trusted_snapshot_required: true
```

`requested_intent` is `none`, `initial-pr`, `ready-for-review`, or `batched-repair`. One gate decision authorizes one operation only.

## Cleanup

- Safe resources removable after success:
- Evidence/resources preserved when blocked:
- Residue report location:
- Secrets/credentials explicitly excluded:

## Rollback

```yaml
rollback_subject: immutable SHA or ref captured before mutation
drift_policy: refuse
unattended_undo_or_force: false
```

## Human-owned operations

- [ ] Semantic conflict resolution
- [ ] `git town continue`, `skip`, `undo`, or `ship`
- [ ] Merge or merge-queue admission
- [ ] Legal/license acceptance
- [ ] Permission, billing, or secret changes
- [ ] Release, production, or destructive rollback

## Acceptance checklist

- [ ] Task packet is complete and digestible.
- [ ] Branch/parent/base graph is exact.
- [ ] Branch and path leases are admitted.
- [ ] Dry-run precedes a bounded no-push sync when synchronization is in scope.
- [ ] Postconditions are independently verified.
- [ ] Positive evals and controls bind the exact head.
- [ ] Evidence lanes remain separate.
- [ ] Cleanup and rollback are explicit.
- [ ] Human Admit remains explicit.
