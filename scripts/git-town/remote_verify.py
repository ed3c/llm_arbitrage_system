#!/usr/bin/env python3
"""Post-push remote head and ancestry verifier (issue #20).

A push that returned zero is not proof the remote holds what you intended. This
re-fetches through the admitted remote and asserts the remote head, the declared
parent ancestry and protected-ref immutability against the refs recorded before
the operation.

Local success is never accepted as remote success: every value compared here is
read from the remote-tracking refs after an explicit fetch.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lease import ADMITTED_REMOTES, redact_remote
from task_packet import canonical_bytes

REMOTE_SCHEMA = "llm-arbitrage/remote-verification/v1"

RESULT_PASS = "PASS"
RESULT_BLOCKED_POLICY = "BLOCKED_POLICY"
RESULT_FAILED_EVAL = "FAILED_EVAL"


class RemoteRejected(Exception):
    """One stable result plus a human-readable reason."""

    def __init__(self, result: str, reason: str) -> None:
        super().__init__(reason)
        self.result = result
        self.reason = reason


def _git(repository: Path, *arguments: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if check and completed.returncode != 0:
        raise RemoteRejected(
            RESULT_FAILED_EVAL, f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _admit_remote(repository: Path, remote: str) -> str:
    url = _git(repository, "remote", "get-url", remote, check=False)
    if not url:
        raise RemoteRejected(RESULT_BLOCKED_POLICY, f"remote {remote} is not configured")
    if url not in ADMITTED_REMOTES:
        raise RemoteRejected(
            RESULT_BLOCKED_POLICY, f"remote {redact_remote(url)} is not an admitted repository remote"
        )
    return redact_remote(url)


def verify_remote(
    *,
    repository: Path,
    remote: str,
    head_branch: str,
    expected_head_sha: str,
    expected_parent_sha: str | None = None,
    protected_before: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch, then compare the remote against what the operation intended."""

    redacted = _admit_remote(repository, remote)
    # An explicit fetch is mandatory: without it every comparison below would
    # read stale local knowledge of the remote and agree with itself.
    _git(repository, "fetch", "--prune", remote)

    findings: list[str] = []
    tracking = f"refs/remotes/{remote}/{head_branch}"
    observed_head = _git(repository, "rev-parse", "--verify", "--quiet", tracking, check=False)
    if not observed_head:
        findings.append(f"{tracking} does not exist on the remote after the operation")
    elif observed_head != expected_head_sha:
        findings.append(
            f"remote head is {observed_head} but the operation intended {expected_head_sha}"
        )

    if expected_parent_sha and observed_head:
        ancestry = subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "merge-base",
                "--is-ancestor",
                expected_parent_sha,
                observed_head,
            ],
            capture_output=True,
            timeout=300,
            check=False,
        )
        if ancestry.returncode != 0:
            findings.append(
                f"remote head does not descend from the declared parent {expected_parent_sha}"
            )

    observed_protected: dict[str, str] = {}
    for branch, before_sha in (protected_before or {}).items():
        reference = f"refs/remotes/{remote}/{branch}"
        current = _git(repository, "rev-parse", "--verify", "--quiet", reference, check=False)
        observed_protected[branch] = current
        if not current:
            findings.append(f"protected branch {branch} vanished from the remote")
        elif current != before_sha:
            findings.append(f"protected branch {branch} was rewritten from {before_sha} to {current}")

    return {
        "schema": REMOTE_SCHEMA,
        "remote": redacted,
        "head_branch": head_branch,
        "expected_head_sha": expected_head_sha,
        "observed_head_sha": observed_head or None,
        "expected_parent_sha": expected_parent_sha,
        "observed_protected_refs": observed_protected,
        "findings": findings,
        "result": RESULT_FAILED_EVAL if findings else RESULT_PASS,
    }


# --- entrypoint ----------------------------------------------------------


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="remote_verify.py", description="Post-push remote head and ancestry verification."
    )
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--head-branch")
    parser.add_argument("--expected-head-sha")
    parser.add_argument("--expected-parent-sha")
    parser.add_argument(
        "--protected-before",
        action="append",
        default=[],
        metavar="BRANCH=SHA",
        help="protected branch and the SHA it held before the operation (repeatable)",
    )
    parser.add_argument("--selftest", action="store_true")
    return parser.parse_args(list(argv))


def _protected_map(entries: Sequence[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entry in entries:
        branch, separator, sha = entry.partition("=")
        if not separator or not branch or not sha:
            raise RemoteRejected(RESULT_BLOCKED_POLICY, f"--protected-before expects BRANCH=SHA, got {entry}")
        mapping[branch] = sha
    return mapping


def _require(value: Any, name: str) -> Any:
    if value is None:
        raise RemoteRejected(RESULT_BLOCKED_POLICY, f"{name} is required")
    return value


def _run_selftest() -> int:
    try:
        _protected_map(["main"])
    except RemoteRejected as rejected:
        assert rejected.result == RESULT_BLOCKED_POLICY
    else:  # pragma: no cover - a silent pass here is the defect being guarded
        raise AssertionError("a malformed --protected-before must block")

    assert _protected_map(["main=" + "a" * 40]) == {"main": "a" * 40}
    assert redact_remote("git@github.com:ed3c/llm_arbitrage_system.git") == "ssh://github.com"
    assert "git@github.com:ed3c/llm_arbitrage_system.git" in ADMITTED_REMOTES

    print("remote_verify selftest: PASS", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.selftest:
        return _run_selftest()
    try:
        payload = verify_remote(
            repository=arguments.repository,
            remote=arguments.remote,
            head_branch=_require(arguments.head_branch, "--head-branch"),
            expected_head_sha=_require(arguments.expected_head_sha, "--expected-head-sha"),
            expected_parent_sha=arguments.expected_parent_sha,
            protected_before=_protected_map(arguments.protected_before),
        )
    except RemoteRejected as rejected:
        print(rejected.reason, file=sys.stderr)
        blocked = {"schema": REMOTE_SCHEMA, "result": rejected.result}
        sys.stdout.write(canonical_bytes(blocked).decode() + "\n")
        return 1
    sys.stdout.write(canonical_bytes(payload).decode() + "\n")
    return 0 if payload["result"] == RESULT_PASS else 1


def _entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
