# Harness — fail-closed canaries (#19)

Control owner for evidence lanes E08 and E09 in `docs/git/EVALS.md`. The
mechanisms under test belong to #17 and #18; this module owns the planted
disagreements that prove they refuse.

## Implementation state

```text
negative_or_mutation_control:  PASS  tests/git-town/test_fail_closed_canaries.py
fixture:                       PASS  fixtures/git-town/canary_tool.sh
cleanup_and_residue:           PASS  covered by the orphan and evidence canaries
rollback:                      PASS  covered by the drift canaries
live_canary:                   NOT_EXERCISED  (#21)
```

`NOT_EXERCISED` above is not a formality. These canaries drive a fixture, not
Git Town. They prove the adapter fails closed against the conditions the
protocol names; they do not prove Git Town produces those conditions the way
the fixture does. That remains issue #21's lane.

## Why a fixture instead of the real tool

A green happy path proves nothing about failing closed. Git Town is not
admitted on any host (`live_execution_admitted: false`, #15), and even once it
is, a real binary cannot be asked to produce a semantic conflict, an editor
prompt, a credential prompt, a hang, an orphaned grandchild, a moved perennial
ref and leftover residue on demand. `fixtures/git-town/canary_tool.sh` can, and
it does so deterministically, so each control disagrees for exactly one reason.

## The canaries

| Planted condition | Expected outcome |
| --- | --- |
| conflict markers, `MERGE_HEAD`, conflict text, exit 1 | `BLOCKED_CONFLICT` |
| conflict markers and `MERGE_HEAD`, **no output, exit 0** | `BLOCKED_CONFLICT` |
| editor wait message | `BLOCKED_PROMPT` |
| credential request | `BLOCKED_PROMPT` |
| never returns | `BLOCKED_TIMEOUT` |
| spawns a grandchild, then hangs | `BLOCKED_TIMEOUT`, session reaped |
| leaves the tree uncommitted, exit 0 | `FAILED_EVAL` |
| moves `main`, exit 0 | `FAILED_EVAL` |
| leaves a stray file, exit 0 | `FAILED_EVAL` |
| head moved independently after the receipt | `ROLLBACK_REFUSED_DRIFT` |
| rollback subject no longer reachable | `ROLLBACK_REFUSED_DRIFT` |

The silent conflict is the important one. It exits zero and says nothing while
leaving the tree unmergeable, so any adapter that reads tool exit status as the
repository result passes it. `docs/git/WORKER_PROTOCOL.md` step 4 says exactly
this — "Tool exit status alone is not the repository result" — and this is the
control that holds it to it.

## Signal → action

**Signal: a mechanism went green and you want to believe it.**
Ask which planted condition would have turned it red. Every control here names
one. A mechanism with no control that produces disagreement is a single
attestation wearing a test's clothes.

**Signal: you are about to trust a cleanup or reaping claim.**
`test_the_orphan_behaviour_really_orphans_without_reaping` runs the fixture the
naive way — killing only the direct child — and asserts the grandchild is still
alive afterwards. Without it, `process_group_reaped: true` could be reporting
on a condition that never existed. That control is what makes the reaping
control mean anything.

This is not hypothetical: writing it found that the residue poll ran while the
direct child was still an unreaped zombie, and a zombie keeps its group alive,
so `process_group_reaped` came back `false` on every timeout. A permanent false
alarm is as useless as never reporting residue at all.

**Signal: a run blocked and you want to clean up.**
Do not. `test_conflict_evidence_is_preserved_not_repaired` asserts the conflict
markers and `MERGE_HEAD` are still present after a blocked run, and
`test_a_blocked_run_preserves_its_evidence_directory` asserts the intermediate
evidence survives with its path reported. A clean run does remove its evidence
directory, and there is a control for that too, so "preserve everything always"
is not the answer either.

**Signal: something wants to unstick a blocked run.**
Nothing may. The canaries assert the only shapes ever sent to the tool are the
two admitted `sync` shapes, and that no adapter source contains
`town continue`, `town skip`, `town undo`, `town ship`, `push --force`,
`--force-with-lease`, `reset --hard`, `branch -D` or `clean -fd`. The fixture
is held to the same rule, so a canary cannot repair the condition it planted.

**Signal: a rollback looks safe.**
It is only safe if nothing moved. The drift canaries move the branch
independently after the receipt was written, and confirm the proposal is
refused with `proposal: null`. A receipt that no longer describes the world
would restore over a change nobody has looked at.

## The canaries can themselves fail

`test_an_unknown_canary_behaviour_is_a_tool_failure` asserts the fixture
refuses an unrecognized behaviour rather than silently succeeding. If it
succeeded, a typo in any control's behaviour name would turn that control into
a green test that plants nothing.

## Deliberate boundaries

- No canary asserts anything about Git Town's real behaviour, remote state,
  CI, or Human Admit. Those are higher lanes and cannot be reached from here.
- The fixture is not a Git Town emulator. It reproduces the *conditions* the
  protocol enumerates, not the tool's semantics.
