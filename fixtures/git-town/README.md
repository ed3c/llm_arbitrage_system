# Git Town canary fixtures

`canary_tool.sh` is a deterministic stand-in for the Git Town executable, used
by `tests/git-town/test_fail_closed_canaries.py` (issue #19).

It exists because a green happy path proves nothing about failing closed. Git
Town is not admitted on any host (`live_execution_admitted: false`, issue #15),
and even once it is, a real binary cannot be asked to produce a semantic
conflict, an editor prompt, a credential prompt, a hang, an orphaned process, a
moved perennial ref and leftover residue on demand. The fixture can.

```text
CANARY_BEHAVIOUR      which condition to produce
CANARY_VERSION        version string reported by --version (default v24.0.0)
CANARY_INVOCATION_LOG appended with each invocation's exact argument shape
CANARY_ORPHAN_PID_FILE where the orphan behaviour records its grandchild pid
```

| Behaviour | Condition produced | Expected adapter result |
| --- | --- | --- |
| `clean` | up-to-date, no change | `PASS` |
| `semantic-conflict` | conflict markers, `MERGE_HEAD`, conflict text, exit 1 | `BLOCKED_CONFLICT` |
| `silent-conflict` | conflict markers and `MERGE_HEAD`, no output, exit 0 | `BLOCKED_CONFLICT` |
| `editor-prompt` | editor wait message, exit 1 | `BLOCKED_PROMPT` |
| `credential-prompt` | credential request, exit 1 | `BLOCKED_PROMPT` |
| `hang` | never returns | `BLOCKED_TIMEOUT` |
| `orphan` | spawns a grandchild, then hangs | `BLOCKED_TIMEOUT` with the session reaped |
| `dirty` | leaves the tree uncommitted, exit 0 | `FAILED_EVAL` |
| `ref-move` | moves `main`, exit 0 | `FAILED_EVAL` |
| `residue` | leaves a stray file, exit 0 | `FAILED_EVAL` |

`silent-conflict` is the important one: it exits zero and says nothing while
leaving the tree unmergeable. Any adapter that reads tool exit status as the
repository result passes it.

The fixture never edits a conflict marker, continues, skips, undoes, ships,
resets, deletes a branch or pushes. Neither may the adapter — the canaries
assert that the only shapes ever sent to the tool are the two admitted `sync`
shapes.
