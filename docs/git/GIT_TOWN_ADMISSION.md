# Git Town exact-tool admission

## Decision

```text
required release: v24.0.0
upstream repo:   git-town/git-town
immutable tag:   0f3e55f5a6bae5b319dd713a0606263d0551af66
release ID:      358702660
live admission:  BLOCKED
owner issue:     #15
```

This document records the repository policy pin. It is not a host admission receipt and does not authorize execution.

## Static upstream evidence

| Evidence | Value | State |
| --- | --- | --- |
| Tag | `v24.0.0` | `PASS` for upstream reference |
| Tag target commit | `0f3e55f5a6bae5b319dd713a0606263d0551af66` | `PASS` for upstream reference |
| GitHub release ID | `358702660` | `PASS` for upstream reference |
| Release mutability metadata | upstream release reports immutable | `PASS` for static metadata only |
| `checksums.txt` release-asset digest | `7532377166cb59dc01c74f86e3a71c54ba9567a461313a5d203a1ea99c571b24` | `PASS` for manifest asset metadata |
| Direct license | MIT | `PASS` for direct license text |
| License blob SHA | `4bcd5ec1942737f7976b8bac8534a8ab642ec0e0` | `PASS` for upstream Git object |
| License text SHA-256 | `eec8a092b92231375231488d27b959e2fa2be80559c97db60c1b0458d3298791` | `PASS` for reviewed direct text |

Upstream references:

- [release v24.0.0](https://github.com/git-town/git-town/releases/tag/v24.0.0)
- [tagged source](https://github.com/git-town/git-town/tree/v24.0.0)
- [direct license](https://github.com/git-town/git-town/blob/v24.0.0/LICENSE)
- [shared Worker Skill](https://github.com/ed3c/skills-shared/tree/main/skills/git-town-stacked-pr-worker)

## Evidence that is still required

Issue #15 must create a host-bound, subject-bound receipt with every lane below. The exact selected artifact depends on the trusted host platform and architecture, so the repository does not guess it.

## How to produce the receipt

```bash
scripts/git-town/admit.sh
```

Ten stages. It measures everything measurable on the host — platform and architecture, the checksums manifest against the digest pinned here, the selected artifact's SHA-256 against that manifest, the extracted executable's digest, its `--version` output, and whether `.git-town.toml` parses under it — and asks a human only for the four decisions this issue defers to a person:

```text
who names the acquisition method, and which exact asset
who owns the SBOM/transitive review, and their decision
who owns the required-notices review, and their decision
who accepts on behalf of the organization
```

Answering `SKIP`, or giving an owner without a decision, records that lane as `NOT_EXERCISED`. **No lane is ever defaulted to `PASS`.** The wizard re-reads the pins above from `docs/git/REPO_PROFILE.md` and stops if they have drifted from its own copies, so it cannot admit against a policy it no longer matches.

`scripts/git-town/admission_receipt.py` turns the resulting lane ledger into one content-addressed, read-only receipt under `receipts/git-town/admission/`. Its `--selftest` plants every required lane at `FAIL` and at `NOT_EXERCISED`, one at a time, and asserts each one blocks admission on its own; `tests/git-town/test_admission_receipt.py` runs the same controls in CI.

The wizard installs nothing system-wide, commits no binary, and deletes nothing: downloaded artifacts and the lane ledger are left in a scratch directory as evidence. Receipts record digests only — no absolute host paths, which `docs/git/REPO_PROFILE.md` denies in tracked files.

Nothing about this entrypoint substitutes for the decisions. It makes them recordable in one sitting; a human still makes them.

| Required lane | Current state | Positive assertion | Negative control |
| --- | --- | --- | --- |
| Host platform and architecture | `NOT_EXERCISED` | selected release artifact matches host | wrong architecture is rejected |
| Artifact acquisition | `NOT_EXERCISED` | immutable release source and bounded acquisition record | mutable `latest` selector is rejected |
| Artifact SHA-256 | `NOT_EXERCISED` | selected artifact matches upstream checksum manifest | one-byte/digest mutation is rejected |
| Installed executable SHA-256 | `NOT_EXERCISED` | installed bytes match the admitted artifact/extraction contract | substituted executable is rejected |
| Executable version output | `NOT_EXERCISED` | exact output resolves to `v24.0.0` | version mismatch is rejected |
| Direct license identity | `PASS` for source text, host receipt absent | receipt binds reviewed license bytes | changed license digest is rejected |
| SBOM or transitive dependency review | `NOT_EXERCISED` | named owner and artifact review state exist | missing mandatory state blocks admission |
| Required notices review | `NOT_EXERCISED` | named owner records notices decision | missing notice state blocks admission |
| Organization/legal approval | `NOT_EXERCISED` | owner-authored approval binds exact release/artifact | tool presence cannot substitute for approval |
| Repository config compatibility | `OPEN` | `.git-town.toml` parses under admitted version | unknown key/value mutation fails |

## Admission result

The result is `PASS` only when all repository-required lanes are `PASS` for one exact host, executable, repository identity, task packet and subject. Any required `ABSENT`, `FAIL`, or `NOT_EXERCISED` lane blocks live execution.

Stable blocked result:

```text
BLOCKED_TOOL_ADMISSION
```

Tool presence on `PATH`, a package-manager receipt, a version string alone, or the direct MIT license alone is insufficient.

## Allowed command surface after admission

The repository admits bounded synchronization only through a fixed adapter owned by issue #18. Direct Agent execution remains denied until that adapter and its controls merge.

The intended command shapes are:

```bash
git town sync --stack --dry-run --non-interactive --no-auto-resolve --no-push
git town sync --stack --non-interactive --no-auto-resolve --no-push
```

The live command may run only after:

```text
valid task packet
exact branch/parent graph
linked worktree admission
branch and path leases
clean-state check
credential-free admitted remote
dry-run scope match
hard timeout
```

## Prohibited commands and behaviors

Workers cannot invoke or automate:

```text
git town continue
git town skip
git town undo
git town ship
automatic semantic conflict edits
raw reset/delete/force push
protected branch rewrite
merge or merge-queue admission
```

A conflict preserves the worktree and receipt for Human Admit. Rollback uses immutable recorded refs and must refuse drift; automatic `git town undo` is not the rollback policy.

## Receipt location

Planned logical location:

```text
receipts/git-town/admission/<subject-digest>.json
```

Current state:

```text
receipt mechanism: NOT_IMPLEMENTED
host receipt:      NOT_EXERCISED
owner:             issue #15
```

Do not commit the executable, downloaded archive, package-manager cache, host path, token, cookie, credential URL, private key, or unbounded command stream.
