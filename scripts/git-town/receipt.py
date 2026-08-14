#!/usr/bin/env python3
"""Bounded sync executor, independent verifier and append-only receipts (#18).

Three typed operations, no free-form command field anywhere:

``capture``  read repository evidence with fixed Git commands
``sync``     run one fixed Git Town command shape under a hard timeout
``verify``   assert the postconditions in ``docs/git/WORKER_PROTOCOL.md`` step 5
``append``   add one immutable entry to the receipt ledger

The command shape is built here from ``docs/git/REPO_PROFILE.md``; the caller
selects a mode, never an argument vector. Streams never reach a receipt raw:
they are digested, bounded and redacted first.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lease import DoctorRejected
from task_packet import _leases_overlap as leases_overlap
from task_packet import canonical_bytes

EVIDENCE_SCHEMA = "llm-arbitrage/sync-evidence/v1"
RUN_SCHEMA = "llm-arbitrage/sync-run/v1"
VERIFY_SCHEMA = "llm-arbitrage/sync-verification/v1"
LEDGER_SCHEMA = "llm-arbitrage/sync-receipt/v1"

PERENNIAL_BRANCHES = ("main",)
REQUIRED_GIT_TOWN_VERSION = "v24.0.0"

# docs/git/REPO_PROFILE.md sync.dry_run_command_shape / live_command_shape.
BASE_SYNC_FLAGS = ("sync", "--stack", "--non-interactive", "--no-auto-resolve", "--no-push")
DRY_RUN_FLAG = "--dry-run"

MAX_STREAM_EXCERPT_BYTES = 2048

RESULT_SYNCED = "SYNCED"
RESULT_NO_CHANGE = "NO_CHANGE"
RESULT_BLOCKED_CONFLICT = "BLOCKED_CONFLICT"
RESULT_BLOCKED_PROMPT = "BLOCKED_PROMPT"
RESULT_BLOCKED_TIMEOUT = "BLOCKED_TIMEOUT"
RESULT_BLOCKED_DIRTY = "BLOCKED_DIRTY"
RESULT_BLOCKED_POLICY = "BLOCKED_POLICY"
RESULT_BLOCKED_TOOL_ADMISSION = "BLOCKED_TOOL_ADMISSION"
RESULT_FAILED_TOOL = "FAILED_TOOL"
RESULT_FAILED_EVAL = "FAILED_EVAL"
RESULT_PASS = "PASS"

_CREDENTIAL_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s@]*:[^/\s@]*@", re.IGNORECASE)
_PROMPT_MARKERS = (
    "username for",
    "password for",
    "passphrase",
    "terminal prompts disabled",
    "please enter",
    "press enter",
    "waiting for your editor",
    "hit return",
)
_CONFLICT_MARKERS = (
    "conflict",
    "fix conflicts",
    "unmerged paths",
    "automatic merge failed",
)


class SyncRejected(Exception):
    """One stable result plus a human-readable reason."""

    def __init__(self, result: str, reason: str) -> None:
        super().__init__(reason)
        self.result = result
        self.reason = reason


# --- fixed Git readers ---------------------------------------------------


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if check and completed.returncode != 0:
        raise SyncRejected(
            RESULT_FAILED_TOOL,
            f"git {' '.join(arguments)} failed: {redact(completed.stderr).strip()}",
        )
    return completed.stdout.strip()


def _ref_map(repository: Path, pattern: str) -> dict[str, str]:
    listing = _git(repository, "for-each-ref", "--format=%(refname) %(objectname)", pattern)
    refs: dict[str, str] = {}
    for line in listing.splitlines():
        name, _, sha = line.partition(" ")
        if name:
            refs[name] = sha
    return refs


def _worktree_branches(repository: Path) -> list[str]:
    # Branch names only. Worktree paths are host-specific and are denied in
    # tracked receipts by docs/git/REPO_PROFILE.md.
    branches = [
        line.removeprefix("branch ").strip()
        for line in _git(repository, "worktree", "list", "--porcelain").splitlines()
        if line.startswith("branch ")
    ]
    return sorted(branches)


def capture_evidence(repository: Path, head_branch: str) -> dict[str, Any]:
    """Everything the verifier compares, read with fixed Git commands only."""

    current_branch = _git(repository, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    return {
        "schema": EVIDENCE_SCHEMA,
        "head_branch": head_branch,
        "current_branch": current_branch or None,
        "head_sha": _git(repository, "rev-parse", "HEAD"),
        "tree_sha": _git(repository, "rev-parse", "HEAD^{tree}"),
        "perennial_refs": {
            name: sha
            for name, sha in _ref_map(repository, "refs/heads/").items()
            if name.removeprefix("refs/heads/") in PERENNIAL_BRANCHES
        },
        "remote_refs": _ref_map(repository, "refs/remotes/"),
        "local_branches": sorted(_ref_map(repository, "refs/heads/")),
        "worktree_branches": _worktree_branches(repository),
        "porcelain_entries": len(
            [line for line in _git(repository, "status", "--porcelain").splitlines() if line]
        ),
        "result": RESULT_PASS,
    }


# --- bounded execution ---------------------------------------------------


def redact(stream: str) -> str:
    return _CREDENTIAL_URL.sub("<redacted-credential>@", stream)


def _stream_record(label: str, stream: str) -> dict[str, Any]:
    import hashlib

    raw = stream.encode("utf-8", errors="replace")
    excerpt = redact(stream)[:MAX_STREAM_EXCERPT_BYTES]
    return {
        "stream": label,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "truncated": len(raw) > MAX_STREAM_EXCERPT_BYTES,
        "excerpt": excerpt,
    }


def command_shape(tool: Path, *, dry_run: bool) -> list[str]:
    """The one shape this adapter may run. Callers pick a mode, not arguments."""

    flags = list(BASE_SYNC_FLAGS)
    if dry_run:
        flags.insert(1, DRY_RUN_FLAG)
    return [str(tool), *flags]


def _admit_tool(tool: Path, environment: Mapping[str, str]) -> str:
    if not tool.is_file():
        raise SyncRejected(RESULT_BLOCKED_TOOL_ADMISSION, f"git town executable is absent: {tool.name}")
    completed = subprocess.run(
        [str(tool), "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=dict(environment),
    )
    reported = f"{completed.stdout} {completed.stderr}"
    if REQUIRED_GIT_TOWN_VERSION not in reported:
        raise SyncRejected(
            RESULT_BLOCKED_TOOL_ADMISSION,
            f"git town version output does not contain {REQUIRED_GIT_TOWN_VERSION}",
        )
    return REQUIRED_GIT_TOWN_VERSION


def _classify(streams: str, *, returncode: int, repository: Path) -> str:
    lowered = streams.lower()
    if any(marker in lowered for marker in _PROMPT_MARKERS):
        return RESULT_BLOCKED_PROMPT
    if any(marker in lowered for marker in _CONFLICT_MARKERS):
        return RESULT_BLOCKED_CONFLICT
    git_dir = Path(_git(repository, "rev-parse", "--absolute-git-dir"))
    if (git_dir / "MERGE_HEAD").exists() or (git_dir / "rebase-merge").exists():
        return RESULT_BLOCKED_CONFLICT
    if returncode != 0:
        return RESULT_FAILED_TOOL
    return RESULT_PASS


def run_sync(
    *, tool: Path, repository: Path, dry_run: bool, timeout_seconds: int, environment: Mapping[str, str]
) -> dict[str, Any]:
    """Run the fixed command shape once, bounded, and classify the outcome."""

    if timeout_seconds <= 0:
        raise SyncRejected(RESULT_BLOCKED_POLICY, "a bounded run requires a positive timeout")
    version = _admit_tool(tool, environment)
    shape = command_shape(tool, dry_run=dry_run)

    try:
        completed = subprocess.run(
            shape,
            cwd=repository,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env=dict(environment),
        )
    except subprocess.TimeoutExpired as expired:
        return {
            "schema": RUN_SCHEMA,
            "mode": "dry-run" if dry_run else "live",
            "tool_version": version,
            "command_shape": shape[1:],
            "exit_code": None,
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
            "streams": [
                _stream_record("stdout", (expired.stdout or b"").decode("utf-8", "replace")),
                _stream_record("stderr", (expired.stderr or b"").decode("utf-8", "replace")),
            ],
            "result": RESULT_BLOCKED_TIMEOUT,
        }

    return {
        "schema": RUN_SCHEMA,
        "mode": "dry-run" if dry_run else "live",
        "tool_version": version,
        "command_shape": shape[1:],
        "exit_code": completed.returncode,
        "timed_out": False,
        "timeout_seconds": timeout_seconds,
        "streams": [
            _stream_record("stdout", completed.stdout),
            _stream_record("stderr", completed.stderr),
        ],
        "result": _classify(
            f"{completed.stdout}\n{completed.stderr}",
            returncode=completed.returncode,
            repository=repository,
        ),
    }


# --- independent verification --------------------------------------------


def _path_is_leased(path: str, allowed: Sequence[str], excluded: Sequence[str]) -> bool:
    if any(leases_overlap(pattern, path) for pattern in excluded):
        return False
    return any(leases_overlap(pattern, path) for pattern in allowed)


def verify_sync(
    *,
    repository: Path,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    allowed_paths: Sequence[str],
    excluded_paths: Sequence[str],
    dry_run_record: Mapping[str, Any] | None = None,
    live_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assert every postcondition independently of the shell that mutated."""

    findings: list[str] = []
    head_branch = str(before["head_branch"])

    if after["head_branch"] != head_branch:
        findings.append("after evidence describes a different head branch than before evidence")
    if after["current_branch"] != head_branch:
        findings.append(f"current branch is {after['current_branch']}, not the declared head {head_branch}")
    if after["perennial_refs"] != before["perennial_refs"]:
        findings.append("a perennial ref moved during a no-push sync")
    if after["remote_refs"] != before["remote_refs"]:
        findings.append("a remote-tracking ref moved during a no-push sync")
    if after["local_branches"] != before["local_branches"]:
        findings.append("the local branch set changed unexpectedly")
    if after["worktree_branches"] != before["worktree_branches"]:
        findings.append("the worktree set changed unexpectedly")
    if int(after["porcelain_entries"]) != 0:
        findings.append(f"{after['porcelain_entries']} uncommitted entries remain after synchronization")

    if dry_run_record is not None and live_record is not None:
        if dry_run_record["command_shape"] == live_record["command_shape"]:
            findings.append("the live command shape is identical to the dry run and omits --dry-run")
        elif [flag for flag in dry_run_record["command_shape"] if flag != DRY_RUN_FLAG] != list(
            live_record["command_shape"]
        ):
            findings.append("the live command scope differs from the dry run beyond --dry-run")
        if dry_run_record["tool_version"] != live_record["tool_version"]:
            findings.append("the live run used a different tool version than the dry run")
        for record in (dry_run_record, live_record):
            if "--no-push" not in record["command_shape"]:
                findings.append(f"the {record['mode']} command omits --no-push")
            if "--no-auto-resolve" not in record["command_shape"]:
                findings.append(f"the {record['mode']} command omits --no-auto-resolve")

    before_sha = str(before["head_sha"])
    after_sha = str(after["head_sha"])
    changed_paths: list[str] = []
    if before_sha == after_sha:
        outcome = RESULT_NO_CHANGE
    else:
        outcome = RESULT_SYNCED
        ancestry = subprocess.run(
            ["git", "-C", str(repository), "merge-base", "--is-ancestor", before_sha, after_sha],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if ancestry.returncode != 0:
            findings.append("the after head does not descend from the pre-sync subject")
        changed_paths = [
            path
            for path in _git(repository, "diff", "--name-only", before_sha, after_sha).splitlines()
            if path
        ]
        for path in changed_paths:
            if not _path_is_leased(path, allowed_paths, excluded_paths):
                findings.append(f"changed path outside the lease: {path}")

    return {
        "schema": VERIFY_SCHEMA,
        "head_branch": head_branch,
        "before_head_sha": before_sha,
        "after_head_sha": after_sha,
        "changed_paths": sorted(changed_paths),
        "rollback_subject": before_sha,
        "findings": findings,
        "result": RESULT_FAILED_EVAL if findings else outcome,
    }


# --- append-only ledger --------------------------------------------------


def append_receipt(receipts_root: Path, entry: Mapping[str, Any]) -> Path:
    """One immutable file per receipt. Nothing is ever rewritten in place."""

    import hashlib

    receipts_root.mkdir(parents=True, exist_ok=True)
    body = canonical_bytes(entry)
    digest = hashlib.sha256(body).hexdigest()
    path = receipts_root / f"{digest}.json"
    if path.exists():
        # Same bytes, same name: an identical receipt is already recorded.
        return path
    path.write_bytes(body + b"\n")
    path.chmod(0o444)
    return path


def build_ledger_entry(
    *,
    head_branch: str,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    dry_run_record: Mapping[str, Any],
    live_record: Mapping[str, Any],
    verification: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": LEDGER_SCHEMA,
        "head_branch": head_branch,
        "before_subject": before["head_sha"],
        "after_subject": after["head_sha"],
        "before_tree": before["tree_sha"],
        "after_tree": after["tree_sha"],
        "tool_version": live_record["tool_version"],
        "lanes": {
            "preflight": before["schema"],
            "local_dry_run": dry_run_record["result"],
            "local_sync": live_record["result"],
            "local_verification": verification["result"],
        },
        "dry_run": dry_run_record,
        "live": live_record,
        "verification": verification,
        "rollback_subject": verification["rollback_subject"],
        "result": verification["result"],
    }


# --- entrypoint ----------------------------------------------------------


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SyncRejected(RESULT_FAILED_EVAL, f"{path.name} is unreadable: {error}") from error
    if not isinstance(loaded, Mapping):
        raise SyncRejected(RESULT_FAILED_EVAL, f"{path.name} is not a JSON object")
    return loaded


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="receipt.py", description="Bounded Git Town sync executor, verifier and receipt ledger."
    )
    parser.add_argument(
        "operation", nargs="?", choices=("capture", "sync", "verify", "append"), help="typed operation"
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--head-branch")
    parser.add_argument("--tool", type=Path, help="admitted git town executable")
    parser.add_argument("--mode", choices=("dry-run", "live"), help="which fixed command shape to run")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--dry-run-record", type=Path)
    parser.add_argument("--live-record", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--allowed-path", action="append", default=[])
    parser.add_argument("--excluded-path", action="append", default=[])
    parser.add_argument("--receipts-root", type=Path)
    parser.add_argument("--selftest", action="store_true")
    return parser.parse_args(list(argv))


def _require(value: Any, name: str) -> Any:
    if value is None:
        raise SyncRejected(RESULT_BLOCKED_POLICY, f"{name} is required for this operation")
    return value


def _dispatch(arguments: argparse.Namespace) -> Mapping[str, Any]:
    repository = arguments.repository
    if arguments.operation == "capture":
        return capture_evidence(repository, _require(arguments.head_branch, "--head-branch"))
    if arguments.operation == "sync":
        import os

        return run_sync(
            tool=Path(_require(arguments.tool, "--tool")),
            repository=repository,
            dry_run=_require(arguments.mode, "--mode") == "dry-run",
            timeout_seconds=arguments.timeout_seconds,
            environment=os.environ,
        )
    if arguments.operation == "verify":
        return verify_sync(
            repository=repository,
            before=_read_json(Path(_require(arguments.before, "--before"))),
            after=_read_json(Path(_require(arguments.after, "--after"))),
            allowed_paths=arguments.allowed_path,
            excluded_paths=arguments.excluded_path,
            dry_run_record=(
                _read_json(arguments.dry_run_record) if arguments.dry_run_record else None
            ),
            live_record=_read_json(arguments.live_record) if arguments.live_record else None,
        )
    before = _read_json(Path(_require(arguments.before, "--before")))
    after = _read_json(Path(_require(arguments.after, "--after")))
    verification = _read_json(Path(_require(arguments.verification, "--verification")))
    entry = build_ledger_entry(
        head_branch=str(before["head_branch"]),
        before=before,
        after=after,
        dry_run_record=_read_json(Path(_require(arguments.dry_run_record, "--dry-run-record"))),
        live_record=_read_json(Path(_require(arguments.live_record, "--live-record"))),
        verification=verification,
    )
    path = append_receipt(Path(_require(arguments.receipts_root, "--receipts-root")), entry)
    return {"receipt": path.name, "result": entry["result"]}


def _run_selftest() -> int:
    tool = Path("/nonexistent/git-town")
    try:
        _admit_tool(tool, {})
    except SyncRejected as rejected:
        assert rejected.result == RESULT_BLOCKED_TOOL_ADMISSION
    else:  # pragma: no cover - a silent pass here is the defect being guarded
        raise AssertionError("an absent tool must block admission")

    dry = command_shape(Path("git-town"), dry_run=True)
    live = command_shape(Path("git-town"), dry_run=False)
    assert DRY_RUN_FLAG in dry and DRY_RUN_FLAG not in live
    assert [flag for flag in dry[1:] if flag != DRY_RUN_FLAG] == live[1:]
    for shape in (dry, live):
        assert "--no-push" in shape and "--no-auto-resolve" in shape and "--non-interactive" in shape

    assert _path_is_leased("scripts/git-town/sync.sh", ["scripts/**"], [])
    assert not _path_is_leased("scripts/git-town/sync.sh", ["scripts/**"], ["scripts/git-town/**"])
    assert not _path_is_leased("src/app.py", ["scripts/**"], [])

    record = _stream_record("stderr", "cloning https://user:token@github.com/ed3c/x.git now")
    assert "token" not in record["excerpt"]
    assert record["bytes"] > 0 and len(record["sha256"]) == 64

    assert _classify("Automatic merge failed", returncode=1, repository=Path.cwd()) == (
        RESULT_BLOCKED_CONFLICT
    )
    assert _classify("Username for 'https://github.com':", returncode=0, repository=Path.cwd()) == (
        RESULT_BLOCKED_PROMPT
    )

    print("receipt selftest: PASS", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.selftest:
        return _run_selftest()
    if arguments.operation is None:
        print("an operation is required unless --selftest is requested", file=sys.stderr)
        return 2
    try:
        payload = _dispatch(arguments)
    except (SyncRejected, DoctorRejected) as rejected:
        print(rejected.reason, file=sys.stderr)
        sys.stdout.write(canonical_bytes({"result": rejected.result}).decode() + "\n")
        return 1
    sys.stdout.write(canonical_bytes(payload).decode() + "\n")
    return 0 if payload.get("result") in {RESULT_PASS, RESULT_SYNCED, RESULT_NO_CHANGE} else 1


def _entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
