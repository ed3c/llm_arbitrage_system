# Git Town and Stacked-PR eval contract

## Purpose

Repository tests remain `make check`, `make phase3-smoke`, and `make phase4-smoke`. This file adds assertions for the Git Town worker, branch graph, task packet, receipts and publication lanes.

The portable eval language comes from the shared `git-town-stacked-pr-worker` Skill. This file selects repository-specific assertions and maps each to an owner issue.

## Evidence ladder

Keep these lanes separate:

```text
1. requirements review
2. static configuration/contract
3. mechanism selftest
4. negative or mutation control
5. live linked-worktree canary
6. local exact-head repository evals
7. publication decision
8. remote publication
9. post-push remote head/ancestry
10. GitHub trusted check
11. Human Admit
12. release / production observation
```

A lower lane cannot mark a higher lane `PASS`.

## Current evidence state

| Lane | Current state | Owner |
| --- | --- | --- |
| Requirements review and decomposition | `PASS` for issues #11–#21 | documentation epic |
| Static `.git-town.toml` and repository profile | `OPEN` in issue #13 | documentation stack |
| Exact host tool admission | `NOT_EXERCISED` | #15 |
| Task-packet mechanism selftest | `NOT_IMPLEMENTED` | #16 |
| Worktree/lease mechanism selftest | `NOT_IMPLEMENTED` | #17 |
| Bounded sync mechanism selftest | `NOT_IMPLEMENTED` | #18 |
| Conflict/prompt/timeout/rollback controls | `NOT_IMPLEMENTED` | #19 |
| Publication decision and remote verification | `NOT_IMPLEMENTED` | #20 |
| Live adoption canary and Human Admit | `NOT_EXERCISED` | #21 |

The documentation stack may produce GitHub CI results for Markdown-only heads. It does not convert live Git Town lanes to `PASS`.

## E01 — canonical Skill ownership

Positive assertions:

- tracked documents point to `ed3c/skills-shared/skills/git-town-stacked-pr-worker`;
- no repository-local directory contains a same-name `SKILL.md` body;
- repository-specific behavior is confined to profile/config/issue/templates/Harness/adapter paths.

Mutation controls:

- add a local shadow Skill → `FAIL`;
- remove the canonical pointer → `FAIL`;
- route portable policy to a repository-only prompt → `FAIL`.

Owner: issue #13.

## E02 — repository profile completeness

Positive assertions:

- repository identity, ID, default/perennial branch and remote are concrete;
- exact Git Town release/tag/checksum/license fields exist;
- host-dependent evidence uses explicit states instead of placeholders;
- sync strategies, worktree/lease selectors, receipt root, eval entrypoints, forbidden data and Human Admit operations exist;
- no angle-bracket placeholder or empty required field remains.

Mutation controls:

- remove one required field → `FAIL`;
- insert unresolved placeholder → `FAIL`;
- change repository identity or main branch → `FAIL`;
- change `background_default_push` to true → `FAIL`.

Owner: issue #13.

## E03 — exact-tool admission

Positive assertions:

- selected host artifact matches platform/architecture;
- release and tag are immutable references;
- artifact SHA-256 matches the upstream manifest;
- installed executable digest and version output match the admitted artifact and `v24.0.0`;
- direct license, provenance, SBOM/transitive, notices and legal lanes meet repository policy;
- receipt binds host, executable, repository and task packet.

Mutation controls:

- wrong version;
- changed artifact digest;
- substituted executable;
- wrong architecture;
- missing SBOM/notices/legal state;
- mutable `latest` acquisition selector.

Expected failure: `BLOCKED_TOOL_ADMISSION`.

Owner: issue #15.

## E04 — task packet and path leases

Positive assertions:

- all fields in `TASK_PACKET.md` validate;
- branch/base/parent/dependencies exist and agree;
- allowed/excluded paths are canonical and disjoint from sibling leases;
- evals, controls, cleanup, rollback and Human Admit exist;
- generic shell injection fields are impossible;
- packet and lease digests are stable.

Mutation controls:

- remove each required field individually;
- overlap one sibling path;
- point parent to the wrong branch;
- request a protected branch as head;
- add arbitrary command text;
- enable push or automatic conflict resolution.

Expected failures: `BLOCKED_TASK_PACKET`, `BLOCKED_BRANCH_LEASE`, `BLOCKED_ANCESTRY`, or `BLOCKED_POLICY`.

Owner: issue #16.

## E05 — worktree and lease doctor

Positive assertions:

- current path is an admitted linked worktree for this repository;
- current branch equals the task packet head;
- primary checkout is not mutated;
- branch and path leases are exclusive, live and renewable;
- repository state is clean and no Git operation is in progress;
- remote URL is admitted and contains no credential;
- non-interactive environment policy is applied by name without logging values.

Mutation controls:

- run from primary checkout;
- wrong repository identity;
- dirty index/tree;
- existing merge/rebase/cherry-pick state;
- duplicate branch lease;
- overlapping path lease;
- expired lease without valid renewal;
- credential-bearing remote URL;
- missing prompt suppression.

Owner: issue #17.

## E06 — dry-run and bounded no-push sync

Positive assertions:

- dry-run occurs before the live command;
- both commands use the same exact executable, worktree, branch, stack scope, flags and timeout;
- command includes `--stack --non-interactive --no-auto-resolve --no-push`;
- task packet owns every synchronized branch/path;
- remote refs do not move;
- current branch remains the owned head;
- before/after graph and streams are bounded and receipted.

Mutation controls:

- dry-run scope differs from live scope;
- remove `--no-push`;
- enable auto-resolve;
- include an unleased branch;
- exceed timeout;
- inject an editor/credential prompt;
- mutate a remote ref during no-push mode.

Owner: issue #18.

## E07 — independent graph and path verification

Positive assertions:

- after head descends from the intended operation's before subject;
- declared parent/stack order holds;
- main/perennial/protected refs did not move unexpectedly;
- changed files are a subset of allowed paths minus exclusions;
- no unexpected branch/worktree exists;
- exact-head repository evals are bound to the after subject.

Mutation controls:

- wrong parent;
- protected ref movement;
- out-of-lease file change;
- unexpected branch/worktree;
- replay eval receipt from an older SHA.

Owner: issues #18 and #19.

## E08 — semantic conflict and prompt stop

Positive assertions:

- planted semantic conflict produces `BLOCKED_CONFLICT`;
- conflict worktree, graph and bounded output evidence are preserved;
- no conflict marker is edited automatically;
- no continue/skip/undo/ship/reset/delete/force operation runs;
- fake editor/credential prompt produces `BLOCKED_PROMPT`;
- timeout produces `BLOCKED_TIMEOUT` with process cleanup evidence.

Mutation controls:

- adapter returns success after conflict markers exist;
- adapter deletes conflict evidence;
- adapter runs a forbidden continuation command;
- orphan process remains after timeout.

Owner: issue #19.

## E09 — cleanup and drift-aware rollback

Positive assertions:

- safe temporary resources are removed after success;
- blocked semantic-conflict resources are preserved when required;
- leases are released only under their cleanup contract;
- residue is reported separately;
- rollback compares exact current refs with the receipt before proposing restoration;
- unrelated drift yields `ROLLBACK_REFUSED_DRIFT`.

Mutation controls:

- planted residue;
- expired process survives;
- rollback target moved independently;
- automatic `git town undo` or force push attempted.

Owner: issue #19.

## E10 — repository exact-head quality

Positive assertions on the exact PR head:

```bash
make check
make phase3-smoke
make phase4-smoke
```

Expected repository CI matrix:

```text
Ruff
strict Mypy
pytest + configured coverage floor
Python 3.10, 3.11, 3.12 and 3.13
Phase 3 smoke
Phase 4 smoke
```

Controls:

- receipt subject differs from checked SHA;
- a required command is omitted;
- old-SHA success is reused after a new commit;
- a smoke path is intentionally corrupted and must fail.

Owner: every implementation PR; CI remains the remote lane.

## E11 — publication gate

Positive assertions:

- local exact-head receipt is valid and current;
- trusted GitHub snapshot binds repository, PR, base/head, draft state, feedback cursor, workflow and billing/circuit state;
- requested intent is one of `initial-pr`, `ready-for-review`, `batched-repair`;
- one `ALLOW` decision authorizes one operation;
- Draft checkpoint pushes remain denied;
- background push/ready/rerun remain denied.

Mutation controls:

- stale local receipt;
- wrong PR base/head;
- repeated feedback cursor;
- old-SHA CI;
- billing/circuit open;
- missing guard;
- unrecognized intent;
- second operation under one `ALLOW`.

Owner: issue #20.

## E12 — remote publication and ancestry

Positive assertions after an admitted operation:

- fetch the remote through the admitted URL;
- exact remote head equals the intended local head;
- remote parent/stack ancestry matches the declared graph;
- protected refs were not rewritten;
- PR metadata equals expected base/head/draft state;
- remote receipt is separate from local receipt.

Mutation controls:

- wrong remote;
- pushed head mismatch;
- parent/base drift;
- protected ref rewrite;
- missing post-push fetch;
- local success used as remote success.

Owner: issue #20.

## E13 — convergence and adoption audit

Positive assertions:

- every issue #15–#20 receipt is admitted and subject-bound;
- first live linked-worktree dry-run and no-push sync pass;
- conflict/prompt/timeout canaries disagree correctly;
- one Draft and one ready publication lane obey policy;
- exact-head CI and remote ancestry are current;
- cleanup and rollback lanes are explicit;
- Human Admit state is explicit;
- report uses all evidence states without collapsing them.

Mutation controls:

- omit one evidence lane;
- promote `NOT_EXERCISED` to `PASS`;
- infer remote/CI/Human Admit from local sync;
- describe documentation presence as live adoption.

Owner: issue #21.

## Documentation stack checks

Issues #12–#14 additionally require:

```text
all referenced repository paths exist on the owning branch
merged/open/planned states match GitHub truth
README directory entries map to State Machine and data-flow owners
active PR bases match the serial branch graph
historical PR numbers and merge subjects are correct
future leaf issues include owner, dependencies, path lease, evals and state
```

The documentation stack remains Draft. Passing documentation CI is not Human Admit.
