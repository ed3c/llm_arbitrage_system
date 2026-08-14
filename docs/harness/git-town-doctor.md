# Harness — worktree and branch-lease doctor (#17)

Mechanism owner for evidence lane E05 in `docs/git/EVALS.md`. Preflight steps 3
and 4 of `docs/git/WORKER_PROTOCOL.md` are the acceptance contract.

## Implementation state

```text
mechanism_selftest:            PASS  scripts/git-town/lease.py --selftest
                                     scripts/git-town/doctor.sh --selftest
negative_or_mutation_control:  PASS  tests/git-town/test_doctor.py
static_contract:               PASS  docs/git/WORKER_PROTOCOL.md
live_canary:                   NOT_EXERCISED  (#21)
```

The doctor admits or refuses a worktree and takes one lease. It never
synchronizes, resolves conflicts, moves refs, pushes, or runs Git Town.

## Fixed entrypoint

```bash
scripts/git-town/doctor.sh --head-branch B --allowed-path P [--allowed-path P]... \
  [--holder ID] [--ttl-seconds N] [--now EPOCH]
scripts/git-town/doctor.sh --selftest
```

`doctor.sh` runs fixed Git commands and nothing else; `lease.py` is the typed
judge and the lease store. The split follows the fixed-entrypoint law in
`docs/harness/README.md`: Bash orchestrates Git, Python validates structure.

`lease.py` also exposes the lease primitives directly for #18 and #19:

```bash
python scripts/git-town/lease.py acquire|renew|release|inspect --lease-root DIR ...
```

## Result vocabulary

| Condition | Result |
| --- | --- |
| linked worktree, admitted remote, clean tree, lease taken | `PASS` |
| uncommitted entries, or a merge/rebase/cherry-pick/revert/bisect in progress | `BLOCKED_DIRTY` |
| branch lease held elsewhere, path overlaps a live lease, or lease expired | `BLOCKED_BRANCH_LEASE` |
| worktree is on a branch other than the packet head, or HEAD is detached | `BLOCKED_ANCESTRY` |
| primary checkout, wrong repository, credential-bearing remote, missing prompt policy, unresolved selector, unsupported argument | `BLOCKED_POLICY` |

## Signal → action

**Signal: a Worker is about to synchronize.**
Run `doctor.sh` from the linked worktree. A `PASS` receipt carries the lease
expiry that bounds the whole execution window; #18 must not start a sync whose
timeout outlives it.

**Signal: you are not sure this is a linked worktree.**
That is exactly the first check, and it runs before anything else that could
mutate state. A linked worktree has its own git dir; in the primary checkout
`--absolute-git-dir` and `--git-common-dir` resolve to the same path. Checking
a directory name or a configured root would pass in a copied tree.

**Signal: two Workers might collide.**
The lease store is the arbiter, and it uses the *same* overlap function as the
task-packet validator — imported, not re-implemented. Two independent
definitions of "overlap" is how a lease system quietly stops holding: both
sides stay green while the trees collide.

**Signal: the remote might carry a credential.**
The URL travels on stdin, never in argv, because argv is visible in the process
table and a credential-bearing remote is precisely what this check exists to
catch. Putting it in argv would leak the secret in the act of rejecting it.
Receipts and rejection reasons carry scheme and host only.

**Signal: an execution window ran long.**
An expired lease does not renew. The window it guarded is gone and another
Worker may already have acted on that assumption, so renewal would be a claim
about the past. The paths do become free for a fresh acquisition.

## Non-interactive policy by name only

`GIT_TERMINAL_PROMPT`, `GIT_PAGER` and `GIT_EDITOR` must be present. The doctor
reports which names are set and never their values — a receipt that echoed a
value would turn the environment into tracked data. Absence is
`BLOCKED_POLICY`, not a warning: a prompt inside a bounded background run is a
hang, not a question.

## Deliberate boundaries

- No ref is read for ancestry beyond the current branch name. Parent/base graph
  verification is #18's post-sync lane; asserting it here would be a preflight
  claiming a postcondition.
- Lease liveness is wall-clock only. There is no process-liveness probe, so a
  crashed Worker holds its lease until expiry. `--ttl-seconds` is the knob that
  trades recovery latency against safety; shorten it rather than adding a
  heuristic that guesses whether a holder is alive.
- The lease root is resolved from the logical selector
  `HOST_LLM_ARBITRAGE_LEASES` (`lease_root_selector` in
  `docs/git/REPO_PROFILE.md`). No host-specific absolute path is committed, and
  an unresolved selector is a block rather than a default.
