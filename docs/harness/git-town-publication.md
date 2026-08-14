# Harness — publication gate and remote verifier (#20)

Mechanism owner for evidence lanes E11 and E12 in `docs/git/EVALS.md`. The
acceptance contract is `docs/git/PUBLICATION.md`.

## Implementation state

```text
mechanism_selftest:            PASS  scripts/git-town/github_snapshot.py --selftest
                                     scripts/git-town/remote_verify.py --selftest
                                     scripts/git-town/publish.sh --selftest
negative_or_mutation_control:  PASS  tests/git-town/test_publication_gate.py
static_contract:               PASS  docs/git/PUBLICATION.md
remote_publication:            NOT_EXERCISED  performed by a human, never here
live_canary:                   NOT_EXERCISED  (#21)
```

## Signal → action

**Signal: local work is green and you want to publish.**
Run the gate. It needs three things that must agree: the working repository's
head, the local sync receipt's `after_subject`, and the snapshot's `head_sha`
and `workflow.head_sha`. Any disagreement is `BLOCKED_STALE_EVIDENCE`. Old-SHA
CI passing is the most common way a publication looks safe and is not.

**Signal: you want the gate to check GitHub for you.**
It will not. The gate is offline by construction: a snapshot is captured out of
band and handed in, so the decision is reproducible and a network hiccup cannot
be mistaken for a policy answer. A snapshot missing any guard field is
`BLOCKED_POLICY` — an absent guard is not a soft state.

**Signal: the same decision is still sitting in your shell history.**
It is spent. `publish.sh` records the decision digest in the ledger before
returning it, so a replay is `BLOCKED_POLICY`. The digest covers the head, so a
new head is a new decision rather than a reuse of the old one — which is what
makes the ledger a spend record and not a cache.

**Signal: the push exited zero.**
That is a claim about your machine. `--verify-remote` fetches through the
admitted remote and compares the remote head, the declared parent ancestry and
protected-ref immutability against the refs recorded before the operation.
Without the explicit fetch, every comparison reads stale local knowledge of the
remote and agrees with itself, which is a check that can only ever pass.

**Signal: the remote URL looks admitted.**
It is checked as Git resolves it, so an `insteadOf` rewrite cannot point an
admitted URL at an unadmitted host. The tests widen the admitted set rather
than redirecting a URL, precisely so this property is not weakened to make a
fixture convenient.

**Signal: a background worker wants to publish.**
There is no intent it may request. `background_push`,
`background_pr_ready_transition` and `background_workflow_rerun` are all denied
in `docs/git/REPO_PROFILE.md`, so background is refused before the intent is
even examined. It may prepare a proposal and a snapshot for a human.

## What the gate cannot do

- It cannot push, open a pull request, mark one ready, rerun a workflow, or
  merge. `test_publish_never_pushes_or_merges` asserts the source contains no
  `git push`, `gh pr merge`, `gh pr ready`, `gh workflow run` or `--force`.
- An `ALLOW` is not merge or promotion authority. Every decision carries
  `requires_human_admit_for` naming merge, permission changes, billing
  recovery, release promotion and production deployment.
- It cannot mark `remote publication` as `PASS`. That lane is performed by a
  human or operator and is verified separately by `--verify-remote`; the
  decision lane and the remote lane never collapse into one another.

## CI

The `Git Town delivery mechanisms` job runs every bundled `--selftest` and the
whole `tests/git-town` suite. It is a separate job rather than extra steps in
`Quality gates` so the delivery mechanisms fail on their own line, and so the
phase stack's own smoke steps and this job do not contend for the same region
of `.github/workflows/ci.yml`.
