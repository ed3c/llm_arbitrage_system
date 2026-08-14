# Publication gate

## Rule

Publication is a separate evidence lane from local synchronization. A local
`SYNCED` receipt is not permission to touch GitHub, and a zero-exit push is not
proof the remote holds what was intended.

`worker_publication_enabled` is `false` in `docs/git/REPO_PROFILE.md`. The gate
decides; it never publishes. An `ALLOW` names one operation for a human or
operator to perform. Merge, permission changes, billing recovery, release
promotion and production deployment remain Human Admit.

## Fixed entrypoints

```bash
scripts/git-town/publish.sh --intent I --head-branch B \
  --receipt RECEIPT.json --snapshot SNAPSHOT.json \
  [--processed-feedback CURSOR]... [--decisions-ledger DIR]

scripts/git-town/publish.sh --verify-remote --head-branch B \
  --expected-head-sha SHA [--expected-parent-sha SHA] \
  [--protected-before BRANCH=SHA]...

scripts/git-town/publish.sh --selftest
```

The decisions ledger resolves from the logical selector
`HOST_LLM_ARBITRAGE_DECISIONS` when `--decisions-ledger` is omitted. An
unresolved selector blocks rather than defaulting.

## Allowed intents

```text
initial-pr
ready-for-review
batched-repair
```

There is no draft-checkpoint intent and no background intent. A background
worker may prepare a proposal and a snapshot; requesting an intent from
background is `BLOCKED_POLICY`, because `background_push`,
`background_pr_ready_transition` and `background_workflow_rerun` are all denied.

## Trusted GitHub snapshot

The gate is offline. It never calls GitHub: a snapshot is captured out of band
and handed in, so the decision is reproducible and a network hiccup cannot be
mistaken for a policy answer.

```json
{
  "schema": "llm-arbitrage/github-snapshot/v1",
  "repository": "ed3c/llm_arbitrage_system",
  "pull_request_number": null,
  "base_branch": "main",
  "head_branch": "branch name",
  "head_sha": "40 lowercase hex characters",
  "draft": true,
  "feedback_cursor": "opaque cursor",
  "workflow": {"head_sha": "40 hex", "conclusion": "success", "run_id": 0},
  "billing": {"circuit": "closed", "reason": "free text"}
}
```

The schema is closed. Every field is required and an undeclared field is
`BLOCKED_POLICY`: a missing guard is not a soft state, and a snapshot is not a
place to smuggle a command.

## Decision vocabulary

| Condition | Decision |
| --- | --- |
| every check passes | `ALLOW_INITIAL_PR` / `ALLOW_READY_FOR_REVIEW` / `ALLOW_BATCHED_REPAIR` |
| local receipt, snapshot or workflow describes another head | `BLOCKED_STALE_EVIDENCE` |
| billing circuit is open | `BLOCKED_BILLING` |
| this feedback cursor was already answered | `BLOCKED_FEEDBACK` |
| unknown intent, background request, missing guard, wrong repository, wrong PR graph, failing trusted check | `BLOCKED_POLICY` |

## One ALLOW authorizes one operation

Each decision carries a `decision_sha256` over its own content. `publish.sh`
records that digest in the decisions ledger **before** returning it, so
replaying the same decision buys nothing: the second attempt is
`BLOCKED_POLICY`. A different head produces a different digest, which is what
makes the ledger a spend record rather than a cache.

## Post-push verification

After the human or operator performs the authorized operation:

```bash
scripts/git-town/publish.sh --verify-remote --head-branch B \
  --expected-head-sha SHA --expected-parent-sha PARENT \
  --protected-before main=SHA
```

This fetches through the admitted remote and asserts the remote head, the
declared parent ancestry and protected-ref immutability. The fetch is
mandatory: without it every comparison reads stale local knowledge of the
remote and agrees with itself.

The remote URL is checked as resolved by Git, so an `insteadOf` rewrite cannot
redirect an admitted URL to an unadmitted host. Receipts carry scheme and host
only.

## Evidence lanes

These stay separate and a lower lane never marks a higher one:

```text
local sync            receipt.py (#18)
local verification    receipt.py verify (#18)
publication decision  github_snapshot.py evaluate (#20)
remote publication    performed by a human or operator, never by this gate
remote ancestry       remote_verify.py (#20)
trusted check         the snapshot's workflow lane
billing circuit       the snapshot's billing lane
Human Admit           merge, permissions, billing recovery, release, production
```
