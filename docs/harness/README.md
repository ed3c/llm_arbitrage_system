# Harness contracts

## Purpose

This directory owns fixed, typed assertions and disagreement-producing controls for repository delivery mechanisms. It does not own arbitrary command execution and it does not replace the runtime test suite.

Current Git Town Harness implementation state:

```text
task-packet validator: NOT_IMPLEMENTED (#16)
worktree/lease doctor: NOT_IMPLEMENTED (#17)
bounded sync/receipts: NOT_IMPLEMENTED (#18)
fail-closed canaries: NOT_IMPLEMENTED (#19)
publication gate: NOT_IMPLEMENTED (#20)
live convergence audit: NOT_EXERCISED (#21)
```

Tracked Markdown defines the acceptance contract. It is not a selftest receipt.

## Evidence lanes

Every Harness report keeps these fields independent:

```text
requirements_review
static_contract
mechanism_selftest
negative_or_mutation_control
live_canary
local_exact_head_repository_evals
publication_decision
remote_publication
remote_ancestry
GitHub_trusted_check
cleanup_and_residue
rollback
Human_Admit
release_or_production
```

Allowed evidence states:

```text
PASS
FAIL
ABSENT
NOT_IMPLEMENTED
NOT_EXERCISED
SKIPPED_BY_POLICY
```

## Fixed entrypoint law

Future scripts expose typed operations such as:

```text
validate_task_packet(packet_path)
doctor(worktree, packet_receipt)
sync_owned_stack(worktree, packet_receipt, admission_receipt)
verify_sync(before_receipt, after_subject)
evaluate_publication(intent, local_receipt, github_snapshot)
verify_remote(expected_head, expected_parent_graph, remote_snapshot)
```

They must not accept a free-form shell field. Bash may orchestrate fixed Git/worktree/process commands; Python should validate structured packets, receipts, graphs, paths and snapshots.

## Receipt law

Every receipt binds:

```text
schema version
repository identity
issue/task packet digest
exact commit and tree subjects
branch/parent/base
worktree and lease identities
mechanism/config/tool digests
assertion or control ID
bounded input/output digests
start/end timestamps
result state
cleanup and residue
rollback subject
```

Never persist secret values, private keys, tokens, cookies, account data, credential-bearing URLs, full environment dumps or unbounded stdout/stderr.

## Positive assertions and controls

| Mechanism | Positive assertion | Required disagreement-producing control |
| --- | --- | --- |
| Tool admission | exact release/artifact/executable/license/provenance policy | wrong version, changed digest, wrong architecture, missing legal/transitive state |
| Task packet | all fields and exact branch/path graph validate | remove each field, overlap path, wrong parent, arbitrary shell field |
| Worktree/lease doctor | isolated linked worktree and exclusive leases | primary checkout, dirty tree, duplicate/expired/overlap lease, bad remote |
| Dry-run/sync | same bounded owned stack, no prompts, no push | scope mismatch, prompt, timeout, unleased branch, remote movement |
| Post-sync verifier | ancestry, protected refs and allowed paths hold | wrong parent, protected ref movement, out-of-lease diff |
| Conflict handling | semantic conflict blocks and preserves evidence | automatic marker edit/continue/skip/undo/ship attempt |
| Cleanup | safe resources removed; blocked evidence preserved | planted residue and orphan process |
| Rollback | exact before refs and drift refusal | independently moved rollback target |
| Publication gate | one intent, exact local receipt, trusted snapshot | stale receipt, old-SHA CI, repeated feedback, billing, wrong PR graph |
| Remote verifier | fetched head and ancestry match | wrong remote/head/parent and protected rewrite |
| Convergence | all evidence lanes remain separate | omitted lane or promoted `NOT_EXERCISED` |

## Repository behavior gates

```bash
make check
make phase3-smoke
make phase4-smoke
```

These commands test Python behavior and offline flows. The Git Town Harness binds their results to an exact post-sync or post-publication head; it never treats old CI as current.

## Planned Harness file map

```text
docs/harness/
├── README.md                              this contract
├── git-town-task-packet.md                #16
├── git-town-doctor.md                     #17
├── git-town-sync.md                       #18
├── git-town-canaries.md                   #19
└── git-town-publication.md                #20

scripts/git-town/
├── task_packet.py                         #16
├── doctor.sh / lease.py                   #17
├── sync.sh / receipt.py                   #18
└── publish.sh / github_snapshot.py /
    remote_verify.py                       #20

tests/git-town/                            #16–#20
fixtures/git-town/                         #19
receipts/git-town/                         #15, #18, #20, #21
```

Absent planned paths remain `NOT_IMPLEMENTED`; do not create empty files to simulate completion.

## Human boundary

Harness results can block or provide evidence. They cannot resolve semantic conflicts, accept legal terms, change permissions/secrets/billing, mark a PR ready without the admitted gate, merge, ship, release, deploy, or perform destructive rollback.
