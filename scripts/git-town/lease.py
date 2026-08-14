#!/usr/bin/env python3
"""Branch/path lease store and worktree doctor judge (issue #17).

`doctor.sh` collects repository facts with fixed Git commands; this module is
the typed judge that turns those facts plus the lease store into one stable
result. Lease geometry is imported from the task-packet validator rather than
re-implemented, so the two mechanisms cannot drift apart on what "overlap"
means.

The remote URL is read from stdin, never from argv: a credential-bearing URL is
one of the conditions this doctor exists to reject, and argv is world-readable
through the process table.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from task_packet import _leases_overlap as leases_overlap
from task_packet import canonical_bytes

LEASE_SCHEMA = "llm-arbitrage/branch-lease/v1"
DOCTOR_SCHEMA = "llm-arbitrage/worktree-doctor-receipt/v1"

REPOSITORY = "ed3c/llm_arbitrage_system"
ADMITTED_REMOTES = (
    "https://github.com/ed3c/llm_arbitrage_system.git",
    "git@github.com:ed3c/llm_arbitrage_system.git",
)
# Named policy only. The doctor reports which variables are present and never
# reports or stores their values.
REQUIRED_PROMPT_SUPPRESSION = ("GIT_TERMINAL_PROMPT", "GIT_PAGER", "GIT_EDITOR")

IN_PROGRESS_MARKERS = {
    "MERGE_HEAD": "merge",
    "REBASE_HEAD": "rebase",
    "rebase-merge": "rebase",
    "rebase-apply": "rebase",
    "CHERRY_PICK_HEAD": "cherry-pick",
    "REVERT_HEAD": "revert",
    "BISECT_LOG": "bisect",
}

RESULT_PASS = "PASS"
RESULT_DIRTY = "BLOCKED_DIRTY"
RESULT_BRANCH_LEASE = "BLOCKED_BRANCH_LEASE"
RESULT_ANCESTRY = "BLOCKED_ANCESTRY"
RESULT_POLICY = "BLOCKED_POLICY"

_CREDENTIAL_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s@]*:[^/\s@]*@", re.IGNORECASE)
_SCHEME_HOST = re.compile(r"\A(?P<scheme>[a-z][a-z0-9+.-]*)://(?:[^@/]*@)?(?P<host>[^/:]+)", re.IGNORECASE)
_SCP_HOST = re.compile(r"\A(?:[^@/]+@)?(?P<host>[^:/]+):", re.IGNORECASE)


class DoctorRejected(Exception):
    """One stable blocked result plus a human-readable reason."""

    def __init__(self, result: str, reason: str) -> None:
        super().__init__(reason)
        self.result = result
        self.reason = reason


# --- lease store ---------------------------------------------------------


def _lease_path(lease_root: Path, branch: str) -> Path:
    # One file per branch; the branch name is the identity, so it is encoded
    # rather than hashed to keep the store readable during an incident.
    return lease_root / f"{branch.replace('/', '%2F')}.json"


def _read_lease(path: Path) -> Mapping[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DoctorRejected(RESULT_BRANCH_LEASE, f"lease {path.name} is unreadable: {error}") from error
    if not isinstance(loaded, Mapping) or loaded.get("schema") != LEASE_SCHEMA:
        raise DoctorRejected(RESULT_BRANCH_LEASE, f"lease {path.name} is not a {LEASE_SCHEMA} document")
    return loaded


def iter_leases(lease_root: Path) -> Iterator[Mapping[str, Any]]:
    if not lease_root.is_dir():
        return
    for path in sorted(lease_root.glob("*.json")):
        yield _read_lease(path)


def live_leases(lease_root: Path, now: float) -> list[Mapping[str, Any]]:
    return [lease for lease in iter_leases(lease_root) if float(lease["expires_at"]) > now]


def acquire_lease(
    lease_root: Path,
    *,
    branch: str,
    holder: str,
    allowed_paths: Sequence[str],
    ttl_seconds: int,
    now: float,
) -> Mapping[str, Any]:
    """Take an exclusive branch lease with a disjoint path set, or refuse."""

    if ttl_seconds <= 0:
        raise DoctorRejected(RESULT_POLICY, "lease ttl must be a positive number of seconds")
    if not allowed_paths:
        raise DoctorRejected(RESULT_POLICY, "a lease requires at least one allowed path")

    for lease in live_leases(lease_root, now):
        other_branch = str(lease["head_branch"])
        if other_branch == branch:
            if str(lease["holder"]) != holder:
                raise DoctorRejected(
                    RESULT_BRANCH_LEASE,
                    f"branch lease {branch} is held by another worker until {lease['expires_at']}",
                )
            continue
        for mine in allowed_paths:
            for theirs in lease["allowed_paths"]:
                if leases_overlap(mine, str(theirs)):
                    raise DoctorRejected(
                        RESULT_BRANCH_LEASE,
                        f"allowed path {mine} overlaps live lease {theirs} on {other_branch}",
                    )

    lease_root.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": LEASE_SCHEMA,
        "head_branch": branch,
        "holder": holder,
        "allowed_paths": sorted(allowed_paths),
        "acquired_at": now,
        "expires_at": now + ttl_seconds,
        "ttl_seconds": ttl_seconds,
    }
    _lease_path(lease_root, branch).write_bytes(canonical_bytes(document) + b"\n")
    return document


def renew_lease(lease_root: Path, *, branch: str, holder: str, now: float) -> Mapping[str, Any]:
    path = _lease_path(lease_root, branch)
    if not path.is_file():
        raise DoctorRejected(RESULT_BRANCH_LEASE, f"no lease exists for {branch}")
    lease = _read_lease(path)
    if str(lease["holder"]) != holder:
        raise DoctorRejected(RESULT_BRANCH_LEASE, f"lease {branch} is held by another worker")
    if float(lease["expires_at"]) <= now:
        # An expired lease is not renewable: the window it guarded is gone and
        # another worker may already have acted on that assumption.
        raise DoctorRejected(
            RESULT_BRANCH_LEASE, f"lease {branch} expired at {lease['expires_at']} and cannot be renewed"
        )
    renewed = dict(lease)
    renewed["expires_at"] = now + float(lease["ttl_seconds"])
    path.write_bytes(canonical_bytes(renewed) + b"\n")
    return renewed


def release_lease(lease_root: Path, *, branch: str, holder: str) -> bool:
    path = _lease_path(lease_root, branch)
    if not path.is_file():
        return False
    if str(_read_lease(path)["holder"]) != holder:
        raise DoctorRejected(RESULT_BRANCH_LEASE, f"lease {branch} is held by another worker")
    path.unlink()
    return True


# --- remote classification -----------------------------------------------


def redact_remote(url: str) -> str:
    """Scheme and host only. A receipt must never carry the full remote URL."""

    scheme_host = _SCHEME_HOST.match(url)
    if scheme_host is not None:
        return f"{scheme_host.group('scheme').lower()}://{scheme_host.group('host').lower()}"
    scp_host = _SCP_HOST.match(url)
    if scp_host is not None:
        return f"ssh://{scp_host.group('host').lower()}"
    return "unrecognized"


def _classify_remote(url: str) -> str:
    if _CREDENTIAL_URL.search(url):
        raise DoctorRejected(RESULT_POLICY, "origin remote embeds a credential and is refused")
    if url not in ADMITTED_REMOTES:
        raise DoctorRejected(
            RESULT_POLICY, f"origin remote {redact_remote(url)} is not an admitted {REPOSITORY} remote"
        )
    return redact_remote(url)


# --- doctor --------------------------------------------------------------


def _detect_in_progress(git_dir: Path) -> str | None:
    for marker, operation in IN_PROGRESS_MARKERS.items():
        if (git_dir / marker).exists():
            return operation
    return None


def _present_prompt_policy(environment: Mapping[str, str]) -> tuple[str, ...]:
    missing = tuple(name for name in REQUIRED_PROMPT_SUPPRESSION if name not in environment)
    if missing:
        raise DoctorRejected(
            RESULT_POLICY,
            f"non-interactive policy variables are not set: {', '.join(missing)}",
        )
    return REQUIRED_PROMPT_SUPPRESSION


def run_doctor(
    *,
    head_branch: str,
    current_branch: str,
    git_dir: Path,
    git_common_dir: Path,
    remote_url: str,
    dirty_entries: int,
    allowed_paths: Sequence[str],
    lease_root: Path,
    holder: str,
    ttl_seconds: int,
    now: float,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    """Judge one worktree and take its lease, or raise ``DoctorRejected``."""

    # A linked worktree has its own git dir; in the primary checkout the two
    # resolve to the same path. This is the isolation invariant, so it is
    # checked before anything that could mutate state.
    if git_dir.resolve() == git_common_dir.resolve():
        raise DoctorRejected(
            RESULT_POLICY, "doctor refuses the primary checkout; run from an admitted linked worktree"
        )

    redacted_remote = _classify_remote(remote_url)
    prompt_policy = _present_prompt_policy(environment)

    if current_branch != head_branch:
        raise DoctorRejected(
            RESULT_ANCESTRY,
            f"worktree is on {current_branch} but the task packet head is {head_branch}",
        )

    if dirty_entries < 0:
        raise DoctorRejected(RESULT_DIRTY, "dirty entry count is not reportable")
    if dirty_entries > 0:
        raise DoctorRejected(
            RESULT_DIRTY, f"worktree has {dirty_entries} uncommitted entries before synchronization"
        )
    in_progress = _detect_in_progress(git_dir)
    if in_progress is not None:
        raise DoctorRejected(RESULT_DIRTY, f"a {in_progress} operation is already in progress")

    lease = acquire_lease(
        lease_root,
        branch=head_branch,
        holder=holder,
        allowed_paths=allowed_paths,
        ttl_seconds=ttl_seconds,
        now=now,
    )

    return {
        "schema": DOCTOR_SCHEMA,
        "repository": REPOSITORY,
        "head_branch": head_branch,
        "worktree_git_dir_is_linked": True,
        "remote": redacted_remote,
        "dirty_entries": 0,
        "in_progress_operation": None,
        "prompt_policy_variables_present": list(prompt_policy),
        "lease_expires_at": lease["expires_at"],
        "allowed_paths": list(lease["allowed_paths"]),
        "result": RESULT_PASS,
    }


def _blocked_receipt(result: str) -> dict[str, Any]:
    return {
        "schema": DOCTOR_SCHEMA,
        "repository": REPOSITORY,
        "head_branch": None,
        "worktree_git_dir_is_linked": None,
        "remote": None,
        "dirty_entries": None,
        "in_progress_operation": None,
        "prompt_policy_variables_present": None,
        "lease_expires_at": None,
        "allowed_paths": None,
        "result": result,
    }


# --- entrypoint ----------------------------------------------------------


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="lease.py", description="Branch/path lease store and worktree doctor judge."
    )
    parser.add_argument(
        "operation",
        nargs="?",
        choices=("doctor", "acquire", "renew", "release", "inspect"),
        help="typed operation to run",
    )
    parser.add_argument("--lease-root", type=Path, help="lease store directory")
    parser.add_argument("--head-branch", help="task packet head branch")
    parser.add_argument("--current-branch", help="branch the worktree is on")
    parser.add_argument("--git-dir", type=Path, help="absolute git dir of this worktree")
    parser.add_argument("--git-common-dir", type=Path, help="absolute common git dir")
    parser.add_argument("--dirty-entries", type=int, help="porcelain status entry count")
    parser.add_argument("--allowed-path", action="append", default=[], help="leased path (repeatable)")
    parser.add_argument("--holder", help="opaque worker identity")
    parser.add_argument("--ttl-seconds", type=int, default=3600, help="lease lifetime")
    parser.add_argument("--now", type=float, help="clock override for deterministic evals")
    parser.add_argument(
        "--remote-url-from-stdin",
        action="store_true",
        help="read the origin URL from stdin so it never enters the process table",
    )
    parser.add_argument("--selftest", action="store_true", help="run built-in contract checks and exit")
    return parser.parse_args(list(argv))


def _require_option(value: Any, name: str) -> Any:
    if value is None:
        raise DoctorRejected(RESULT_POLICY, f"{name} is required for this operation")
    return value


def _dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    now = time.time() if arguments.now is None else arguments.now
    lease_root = Path(_require_option(arguments.lease_root, "--lease-root"))

    if arguments.operation == "doctor":
        if not arguments.remote_url_from_stdin:
            raise DoctorRejected(RESULT_POLICY, "the origin URL must be supplied through stdin")
        return run_doctor(
            head_branch=_require_option(arguments.head_branch, "--head-branch"),
            current_branch=_require_option(arguments.current_branch, "--current-branch"),
            git_dir=Path(_require_option(arguments.git_dir, "--git-dir")),
            git_common_dir=Path(_require_option(arguments.git_common_dir, "--git-common-dir")),
            remote_url=sys.stdin.readline().strip(),
            dirty_entries=int(_require_option(arguments.dirty_entries, "--dirty-entries")),
            allowed_paths=arguments.allowed_path,
            lease_root=lease_root,
            holder=_require_option(arguments.holder, "--holder"),
            ttl_seconds=arguments.ttl_seconds,
            now=now,
            environment=os.environ,
        )
    if arguments.operation == "acquire":
        lease = acquire_lease(
            lease_root,
            branch=_require_option(arguments.head_branch, "--head-branch"),
            holder=_require_option(arguments.holder, "--holder"),
            allowed_paths=arguments.allowed_path,
            ttl_seconds=arguments.ttl_seconds,
            now=now,
        )
        return {**lease, "result": RESULT_PASS}
    if arguments.operation == "renew":
        lease = renew_lease(
            lease_root,
            branch=_require_option(arguments.head_branch, "--head-branch"),
            holder=_require_option(arguments.holder, "--holder"),
            now=now,
        )
        return {**lease, "result": RESULT_PASS}
    if arguments.operation == "release":
        removed = release_lease(
            lease_root,
            branch=_require_option(arguments.head_branch, "--head-branch"),
            holder=_require_option(arguments.holder, "--holder"),
        )
        return {"head_branch": arguments.head_branch, "released": removed, "result": RESULT_PASS}
    return {
        "lease_root": str(lease_root),
        "live_leases": [dict(lease) for lease in live_leases(lease_root, now)],
        "result": RESULT_PASS,
    }


def _run_selftest() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root) / "leases"
        held = acquire_lease(
            root,
            branch="tooling/a",
            holder="worker-a",
            allowed_paths=["scripts/git-town/doctor.sh"],
            ttl_seconds=60,
            now=1000.0,
        )
        assert held["expires_at"] == 1060.0
        assert len(live_leases(root, 1000.0)) == 1
        assert live_leases(root, 2000.0) == []

        for branch, paths, holder in (
            ("tooling/a", ["docs/other.md"], "worker-b"),
            ("tooling/b", ["scripts/**"], "worker-b"),
            ("tooling/b", ["scripts/git-town/doctor.sh"], "worker-b"),
        ):
            try:
                acquire_lease(
                    root, branch=branch, holder=holder, allowed_paths=paths, ttl_seconds=60, now=1000.0
                )
            except DoctorRejected as rejected:
                assert rejected.result == RESULT_BRANCH_LEASE, rejected.result
            else:  # pragma: no cover - a silent pass here is the defect being guarded
                raise AssertionError(f"{branch} with {paths} should have been refused")

        # An expired lease is not renewable, and its paths become free.
        try:
            renew_lease(root, branch="tooling/a", holder="worker-a", now=2000.0)
        except DoctorRejected as rejected:
            assert rejected.result == RESULT_BRANCH_LEASE
        else:  # pragma: no cover
            raise AssertionError("an expired lease must not renew")
        acquire_lease(
            root,
            branch="tooling/b",
            holder="worker-b",
            allowed_paths=["scripts/git-town/doctor.sh"],
            ttl_seconds=60,
            now=2000.0,
        )

    assert redact_remote("https://user:token@github.com/ed3c/x.git") == "https://github.com"
    assert redact_remote("git@github.com:ed3c/llm_arbitrage_system.git") == "ssh://github.com"
    for url, expected in (
        ("https://user:token@github.com/ed3c/llm_arbitrage_system.git", RESULT_POLICY),
        ("https://github.com/someone/else.git", RESULT_POLICY),
    ):
        try:
            _classify_remote(url)
        except DoctorRejected as rejected:
            assert rejected.result == expected
        else:  # pragma: no cover
            raise AssertionError(f"{redact_remote(url)} should have been refused")

    try:
        _present_prompt_policy({"GIT_TERMINAL_PROMPT": "0"})
    except DoctorRejected as rejected:
        assert rejected.result == RESULT_POLICY
        assert "0" not in rejected.reason.replace("GIT_TERMINAL_PROMPT", "")
    else:  # pragma: no cover
        raise AssertionError("missing prompt policy must block")

    print("lease selftest: PASS", file=sys.stderr)
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
    except DoctorRejected as rejected:
        print(rejected.reason, file=sys.stderr)
        sys.stdout.write(canonical_bytes(_blocked_receipt(rejected.result)).decode() + "\n")
        return 1
    sys.stdout.write(canonical_bytes(payload).decode() + "\n")
    return 0


def _entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
