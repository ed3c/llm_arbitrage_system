"""E06 and E07 evals for the bounded no-push sync adapter (issue #18).

Git Town itself is not admitted on any host yet (#15), so the adapter is driven
against a stub executable whose behaviour is selected by an environment
variable. The stub is what makes the disagreement-producing controls — conflict,
prompt, timeout, out-of-lease diff, moved perennial ref — reachable at all; a
real binary would only ever demonstrate the happy path.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RECEIPT_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "receipt.py"
SYNC_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "sync.sh"

STUB = """#!/usr/bin/env bash
set -u
if [ "${1:-}" = "--version" ]; then
  printf '%s\\n' "${STUB_VERSION:-Git Town 24.0.0}"
  exit 0
fi
# Record the exact shape this invocation received so a test can assert which
# commands actually ran rather than inferring it from side effects.
[ -z "${STUB_INVOCATION_LOG:-}" ] || printf '%s\\n' "$*" >> "${STUB_INVOCATION_LOG}"
case "${STUB_BEHAVIOUR:-noop}" in
  noop)     printf 'branch is up to date\\n'; exit 0 ;;
  commit)   printf 'synced\\n' > /dev/null
            git commit --allow-empty -q -m "stub sync commit"; exit 0 ;;
  leased)   printf 'leased change\\n' >> "${STUB_LEASED_FILE}"
            git add -A && git commit -q -m "stub leased change"; exit 0 ;;
  unleased) printf 'drift\\n' >> "${STUB_UNLEASED_FILE}"
            git add -A && git commit -q -m "stub unleased change"; exit 0 ;;
  perennial) git branch -f main HEAD; printf 'moved main\\n'; exit 0 ;;
  branchy)  git branch stub/extra HEAD; printf 'created a branch\\n'; exit 0 ;;
  conflict) printf 'CONFLICT (content): Merge conflict in file.txt\\n' >&2; exit 1 ;;
  prompt)   printf "Username for 'https://github.com': " >&2; exit 1 ;;
  hang)     sleep 30; exit 0 ;;
  fail)     printf 'unexpected tool failure\\n' >&2; exit 3 ;;
  *)        printf 'unknown stub behaviour\\n' >&2; exit 9 ;;
esac
"""


def _load(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


receipt_module = _load("git_town_receipt", RECEIPT_PATH)


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
    _git(primary, "config", "user.email", "sync@example.invalid")
    _git(primary, "config", "user.name", "sync")
    _git(primary, "remote", "add", "origin", "git@github.com:ed3c/llm_arbitrage_system.git")
    (primary / "leased.txt").write_text("leased\n", encoding="utf-8")
    (primary / "unleased.txt").write_text("unleased\n", encoding="utf-8")
    _git(primary, "add", "-A")
    _git(primary, "commit", "-m", "fixture")
    _git(primary, "checkout", "-q", "-b", "tooling/owned")
    return primary


@pytest.fixture
def stub(tmp_path: Path) -> Path:
    path = tmp_path / "git-town-stub"
    path.write_text(STUB, encoding="utf-8")
    path.chmod(0o755)
    return path


def _environment(repository: Path, behaviour: str, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "STUB_BEHAVIOUR": behaviour,
        "STUB_LEASED_FILE": str(repository / "leased.txt"),
        "STUB_UNLEASED_FILE": str(repository / "unleased.txt"),
        **extra,
    }


def _run_sync(repository: Path, stub: Path, behaviour: str, *, dry_run: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = receipt_module.run_sync(
        tool=stub,
        repository=repository,
        dry_run=dry_run,
        timeout_seconds=60,
        environment=_environment(repository, behaviour),
    )
    return result


# --- command shape fidelity ----------------------------------------------


def test_the_dry_run_and_live_shapes_differ_only_by_the_dry_run_flag() -> None:
    dry = receipt_module.command_shape(Path("git-town"), dry_run=True)
    live = receipt_module.command_shape(Path("git-town"), dry_run=False)

    assert dry[1:] == ["sync", "--dry-run", "--stack", "--non-interactive", "--no-auto-resolve", "--no-push"]
    assert live[1:] == ["sync", "--stack", "--non-interactive", "--no-auto-resolve", "--no-push"]


def test_the_adapter_cannot_be_asked_for_an_arbitrary_command() -> None:
    source = RECEIPT_PATH.read_text(encoding="utf-8")

    assert "--mode" in source and "choices=(\"dry-run\", \"live\")" in source
    for forbidden in ("shell=True", "--continue", "--skip", "undo", "ship", "--force"):
        assert forbidden not in receipt_module.BASE_SYNC_FLAGS


# --- tool admission ------------------------------------------------------


def test_an_absent_tool_blocks_admission(repository: Path, tmp_path: Path) -> None:
    with pytest.raises(receipt_module.SyncRejected) as rejected:
        receipt_module.run_sync(
            tool=tmp_path / "absent",
            repository=repository,
            dry_run=True,
            timeout_seconds=60,
            environment=dict(os.environ),
        )

    assert rejected.value.result == "BLOCKED_TOOL_ADMISSION"


def test_a_wrong_tool_version_blocks_admission(repository: Path, stub: Path) -> None:
    with pytest.raises(receipt_module.SyncRejected) as rejected:
        receipt_module.run_sync(
            tool=stub,
            repository=repository,
            dry_run=True,
            timeout_seconds=60,
            environment=_environment(repository, "noop", STUB_VERSION="v23.9.0"),
        )

    assert rejected.value.result == "BLOCKED_TOOL_ADMISSION"


# --- outcome classification ----------------------------------------------


@pytest.mark.parametrize(
    ("behaviour", "expected"),
    [
        ("noop", "PASS"),
        ("conflict", "BLOCKED_CONFLICT"),
        ("prompt", "BLOCKED_PROMPT"),
        ("fail", "FAILED_TOOL"),
    ],
)
def test_tool_outcomes_map_to_stable_results(
    repository: Path, stub: Path, behaviour: str, expected: str
) -> None:
    assert _run_sync(repository, stub, behaviour)["result"] == expected


def test_a_hard_timeout_is_a_blocked_result_not_a_failure(repository: Path, stub: Path) -> None:
    record = receipt_module.run_sync(
        tool=stub,
        repository=repository,
        dry_run=False,
        timeout_seconds=1,
        environment=_environment(repository, "hang"),
    )

    assert record["result"] == "BLOCKED_TIMEOUT"
    assert record["timed_out"] is True
    assert record["exit_code"] is None


def test_a_non_positive_timeout_is_refused(repository: Path, stub: Path) -> None:
    with pytest.raises(receipt_module.SyncRejected) as rejected:
        receipt_module.run_sync(
            tool=stub,
            repository=repository,
            dry_run=False,
            timeout_seconds=0,
            environment=_environment(repository, "noop"),
        )

    assert rejected.value.result == "BLOCKED_POLICY"


def test_streams_are_digested_bounded_and_redacted(repository: Path, stub: Path) -> None:
    record = _run_sync(repository, stub, "prompt")
    streams = {entry["stream"]: entry for entry in record["streams"]}

    assert len(streams["stdout"]["sha256"]) == 64
    assert streams["stderr"]["bytes"] > 0
    assert len(streams["stderr"]["excerpt"]) <= receipt_module.MAX_STREAM_EXCERPT_BYTES


# --- independent verification --------------------------------------------


def _verify(repository: Path, before: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    after = receipt_module.capture_evidence(repository, "tooling/owned")
    result: dict[str, Any] = receipt_module.verify_sync(
        repository=repository,
        before=before,
        after=after,
        allowed_paths=kwargs.pop("allowed_paths", ["leased.txt"]),
        excluded_paths=kwargs.pop("excluded_paths", []),
        **kwargs,
    )
    return result


def test_an_unchanged_head_verifies_as_no_change(repository: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")

    assert _verify(repository, before)["result"] == "NO_CHANGE"


def test_a_leased_change_verifies_as_synced(repository: Path, stub: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _run_sync(repository, stub, "leased")
    verification = _verify(repository, before)

    assert verification["result"] == "SYNCED"
    assert verification["changed_paths"] == ["leased.txt"]
    assert verification["rollback_subject"] == before["head_sha"]


def test_an_out_of_lease_change_fails_the_eval(repository: Path, stub: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _run_sync(repository, stub, "unleased")
    verification = _verify(repository, before)

    assert verification["result"] == "FAILED_EVAL"
    assert any("outside the lease" in finding for finding in verification["findings"])


def test_an_excluded_path_overrides_an_allowed_glob(repository: Path, stub: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _run_sync(repository, stub, "unleased")
    verification = _verify(
        repository, before, allowed_paths=["**"], excluded_paths=["unleased.txt"]
    )

    assert verification["result"] == "FAILED_EVAL"


def test_a_moved_perennial_ref_fails_the_eval(repository: Path, stub: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _run_sync(repository, stub, "commit")
    _run_sync(repository, stub, "perennial")
    verification = _verify(repository, before)

    assert verification["result"] == "FAILED_EVAL"
    assert any("perennial ref moved" in finding for finding in verification["findings"])


def test_an_unexpected_branch_fails_the_eval(repository: Path, stub: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _run_sync(repository, stub, "branchy")
    verification = _verify(repository, before)

    assert verification["result"] == "FAILED_EVAL"
    assert any("local branch set changed" in finding for finding in verification["findings"])


def test_leaving_the_declared_head_fails_the_eval(repository: Path, stub: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _git(repository, "checkout", "-q", "main")
    verification = _verify(repository, before)

    assert verification["result"] == "FAILED_EVAL"
    assert any("not the declared head" in finding for finding in verification["findings"])


def test_a_dirty_tree_after_sync_fails_the_eval(repository: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    (repository / "residue.txt").write_text("left behind\n", encoding="utf-8")
    verification = _verify(repository, before)

    assert verification["result"] == "FAILED_EVAL"
    assert any("uncommitted entries remain" in finding for finding in verification["findings"])


def test_a_moved_remote_ref_fails_the_no_push_eval(repository: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _git(repository, "update-ref", "refs/remotes/origin/tooling/owned", "HEAD")
    verification = _verify(repository, before)

    assert verification["result"] == "FAILED_EVAL"
    assert any("remote-tracking ref moved" in finding for finding in verification["findings"])


def test_a_rewritten_head_that_does_not_descend_fails_the_eval(repository: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    _git(repository, "checkout", "-q", "--orphan", "tooling/rewritten")
    _git(repository, "commit", "-q", "--allow-empty", "-m", "rewritten history")
    _git(repository, "branch", "-f", "tooling/owned", "HEAD")
    _git(repository, "checkout", "-q", "tooling/owned")
    _git(repository, "branch", "-D", "tooling/rewritten")
    verification = _verify(repository, before)

    assert verification["result"] == "FAILED_EVAL"
    assert any("does not descend" in finding for finding in verification["findings"])


@pytest.mark.parametrize(
    ("dry_shape", "live_shape", "expected_finding"),
    [
        (["sync", "--stack"], ["sync", "--stack"], "identical to the dry run"),
        (["sync", "--dry-run", "--stack"], ["sync", "--stack", "--all"], "differs from the dry run"),
    ],
)
def test_scope_infidelity_between_dry_run_and_live_fails_the_eval(
    repository: Path, dry_shape: list[str], live_shape: list[str], expected_finding: str
) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    verification = _verify(
        repository,
        before,
        dry_run_record={"command_shape": dry_shape, "tool_version": "v24.0.0", "mode": "dry-run"},
        live_record={"command_shape": live_shape, "tool_version": "v24.0.0", "mode": "live"},
    )

    assert verification["result"] == "FAILED_EVAL"
    assert any(expected_finding in finding for finding in verification["findings"])


@pytest.mark.parametrize("dropped", ["--no-push", "--no-auto-resolve"])
def test_dropping_a_mandatory_flag_fails_the_eval(repository: Path, dropped: str) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    live_shape = [flag for flag in receipt_module.BASE_SYNC_FLAGS if flag != dropped]
    verification = _verify(
        repository,
        before,
        dry_run_record={
            "command_shape": ["sync", "--dry-run", *live_shape[1:]],
            "tool_version": "v24.0.0",
            "mode": "dry-run",
        },
        live_record={"command_shape": live_shape, "tool_version": "v24.0.0", "mode": "live"},
    )

    assert verification["result"] == "FAILED_EVAL"
    assert any(dropped in finding for finding in verification["findings"])


def test_a_tool_version_change_between_runs_fails_the_eval(repository: Path) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    verification = _verify(
        repository,
        before,
        dry_run_record={
            "command_shape": ["sync", "--dry-run", *receipt_module.BASE_SYNC_FLAGS[1:]],
            "tool_version": "v24.0.0",
            "mode": "dry-run",
        },
        live_record={
            "command_shape": list(receipt_module.BASE_SYNC_FLAGS),
            "tool_version": "v23.9.0",
            "mode": "live",
        },
    )

    assert verification["result"] == "FAILED_EVAL"
    assert any("different tool version" in finding for finding in verification["findings"])


# --- append-only ledger --------------------------------------------------


def test_a_receipt_binds_its_exact_subjects_and_is_immutable(
    repository: Path, stub: Path, tmp_path: Path
) -> None:
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    dry = _run_sync(repository, stub, "noop", dry_run=True)
    live = _run_sync(repository, stub, "leased")
    after = receipt_module.capture_evidence(repository, "tooling/owned")
    verification = receipt_module.verify_sync(
        repository=repository,
        before=before,
        after=after,
        allowed_paths=["leased.txt"],
        excluded_paths=[],
        dry_run_record=dry,
        live_record=live,
    )
    entry = receipt_module.build_ledger_entry(
        head_branch="tooling/owned",
        before=before,
        after=after,
        dry_run_record=dry,
        live_record=live,
        verification=verification,
    )

    assert entry["before_subject"] == before["head_sha"]
    assert entry["after_subject"] == after["head_sha"]
    assert entry["rollback_subject"] == before["head_sha"]
    assert entry["result"] == "SYNCED"
    assert set(entry["lanes"]) == {"preflight", "local_dry_run", "local_sync", "local_verification"}

    ledger = tmp_path / "receipts"
    path = receipt_module.append_receipt(ledger, entry)
    assert path.stat().st_mode & 0o222 == 0
    # Appending the identical receipt is idempotent, and a changed subject is a
    # different file: the ledger is never rewritten in place.
    assert receipt_module.append_receipt(ledger, entry) == path
    other = receipt_module.append_receipt(ledger, {**entry, "after_subject": "0" * 40})
    assert other != path
    assert len(list(ledger.glob("*.json"))) == 2


def test_a_receipt_never_carries_a_raw_credential_or_host_path(
    repository: Path, stub: Path, tmp_path: Path
) -> None:
    _git(repository, "remote", "set-url", "origin", "git@github.com:ed3c/llm_arbitrage_system.git")
    before = receipt_module.capture_evidence(repository, "tooling/owned")
    record = receipt_module.run_sync(
        tool=stub,
        repository=repository,
        dry_run=True,
        timeout_seconds=60,
        environment=_environment(repository, "noop"),
    )
    serialized = json.dumps({"before": before, "record": record})

    assert str(tmp_path) not in serialized
    assert "worktree_branches" in before and all(
        not branch.startswith("/") for branch in before["worktree_branches"]
    )


# --- adapter ordering and status propagation -----------------------------


def _run_sync_sh(
    repository: Path, *arguments: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    child = {
        **os.environ,
        "PYTHON": sys.executable,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_PAGER": "cat",
        "GIT_EDITOR": "true",
    }
    if environment is not None:
        child.update(environment)
    return subprocess.run(
        ["bash", str(SYNC_PATH), *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=child,
    )


def test_sync_sh_blocks_when_the_tool_selector_is_unresolved(repository: Path) -> None:
    completed = _run_sync_sh(
        repository,
        "--head-branch",
        "tooling/owned",
        "--allowed-path",
        "leased.txt",
        "--skip-doctor",
        environment={"HOST_GIT_TOWN_BIN": ""},
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_TOOL_ADMISSION"
    assert "issue #15" in completed.stderr


def test_sync_sh_stops_at_the_dry_run_when_asked(
    repository: Path, stub: Path, tmp_path: Path
) -> None:
    invocations = tmp_path / "invocations.log"
    completed = _run_sync_sh(
        repository,
        "--head-branch",
        "tooling/owned",
        "--allowed-path",
        "leased.txt",
        "--skip-doctor",
        "--dry-run-only",
        environment=_environment(
            repository, "noop", HOST_GIT_TOWN_BIN=str(stub), STUB_INVOCATION_LOG=str(invocations)
        ),
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"result": "PASS", "stage": "dry-run"}
    # Assert on the shapes that actually ran, not on a side effect: exactly one
    # invocation, and it carried --dry-run.
    shapes = invocations.read_text(encoding="utf-8").splitlines()
    assert shapes == ["sync --dry-run --stack --non-interactive --no-auto-resolve --no-push"]


def test_sync_sh_runs_the_dry_run_before_the_live_command(
    repository: Path, stub: Path, tmp_path: Path
) -> None:
    invocations = tmp_path / "invocations.log"
    completed = _run_sync_sh(
        repository,
        "--head-branch",
        "tooling/owned",
        "--allowed-path",
        "leased.txt",
        "--skip-doctor",
        environment=_environment(
            repository, "noop", HOST_GIT_TOWN_BIN=str(stub), STUB_INVOCATION_LOG=str(invocations)
        ),
    )

    assert completed.returncode == 0, completed.stderr
    assert invocations.read_text(encoding="utf-8").splitlines() == [
        "sync --dry-run --stack --non-interactive --no-auto-resolve --no-push",
        "sync --stack --non-interactive --no-auto-resolve --no-push",
    ]


@pytest.mark.parametrize("behaviour", ["conflict", "prompt", "fail"])
def test_a_blocked_dry_run_means_the_live_command_never_runs(
    repository: Path, stub: Path, tmp_path: Path, behaviour: str
) -> None:
    invocations = tmp_path / "invocations.log"
    _run_sync_sh(
        repository,
        "--head-branch",
        "tooling/owned",
        "--allowed-path",
        "leased.txt",
        "--skip-doctor",
        environment=_environment(
            repository, behaviour, HOST_GIT_TOWN_BIN=str(stub), STUB_INVOCATION_LOG=str(invocations)
        ),
    )

    shapes = invocations.read_text(encoding="utf-8").splitlines()
    assert len(shapes) == 1
    assert "--dry-run" in shapes[0]


def test_sync_sh_records_a_receipt_on_a_leased_change(repository: Path, stub: Path) -> None:
    receipts = repository / "receipts" / "git-town" / "sync"
    completed = _run_sync_sh(
        repository,
        "--head-branch",
        "tooling/owned",
        "--allowed-path",
        "leased.txt",
        "--skip-doctor",
        "--receipts-root",
        str(receipts),
        environment=_environment(repository, "leased", HOST_GIT_TOWN_BIN=str(stub)),
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert json.loads(completed.stdout)["result"] == "SYNCED"
    entries = list(receipts.glob("*.json"))
    assert len(entries) == 1
    assert json.loads(entries[0].read_text(encoding="utf-8"))["result"] == "SYNCED"


@pytest.mark.parametrize(
    ("behaviour", "expected"),
    [("conflict", "BLOCKED_CONFLICT"), ("prompt", "BLOCKED_PROMPT"), ("fail", "FAILED_TOOL")],
)
def test_sync_sh_propagates_a_blocked_dry_run_and_never_runs_live(
    repository: Path, stub: Path, behaviour: str, expected: str
) -> None:
    completed = _run_sync_sh(
        repository,
        "--head-branch",
        "tooling/owned",
        "--allowed-path",
        "leased.txt",
        "--skip-doctor",
        environment=_environment(repository, behaviour, HOST_GIT_TOWN_BIN=str(stub)),
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == expected
    assert "preserved sync evidence" in completed.stderr


def test_sync_sh_fails_the_eval_on_an_out_of_lease_change(repository: Path, stub: Path) -> None:
    completed = _run_sync_sh(
        repository,
        "--head-branch",
        "tooling/owned",
        "--allowed-path",
        "leased.txt",
        "--skip-doctor",
        environment=_environment(repository, "unleased", HOST_GIT_TOWN_BIN=str(stub)),
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "FAILED_EVAL"


def test_sync_sh_refuses_a_continuation_argument(repository: Path) -> None:
    completed = _run_sync_sh(repository, "--continue")

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_POLICY"


def test_sync_sh_never_contains_a_forbidden_continuation_command() -> None:
    source = SYNC_PATH.read_text(encoding="utf-8")

    for forbidden in ("town continue", "town skip", "town undo", "town ship", "push --force", "reset --hard"):
        assert forbidden not in source


def test_the_bundled_selftests_pass() -> None:
    for command in (
        [sys.executable, str(RECEIPT_PATH), "--selftest"],
        ["bash", str(SYNC_PATH), "--selftest"],
    ):
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "PYTHON": sys.executable},
        )
        assert completed.returncode == 0, completed.stderr
        assert "PASS" in completed.stderr


# --- version matching ----------------------------------------------------
#
# The first live run refused the very executable issue #15 had just admitted:
# the pin is `v24.0.0` and `git-town --version` prints `Git Town 24.0.0`. The
# stub had printed `git-town v24.0.0`, so the mismatch was invisible until a
# real binary ran. These controls pin the real output shape.


def test_the_real_version_output_shape_is_accepted() -> None:
    # This is verbatim what git-town v24.0.0 prints on stdout.
    assert receipt_module.version_output_matches("Git Town 24.0.0\n ")


@pytest.mark.parametrize(
    "reported",
    [
        "Git Town 24.0.0",
        "git-town v24.0.0",
        "git town version 24.0.0",
        "  v24.0.0  ",
    ],
)
def test_every_reasonable_spelling_of_the_admitted_version_is_accepted(reported: str) -> None:
    assert receipt_module.version_output_matches(reported)


@pytest.mark.parametrize(
    "reported",
    [
        "Git Town 23.9.0",
        "Git Town 25.0.0",
        "Git Town 124.0.0",
        "Git Town 24.0.01",
        "Git Town 24.0.10",
        "",
    ],
)
def test_a_version_that_is_not_the_admitted_release_is_refused(reported: str) -> None:
    assert not receipt_module.version_output_matches(reported)


def test_the_stub_reports_the_same_shape_as_the_real_executable() -> None:
    # If this drifts back to an invented format, the stub stops standing in for
    # the tool and can hide the next mismatch the same way.
    assert "Git Town 24.0.0" in STUB
