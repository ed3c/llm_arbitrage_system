"""E08 and E09 fail-closed canaries for the Git Town Worker (issue #19).

Each canary plants one deterministic disagreement with `fixtures/git-town/
canary_tool.sh` and asserts the adapter refuses in the documented way, preserves
its evidence, and never reaches for a forbidden continuation command.

A green happy path proves nothing about failing closed, which is the whole
reason this module exists separately from `test_sync_contract.py`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RECEIPT_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "receipt.py"
SYNC_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "sync.sh"
DOCTOR_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "doctor.sh"
CANARY_TOOL = REPOSITORY_ROOT / "fixtures" / "git-town" / "canary_tool.sh"

FORBIDDEN_SUBCOMMANDS = ("continue", "skip", "undo", "ship", "abort")
PROMPT_POLICY = {"GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "GIT_EDITOR": "true"}


def _load(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


receipt_module = _load("git_town_receipt_canaries", RECEIPT_PATH)


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return completed.stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    primary = tmp_path / "repo"
    primary.mkdir()
    _git(primary, "init", "--initial-branch", "main")
    _git(primary, "config", "user.email", "canary@example.invalid")
    _git(primary, "config", "user.name", "canary")
    _git(primary, "remote", "add", "origin", "git@github.com:ed3c/llm_arbitrage_system.git")
    (primary / "leased.txt").write_text("original\n", encoding="utf-8")
    _git(primary, "add", "-A")
    _git(primary, "commit", "-m", "fixture")
    _git(primary, "checkout", "-q", "-b", "tooling/owned")
    _git(primary, "commit", "-q", "--allow-empty", "-m", "owned head ahead of main")
    return primary


@pytest.fixture
def canary(tmp_path: Path) -> dict[str, Any]:
    log = tmp_path / "invocations.log"
    orphan_pid_file = tmp_path / "orphan.pid"
    return {"tool": CANARY_TOOL, "log": log, "orphan_pid_file": orphan_pid_file}


def _environment(canary: dict[str, Any], behaviour: str, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        **PROMPT_POLICY,
        "CANARY_BEHAVIOUR": behaviour,
        "CANARY_INVOCATION_LOG": str(canary["log"]),
        "CANARY_ORPHAN_PID_FILE": str(canary["orphan_pid_file"]),
        **extra,
    }


def _run(
    repository: Path, canary: dict[str, Any], behaviour: str, *, timeout: int = 60
) -> dict[str, Any]:
    record: dict[str, Any] = receipt_module.run_sync(
        tool=canary["tool"],
        repository=repository,
        dry_run=False,
        timeout_seconds=timeout,
        environment=_environment(canary, behaviour),
    )
    return record


def _shapes(canary: dict[str, Any]) -> list[str]:
    if not canary["log"].exists():
        return []
    return canary["log"].read_text(encoding="utf-8").splitlines()


# --- the canaries --------------------------------------------------------


def test_a_planted_semantic_conflict_blocks(repository: Path, canary: dict[str, Any]) -> None:
    record = _run(repository, canary, "semantic-conflict")

    assert record["result"] == "BLOCKED_CONFLICT"


def test_a_silent_conflict_still_blocks_despite_a_zero_exit(
    repository: Path, canary: dict[str, Any]
) -> None:
    record = _run(repository, canary, "silent-conflict")

    # The tool exited zero and printed nothing. Anything that reads exit status
    # as the repository result passes this.
    assert record["exit_code"] == 0
    assert record["streams"][0]["bytes"] == 0
    assert record["result"] == "BLOCKED_CONFLICT"


def test_conflict_evidence_is_preserved_not_repaired(
    repository: Path, canary: dict[str, Any]
) -> None:
    _run(repository, canary, "semantic-conflict")
    git_dir = Path(_git(repository, "rev-parse", "--absolute-git-dir"))

    assert (git_dir / "MERGE_HEAD").exists()
    assert "<<<<<<<" in (repository / "leased.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("behaviour", ["editor-prompt", "credential-prompt"])
def test_an_interactive_request_blocks(
    repository: Path, canary: dict[str, Any], behaviour: str
) -> None:
    assert _run(repository, canary, behaviour)["result"] == "BLOCKED_PROMPT"


def test_a_hang_blocks_on_the_hard_timeout(repository: Path, canary: dict[str, Any]) -> None:
    started = time.monotonic()
    record = _run(repository, canary, "hang", timeout=2)

    assert record["result"] == "BLOCKED_TIMEOUT"
    assert record["timed_out"] is True
    assert time.monotonic() - started < 30


def test_a_timeout_reaps_the_orphaned_grandchild(
    repository: Path, canary: dict[str, Any]
) -> None:
    record = _run(repository, canary, "orphan", timeout=2)

    assert record["result"] == "BLOCKED_TIMEOUT"
    assert record["residue"]["killed_on_timeout"] is True
    assert record["residue"]["process_group_reaped"] is True

    orphan_pid = int(canary["orphan_pid_file"].read_text(encoding="utf-8").strip())
    with pytest.raises(ProcessLookupError):
        # A surviving grandchild is exactly what the cleanup lane must not hide.
        os.kill(orphan_pid, 0)


def test_a_clean_run_reports_no_residue(repository: Path, canary: dict[str, Any]) -> None:
    record = _run(repository, canary, "clean")

    assert record["result"] == "PASS"
    assert record["residue"] == {"process_group_reaped": True, "killed_on_timeout": False}


# --- verification-level canaries -----------------------------------------


def _verify_after(
    repository: Path, before: dict[str, Any], allowed: list[str] | None = None
) -> dict[str, Any]:
    after = receipt_module.capture_evidence(repository, "tooling/owned")
    result: dict[str, Any] = receipt_module.verify_sync(
        repository=repository,
        before=before,
        after=after,
        allowed_paths=allowed if allowed is not None else ["leased.txt"],
        excluded_paths=[],
    )
    return result


@pytest.mark.parametrize(
    ("behaviour", "expected_finding"),
    [
        ("dirty", "uncommitted entries remain"),
        ("ref-move", "perennial ref moved"),
        ("residue", "uncommitted entries remain"),
    ],
)
def test_a_zero_exit_that_left_the_repository_wrong_fails_the_eval(
    repository: Path, canary: dict[str, Any], behaviour: str, expected_finding: str
) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    record = _run(repository, canary, behaviour)
    verification = _verify_after(repository, before)

    assert record["exit_code"] == 0
    assert verification["result"] == "FAILED_EVAL"
    assert any(expected_finding in finding for finding in verification["findings"])


def test_the_before_and_after_graph_are_both_recorded(
    repository: Path, canary: dict[str, Any]
) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _run(repository, canary, "clean")
    verification = _verify_after(repository, before)

    assert verification["before_head_sha"] == before["head_sha"]
    assert verification["after_head_sha"] == before["head_sha"]
    assert verification["rollback_subject"] == before["head_sha"]


# --- drift-aware rollback ------------------------------------------------


def _receipt_for(repository: Path, before: dict[str, Any]) -> dict[str, Any]:
    after = receipt_module.capture_evidence(repository, "tooling/owned")
    verification = receipt_module.verify_sync(
        repository=repository,
        before=before,
        after=after,
        allowed_paths=["leased.txt"],
        excluded_paths=[],
    )
    record = {
        "command_shape": list(receipt_module.BASE_SYNC_FLAGS),
        "tool_version": "v24.0.0",
        "result": "PASS",
        "mode": "live",
    }
    return receipt_module.build_ledger_entry(
        head_branch="tooling/owned",
        before=before,
        after=after,
        dry_run_record=record,
        live_record=record,
        verification=verification,
    )


def test_an_undrifted_rollback_returns_a_proposal_and_executes_nothing(repository: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    entry = _receipt_for(repository, before)
    head_before_proposal = _git(repository, "rev-parse", "HEAD")

    proposal = receipt_module.propose_rollback(repository=repository, receipt=entry)

    assert proposal["result"] == "PASS"
    assert proposal["requires_human_admit"] is True
    assert proposal["proposal"]["restore_to"] == before["head_sha"]
    # A proposal is not an action.
    assert _git(repository, "rev-parse", "HEAD") == head_before_proposal


def test_a_rollback_target_that_drifted_is_refused(repository: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    entry = _receipt_for(repository, before)

    # Someone else moved the branch after the receipt was written.
    _git(repository, "commit", "-q", "--allow-empty", "-m", "independent movement")

    proposal = receipt_module.propose_rollback(repository=repository, receipt=entry)

    assert proposal["result"] == "ROLLBACK_REFUSED_DRIFT"
    assert proposal["proposal"] is None
    assert proposal["drift"]


def test_a_rollback_whose_subject_vanished_is_refused(repository: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    entry = dict(_receipt_for(repository, before))
    entry["rollback_subject"] = "0" * 40

    proposal = receipt_module.propose_rollback(repository=repository, receipt=entry)

    assert proposal["result"] == "ROLLBACK_REFUSED_DRIFT"
    assert any("no longer reachable" in reason for reason in proposal["drift"])


# --- forbidden mutations -------------------------------------------------


@pytest.mark.parametrize(
    "behaviour",
    ["semantic-conflict", "silent-conflict", "editor-prompt", "credential-prompt", "ref-move"],
)
def test_the_adapter_never_sends_a_continuation_subcommand(
    repository: Path, canary: dict[str, Any], behaviour: str
) -> None:
    _run(repository, canary, behaviour)
    shapes = _shapes(canary)

    assert shapes, "the canary tool was never invoked"
    for shape in shapes:
        assert shape.split()[0] == "sync"
        for forbidden in FORBIDDEN_SUBCOMMANDS:
            assert f" {forbidden}" not in f" {shape}"


def test_a_blocked_dry_run_never_reaches_the_live_command(
    repository: Path, canary: dict[str, Any], tmp_path: Path
) -> None:
    completed = subprocess.run(
        [
            "bash",
            str(SYNC_PATH),
            "--head-branch",
            "tooling/owned",
            "--allowed-path",
            "leased.txt",
            "--skip-doctor",
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=_environment(
            canary, "semantic-conflict", PYTHON=sys.executable, HOST_GIT_TOWN_BIN=str(CANARY_TOOL)
        ),
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_CONFLICT"
    assert len(_shapes(canary)) == 1
    assert "--dry-run" in _shapes(canary)[0]


def test_a_blocked_run_preserves_its_evidence_directory(
    repository: Path, canary: dict[str, Any]
) -> None:
    completed = subprocess.run(
        [
            "bash",
            str(SYNC_PATH),
            "--head-branch",
            "tooling/owned",
            "--allowed-path",
            "leased.txt",
            "--skip-doctor",
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=_environment(
            canary, "semantic-conflict", PYTHON=sys.executable, HOST_GIT_TOWN_BIN=str(CANARY_TOOL)
        ),
    )

    assert "preserved sync evidence" in completed.stderr
    preserved = Path(completed.stderr.split("preserved sync evidence:")[1].split()[0])
    assert preserved.is_dir()
    assert (preserved / "dry-run.json").is_file()


def test_a_clean_run_removes_its_evidence_directory(
    repository: Path, canary: dict[str, Any]
) -> None:
    completed = subprocess.run(
        [
            "bash",
            str(SYNC_PATH),
            "--head-branch",
            "tooling/owned",
            "--allowed-path",
            "leased.txt",
            "--skip-doctor",
            "--receipts-root",
            str(repository / ".canary-receipts"),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=_environment(
            canary, "clean", PYTHON=sys.executable, HOST_GIT_TOWN_BIN=str(CANARY_TOOL)
        ),
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "preserved sync evidence" not in completed.stderr


@pytest.mark.parametrize("script", [SYNC_PATH, DOCTOR_PATH, RECEIPT_PATH])
def test_no_adapter_source_contains_a_destructive_command(script: Path) -> None:
    source = script.read_text(encoding="utf-8")

    for forbidden in (
        "town continue",
        "town skip",
        "town undo",
        "town ship",
        "push --force",
        "--force-with-lease",
        "reset --hard",
        "branch -D",
        "clean -fd",
    ):
        assert forbidden not in source, f"{script.name} contains {forbidden}"


def test_the_canary_tool_itself_never_repairs_a_conflict() -> None:
    source = CANARY_TOOL.read_text(encoding="utf-8")

    for forbidden in ("git merge --continue", "git rebase --continue", "git push", "reset --hard"):
        assert forbidden not in source


# --- the canaries must be able to fail -----------------------------------


def test_an_unknown_canary_behaviour_is_a_tool_failure(
    repository: Path, canary: dict[str, Any]
) -> None:
    # If the fixture silently succeeded on an unrecognized behaviour, every
    # canary above would pass without producing its condition.
    assert _run(repository, canary, "not-a-behaviour")["result"] == "FAILED_TOOL"


def test_the_canary_tool_reports_the_admitted_version(
    repository: Path, canary: dict[str, Any]
) -> None:
    with pytest.raises(receipt_module.SyncRejected) as rejected:
        receipt_module.run_sync(
            tool=canary["tool"],
            repository=repository,
            dry_run=True,
            timeout_seconds=30,
            environment=_environment(canary, "clean", CANARY_VERSION="v23.0.0"),
        )

    assert rejected.value.result == "BLOCKED_TOOL_ADMISSION"


def test_the_orphan_behaviour_really_orphans_without_reaping(
    repository: Path, canary: dict[str, Any]
) -> None:
    """The reaping control is only meaningful if the grandchild would survive.

    Run the fixture the naive way — kill the direct child only — and confirm the
    grandchild is still alive. Without this, `process_group_reaped: True` could
    be reporting on a condition that never existed.
    """

    process = subprocess.Popen(
        [str(CANARY_TOOL), "sync"],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_environment(canary, "orphan"),
    )
    for _ in range(200):
        if canary["orphan_pid_file"].exists():
            break
        time.sleep(0.02)
    process.kill()
    process.wait(timeout=30)

    orphan_pid = int(canary["orphan_pid_file"].read_text(encoding="utf-8").strip())
    try:
        os.kill(orphan_pid, 0)
    finally:
        try:
            os.kill(orphan_pid, signal.SIGKILL)
        except ProcessLookupError:  # pragma: no cover - already gone
            pass
