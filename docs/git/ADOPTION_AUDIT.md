# Git Town adoption audit

Owner issue: [#21](https://github.com/ed3c/llm_arbitrage_system/issues/21).

## Rule

No lower lane marks a higher lane. A mechanism selftest is not a live run, a
live run is not a publication, a publication is not a merge, and none of them
is Human Admit. Lanes that were not exercised say so.

## Evidence states

```text
PASS               observed, bound to an exact subject
FAIL               observed and wrong
ABSENT             the artefact does not exist
NOT_IMPLEMENTED    no mechanism exists
NOT_EXERCISED      a mechanism exists but has not been run in this lane
SKIPPED_BY_POLICY  deliberately not done
```

## Lane report

| Lane | State | Evidence |
| --- | --- | --- |
| Shared Skill resolution | `PASS` for tracked tree | `AGENTS.md` and `docs/git/README.md` point at `ed3c/skills-shared/skills/git-town-stacked-pr-worker`; no `SKILL.md` exists anywhere in this repository |
| Exact executable admission | `PASS` for `darwin_arm64` | admission receipt `eda73fcc`; artifact `0de42d52…`, executable `9f3807e0…`, output `Git Town 24.0.0` |
| Repository profile | `PASS` | `docs/git/REPO_PROFILE.md`, with digests bound to the receipt by a control |
| Repository config compatibility | `PASS` | `.git-town.toml` parses under the admitted executable and now emits no deprecation warning |
| Stack graph | `PASS` | `docs/git/STACKED_PRS.md` carries every merged PR with its exact merge subject |
| Isolated worktree and leases | `PASS` | live `doctor.sh` on two real linked worktrees, each taking an exclusive branch/path lease |
| Live dry-run | `PASS` | `sync --dry-run --stack --non-interactive --no-auto-resolve --no-push` against the admitted executable |
| Live bounded no-push sync | `PASS` (`NO_CHANGE`) | sync receipt `c5b39f8c`; head unchanged, zero verification findings, no remote ref moved |
| Independent post-sync verification | `PASS` | same receipt: current branch, perennial refs, remote-tracking refs, branch and worktree sets, tree cleanliness, ancestry, path lease |
| Cleanup and residue | `PASS` | run record reports `process_group_reaped: true`, `killed_on_timeout: false`; blocked runs preserved their evidence directories and reported the path |
| Rollback subject | `PASS` | receipt binds `59cbc6d6…` as the immutable pre-sync subject; no rollback was performed |
| Conflict / prompt / timeout canaries | `PASS` against the fixture, `NOT_EXERCISED` against Git Town | `tests/git-town/test_fail_closed_canaries.py` drives `fixtures/git-town/canary_tool.sh`; no semantic conflict has been planted into a real `git town sync` |
| Exact-head repository evals | `PASS` | ruff, strict mypy, pytest with the coverage floor, phase 3–8 smokes and the Git Town mechanism job, green on every merged head |
| Draft publication lane through the gate | `NOT_EXERCISED` | `publish.sh` has never issued an `ALLOW`; every PR in this repository was opened and merged through GitHub directly |
| Ready-for-review lane through the gate | `NOT_EXERCISED` | same |
| Post-push remote head and ancestry | `NOT_EXERCISED` | `remote_verify.py` has never run against `origin` after a real push |
| GitHub trusted check | `PASS` | required checks green on each merged exact head, read per SHA rather than per branch |
| Human Admit | `PASS` | every merge in this repository was authorized explicitly by the repository owner; no Worker marked ready, retargeted, merged or shipped on its own |
| Release / production observation | `SKIPPED_BY_POLICY` | this repository is paper-only; there is no release or production lane |

## What the live run found

Running it for real produced three findings that no fixture could have:

1. **The adapter refused the executable it had just admitted.** The policy pin
   is `v24.0.0`; `git-town --version` prints `Git Town 24.0.0`. The admission
   wizard compared against the bare number and accepted it, while the sync
   adapter compared against the pin literally and rejected it — two checks of
   one predicate, disagreeing about the same binary. The root cause was the
   fixtures: both printed `git-town v24.0.0`, a format the tool never emits.

2. **The tracked configuration used a key deprecated in v24.0.0.**
   `push-new-branches` alongside the current `share-new-branches`. Removing the
   deprecated key left `git town config` byte-identical.

3. **Nothing declared the branch parent to Git Town.** Under
   `--non-interactive`, a branch whose parent Git Town does not know fails the
   dry run outright. That refusal is correct; what was missing was the step
   saying so. `docs/git/WORKER_PROTOCOL.md` now carries it as step 1b.

Each was invisible to a green test suite. That is the argument for this issue.

## What remains unexercised, and why

The publication lanes are `NOT_EXERCISED` by choice, not by omission. Exercising
them means pushing a branch and transitioning a pull request through
`publish.sh` in order to observe the gate, then verifying the remote afterwards.
Doing that for its own sake would spend a CI run and a pull request to
demonstrate a mechanism whose controls already pass offline.

The honest state is therefore:

```text
publication decision   mechanism PASS, live lane NOT_EXERCISED
remote publication     NOT_EXERCISED
remote ancestry        NOT_EXERCISED
```

They become `PASS` the first time a real publication is driven through the gate
and verified. Until then, this document must not say otherwise.

## Admission is not adoption

Git Town `v24.0.0` is admitted on one host and has been driven through one
dry-run and one bounded no-push sync. That is adoption of the *synchronization*
lane on `darwin_arm64`. It is not:

```text
adoption on any other host          each needs its own admission receipt
adoption of the publication lane    NOT_EXERCISED above
authority to merge                  Human Admit, unchanged
authority to push                   worker_publication_enabled is still false
```
