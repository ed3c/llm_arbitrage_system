# Git Town exact-tool admission

## Decision

```text
required release: v24.0.0
upstream repo:   git-town/git-town
immutable tag:   0f3e55f5a6bae5b319dd713a0606263d0551af66
release ID:      358702660
live admission:  ADMITTED for darwin_arm64
receipt:         eda73fccce27c0885f82d25ef8f6b2fa82047b075e334b22e03c06bb33e7051d
owner issue:     #15 (closed)
```

Admission is host-bound. This records one machine. Any other platform or
architecture must run `scripts/git-town/admit.sh` and produce its own receipt.

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

## Evidence lanes

Issue #15 required a host-bound, subject-bound receipt with every lane below. Receipt `eda73fcc` supplies all twelve for `darwin_arm64`. The exact selected artifact depends on the trusted host platform and architecture, so the repository still does not guess it for any other machine.

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

| Required lane | State | Recorded evidence |
| --- | --- | --- |
| Repository policy pins | `PASS` | profile agrees with every pin the wizard used |
| Host platform and architecture | `PASS` | `Darwin/arm64` maps to `macos_arm` |
| Artifact acquisition | `PASS` | immutable release `358702660`, asset `git-town_macos_arm_64.tar.gz`, named by `ed3c` |
| Checksums manifest | `PASS` | manifest digest matches the pinned `7532377166cb...` |
| Artifact SHA-256 | `PASS` | `0de42d52bad34316413c9d0ba0052d09d4ba8746930aa2cc6eaa5931562a91b2` |
| Installed executable SHA-256 | `PASS` | `9f3807e07a6be79e4637b140deda9dff5d3a89321b8026a2f2e4a04d2f37fa2d` |
| Executable version output | `PASS` | `Git Town 24.0.0` |
| Direct license identity | `PASS` | MIT text reviewed; digest pinned in `docs/git/REPO_PROFILE.md` |
| SBOM or transitive dependency review | `PASS` | accepted by `ed3c` |
| Required notices review | `PASS` | accepted by `ed3c` |
| Organization/legal approval | `PASS` | approved by `ed3cTheory` for release `358702660` |
| Repository config compatibility | `PASS` | `.git-town.toml` parses under the admitted executable |

Each lane's negative control lives in `tests/git-town/test_admission_receipt.py`: every one of the twelve is planted at `FAIL` and at `NOT_EXERCISED` in turn, and each is asserted to block admission on its own.

## Admission result

```text
PASS
```

The result is `PASS` only when all repository-required lanes are `PASS` for one exact host, executable, repository identity, task packet and subject. Any required `ABSENT`, `FAIL`, or `NOT_EXERCISED` lane blocks live execution — `scripts/git-town/admission_receipt.py` enforces that rule, and its controls prove each lane can block alone.

Tool presence on `PATH`, a package-manager receipt, a version string alone, or the direct MIT license alone remains insufficient. This receipt is none of those: it binds a measured artifact digest to the upstream manifest, a measured executable digest to that artifact, and three named human decisions to that exact release.

Stable blocked result, for any host without its own receipt:

```text
BLOCKED_TOOL_ADMISSION
```

## What admission does not authorize

Admission makes a live Git Town run *possible*. It does not make one *observed*, and it grants no publication or merge authority:

```text
worker_publication_enabled   still false
live canary                  NOT_EXERCISED, owned by issue #21
merge                        Human Admit, unchanged
```

## Allowed command surface after admission

The repository admits bounded synchronization only through the fixed adapter owned by issue #18, which is merged. Direct Agent execution of `git town` remains denied: the adapter builds the command shape itself, so no caller can pass an argument vector.

Point the logical selector at the admitted executable before using it:

```bash
export HOST_GIT_TOWN_BIN=/path/to/the/admitted/git-town
```

The receipt records digests, not paths — `absolute_host_paths_in_tracked_files` is denied — so the selector is resolved per host and never committed.

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
