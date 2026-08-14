# Harness — task-packet and path-lease validator (#16)

Mechanism owner for evidence lane E04 in `docs/git/EVALS.md`. The acceptance
contract is `docs/git/TASK_PACKET.md`; this file records how to trigger the
mechanism, what it does, and why each control earns its cost.

## Implementation state

```text
mechanism_selftest:            PASS      scripts/git-town/task_packet.py --selftest
negative_or_mutation_control:  PASS      tests/git-town/test_task_packet.py
static_contract:               PASS      docs/git/TASK_PACKET.md
live_canary:                   NOT_EXERCISED  (#21)
```

The validator refuses packets. It does not create branches, touch worktrees,
run Git Town, publish, or merge. A `PASS` here is a precondition for the
Worker, never an admission to act.

## Fixed entrypoint

```bash
python scripts/git-town/task_packet.py --packet PACKET.yaml \
  [--sibling-lease LEASE.json ...] \
  [--emit-canonical CANONICAL.json] [--emit-lease LEASE.json]
python scripts/git-town/task_packet.py --selftest
```

There is no free-form command field, by construction: the schema is closed and
any undeclared key is rejected. `--sibling-lease` consumes the same manifest
`--emit-lease` produces, so one admitted Worker's lease is literally the input
that blocks the next Worker from claiming its paths.

Exit status is `0` only for `PASS`. Stdout is always one canonical receipt
(sorted keys, no whitespace) so it can be digested without re-serialization;
the human-readable reason goes to stderr and never contaminates the digest.

## Result vocabulary

| Condition | Result |
| --- | --- |
| every law holds | `PASS` |
| missing, empty or wrongly typed required field | `BLOCKED_TASK_PACKET` |
| branch, parent, dependency or stack-class graph disagrees | `BLOCKED_ANCESTRY` |
| branch lease held, or an allowed path overlaps a live lease | `BLOCKED_BRANCH_LEASE` |
| unsafe command, push, conflict, rollback or host-path request | `BLOCKED_POLICY` |
| tool profile absent or exact admission waived | `BLOCKED_TOOL_ADMISSION` |

## Signal → action

**Signal: a packet is about to authorize branch work.**
Run the entrypoint and keep the receipt. Without a `PASS` receipt bound to the
packet digest, the downstream doctor (#17) and sync (#18) have nothing to bind
their subjects to, and their own receipts become unfalsifiable.

**Signal: two Workers might want the same files.**
Pass every live `--emit-lease` manifest as `--sibling-lease`. Overlap is
computed on path geometry, not on branch names: `scripts/**` and
`scripts/git-town/task_packet.py` overlap even though neither string contains
the other's branch. Name-based lease checks pass while the trees collide.

**Signal: a packet grew a new field.**
The removal controls are generated from the schema itself, so a field added to
`_SECTIONS` immediately gains its own "remove this field" control. A new
required field with no control is therefore not possible by forgetting; it is
only possible by editing the schema without editing the schema.

**Signal: the validator went green and you want to trust it.**
`--selftest` plants five mutations (push enabled, perennial parent, mismatched
branch lease, removed field, injected shell field) and fails if any of them
validates. A green run that never proved it can go red is a single-attestation
claim; this makes the red path part of the same command.

## Why the digest is computed after normalization

`packet_sha256` is taken over the canonical form the validator builds, not over
the source YAML bytes. Two packets that differ only in key order, list order of
paths, or comments produce the same digest, so a receipt stays bound to the
packet's meaning rather than to its formatting. Reformatting a packet must not
silently invalidate every receipt that referenced it; conversely, changing one
allowed path must change the digest, which it does.

## Deliberate boundaries

- Issue existence is not verified against GitHub. The validator is offline and
  network-free by design; issue resolution belongs to the publication gate
  (#20), which already holds a trusted GitHub snapshot. Claiming issue
  existence here would be a lower lane asserting a higher lane's evidence.
- Branch existence is not verified against the local repository. Branch and
  worktree reality is issue #17's lane; this mechanism validates the declared
  graph's internal consistency only.
- The state tables in `docs/harness/README.md`, `docs/git/EVALS.md`,
  `docs/git/WORKER_PROTOCOL.md` and `docs/git/REPO_PROFILE.md` are owned by the
  convergence slice. This mechanism does not promote its own lane there.
