# Harness — bounded no-push sync and receipt writer (#18)

Mechanism owner for evidence lanes E06 and E07 in `docs/git/EVALS.md`. Task
execution steps 2 to 7 of `docs/git/WORKER_PROTOCOL.md` are the acceptance
contract.

## Implementation state

```text
mechanism_selftest:            PASS  scripts/git-town/receipt.py --selftest
                                     scripts/git-town/sync.sh --selftest
negative_or_mutation_control:  PASS  tests/git-town/test_sync_contract.py
static_contract:               PASS  docs/git/WORKER_PROTOCOL.md
live_canary:                   NOT_EXERCISED  (#21)
```

The adapter is bounded and no-push. It never resolves conflicts, edits conflict
markers, continues, skips, undoes, ships, resets, deletes a branch, or pushes.

## Fixed entrypoint

```bash
scripts/git-town/sync.sh --head-branch B --allowed-path P [--allowed-path P]... \
  [--excluded-path P]... [--timeout-seconds N] [--receipts-root DIR] [--dry-run-only]
scripts/git-town/sync.sh --selftest
```

`sync.sh` owns ordering, selector resolution, cleanup and status propagation.
Every step is a typed operation in `receipt.py`:

```text
capture   repository evidence from fixed Git commands
sync      one fixed Git Town command shape, bounded by a hard timeout
verify    the step-5 postconditions, independent of the mutating path
append    one immutable entry in the receipt ledger
propose-rollback   compare the world against a receipt and propose, never act
```

The Git Town executable is resolved from the logical selector
`HOST_GIT_TOWN_BIN`. `v24.0.0` is admitted for `darwin_arm64` by receipt
`eda73fcc` (#15), so on that host the adapter can run; anywhere else, and
whenever the selector is unset, it returns `BLOCKED_TOOL_ADMISSION`.

## The caller picks a mode, never an argument vector

`receipt.py sync --mode dry-run|live` builds the command itself from
`docs/git/REPO_PROFILE.md`:

```text
dry-run:  sync --dry-run --stack --non-interactive --no-auto-resolve --no-push
live:     sync          --stack --non-interactive --no-auto-resolve --no-push
```

There is no argv parameter to pass through, so `--no-push` cannot be dropped by
a caller and a continuation subcommand cannot be requested at all. The verifier
additionally asserts the two shapes differ only by `--dry-run` and that both
still carry `--no-push` and `--no-auto-resolve`, so a future edit to the shape
constants is caught rather than trusted.

## Result vocabulary

| Condition | Result |
| --- | --- |
| head moved, every postcondition holds | `SYNCED` |
| head unchanged, every postcondition holds | `NO_CHANGE` |
| conflict text, or `MERGE_HEAD`/`rebase-merge` present after the run | `BLOCKED_CONFLICT` |
| prompt text on either stream | `BLOCKED_PROMPT` |
| hard timeout reached | `BLOCKED_TIMEOUT` |
| tool selector unresolved, or version is not `v24.0.0` | `BLOCKED_TOOL_ADMISSION` |
| non-zero exit with no more specific state | `FAILED_TOOL` |
| any postcondition fails, even on a zero exit | `FAILED_EVAL` |
| a rollback is requested but the world moved since the receipt | `ROLLBACK_REFUSED_DRIFT` |

## Signal → action

**Signal: the tool exited zero.**
That is not the repository result. `verify` re-reads the repository and checks
the current branch, perennial refs, remote-tracking refs, the branch and
worktree sets, working-tree cleanliness, ancestry from the pre-sync subject,
and that every changed path is inside the lease. A zero exit with a moved
perennial ref is `FAILED_EVAL`.

**Signal: you want to know it would refuse.**
Run with `--dry-run-only`. It performs admission and the dry run and stops
before the live command. There is a control asserting exactly one invocation
reached the tool and that it carried `--dry-run`.

**Signal: a run blocked.**
The intermediate evidence directory is preserved and its path is printed. On a
clean run it is removed. Cleanup never destroys blocked evidence, because a
preserved conflict lane is the only thing a human has to work from.

**Signal: you want to trust the receipt.**
It binds `before_subject`, `after_subject`, both trees, the tool version, all
four lane results, and the rollback subject. Files are written read-only and
named by their own content digest, so an identical receipt is idempotent and a
changed subject is a different file. The ledger is never rewritten in place.

**Signal: the tool spawned children and then hung.**
The tool runs in its own session and a timeout reaps the whole group.
`subprocess.run(timeout=...)` kills only the direct child, which leaves
grandchildren running while the adapter reports a clean stop. The run record
carries a `residue` lane with `process_group_reaped`; if a process survives the
kill it is reported as `false` rather than assumed away.

**Signal: streams may contain something sensitive.**
They never reach a receipt raw. Each stream is stored as a SHA-256, a byte
count, a truncation flag, and a bounded excerpt with credential URLs replaced.
Worktree evidence records branch names only — worktree paths are host-specific
and denied in tracked receipts.

## Why the controls need a stub executable

Git Town is not admitted on any host (#15), and a real binary would only ever
demonstrate the happy path anyway. The controls drive a stub whose behaviour is
selected by an environment variable, which is what makes conflict, prompt,
timeout, out-of-lease diff, moved perennial ref and unexpected branch reachable
at all. A green adapter that has never been shown to go red is a single
attestation; these make the red paths part of the same suite.

## Deliberate boundaries

- Rollback is proposed, never performed. `propose-rollback` compares the head
  against the receipt's recorded after-subject and confirms the rollback
  subject is still reachable. Any disagreement is `ROLLBACK_REFUSED_DRIFT`:
  the receipt no longer describes the world, so restoring from it would
  overwrite a change nobody has looked at. A clean comparison returns a bounded
  proposal with `requires_human_admit`. `git town undo`, raw reset/delete and
  force push are never run unattended. Issue #19 owns the drift canaries.
- Prompt and conflict classification is textual plus a Git state probe. Text
  matching alone would miss a silent conflict, and the state probe alone would
  miss a tool that reports a conflict without leaving markers; neither is
  sufficient, so both run.
- Publication is a different lane entirely. This adapter may prepare evidence
  for #20's gate; it cannot push or transition a PR.
