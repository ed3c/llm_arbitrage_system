"""E05 evals for the worktree and branch-lease doctor (issue #17).

The judge is exercised directly with synthetic facts, and `doctor.sh` is
exercised against real linked worktrees so the fact-collection layer is covered
by the same controls rather than assumed correct.
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
LEASE_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "lease.py"
DOCTOR_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "doctor.sh"

ADMITTED_REMOTE = "git@github.com:ed3c/llm_arbitrage_system.git"
PROMPT_POLICY = {"GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "GIT_EDITOR": "true"}


def _load(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


lease_module = _load("git_town_lease", LEASE_PATH)


def _facts(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    git_dir = tmp_path / "linked" / ".git"
    common_dir = tmp_path / "primary" / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    common_dir.mkdir(parents=True, exist_ok=True)
    facts: dict[str, Any] = {
        "head_branch": "tooling/git-town-worktree-doctor",
        "current_branch": "tooling/git-town-worktree-doctor",
        "git_dir": git_dir,
        "git_common_dir": common_dir,
        "remote_url": ADMITTED_REMOTE,
        "dirty_entries": 0,
        "allowed_paths": ["scripts/git-town/doctor.sh"],
        "lease_root": tmp_path / "leases",
        "holder": "worker-under-test",
        "ttl_seconds": 3600,
        "now": 1_000.0,
        "environment": dict(PROMPT_POLICY),
    }
    facts.update(overrides)
    return facts


def _rejection(tmp_path: Path, **overrides: Any) -> str:
    with pytest.raises(lease_module.DoctorRejected) as rejected:
        lease_module.run_doctor(**_facts(tmp_path, **overrides))
    result: str = rejected.value.result
    return result


# --- positive assertions -------------------------------------------------


def test_an_admitted_linked_worktree_passes_and_takes_its_lease(tmp_path: Path) -> None:
    receipt = lease_module.run_doctor(**_facts(tmp_path))

    assert receipt["result"] == "PASS"
    assert receipt["repository"] == "ed3c/llm_arbitrage_system"
    assert receipt["worktree_git_dir_is_linked"] is True
    assert receipt["lease_expires_at"] == 1_000.0 + 3600
    assert lease_module.live_leases(tmp_path / "leases", 1_000.0)


def test_the_receipt_names_prompt_policy_variables_and_never_their_values(tmp_path: Path) -> None:
    receipt = lease_module.run_doctor(
        **_facts(tmp_path, environment={**PROMPT_POLICY, "GIT_TERMINAL_PROMPT": "sentinel-value"})
    )

    assert receipt["prompt_policy_variables_present"] == [
        "GIT_TERMINAL_PROMPT",
        "GIT_PAGER",
        "GIT_EDITOR",
    ]
    assert "sentinel-value" not in json.dumps(receipt)


def test_the_receipt_redacts_the_remote_to_scheme_and_host(tmp_path: Path) -> None:
    receipt = lease_module.run_doctor(**_facts(tmp_path))

    assert receipt["remote"] == "ssh://github.com"
    assert "ed3c/llm_arbitrage_system.git" not in json.dumps(receipt)


def test_the_same_holder_may_reassert_its_own_live_lease(tmp_path: Path) -> None:
    lease_module.run_doctor(**_facts(tmp_path))

    assert lease_module.run_doctor(**_facts(tmp_path, now=1_100.0))["result"] == "PASS"


# --- mutation controls ---------------------------------------------------


def test_the_primary_checkout_is_refused(tmp_path: Path) -> None:
    shared = tmp_path / "primary" / ".git"
    shared.mkdir(parents=True)

    assert _rejection(tmp_path, git_dir=shared, git_common_dir=shared) == "BLOCKED_POLICY"


@pytest.mark.parametrize(
    "remote_url",
    [
        "https://someone-else@github.com/other/repo.git",
        "https://github.com/other/llm_arbitrage_system.git",
        "git@gitlab.com:ed3c/llm_arbitrage_system.git",
    ],
)
def test_a_wrong_repository_identity_is_refused(tmp_path: Path, remote_url: str) -> None:
    assert _rejection(tmp_path, remote_url=remote_url) == "BLOCKED_POLICY"


@pytest.mark.parametrize(
    "remote_url",
    [
        "https://worker:ghp_secret@github.com/ed3c/llm_arbitrage_system.git",
        "https://x-access-token:secret@github.com/ed3c/llm_arbitrage_system.git",
    ],
)
def test_a_credential_bearing_remote_is_refused(tmp_path: Path, remote_url: str) -> None:
    with pytest.raises(lease_module.DoctorRejected) as rejected:
        lease_module.run_doctor(**_facts(tmp_path, remote_url=remote_url))

    assert rejected.value.result == "BLOCKED_POLICY"
    assert "secret" not in rejected.value.reason


def test_a_dirty_worktree_is_refused(tmp_path: Path) -> None:
    assert _rejection(tmp_path, dirty_entries=3) == "BLOCKED_DIRTY"


@pytest.mark.parametrize(
    "marker", ["MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG"]
)
def test_an_in_progress_git_operation_is_refused(tmp_path: Path, marker: str) -> None:
    facts = _facts(tmp_path)
    (facts["git_dir"] / marker).write_text("", encoding="utf-8")

    with pytest.raises(lease_module.DoctorRejected) as rejected:
        lease_module.run_doctor(**facts)

    assert rejected.value.result == "BLOCKED_DIRTY"


def test_being_on_the_wrong_branch_is_an_ancestry_block(tmp_path: Path) -> None:
    assert _rejection(tmp_path, current_branch="main") == "BLOCKED_ANCESTRY"


def test_a_duplicate_branch_lease_is_refused(tmp_path: Path) -> None:
    lease_module.run_doctor(**_facts(tmp_path, holder="worker-a"))

    assert _rejection(tmp_path, holder="worker-b") == "BLOCKED_BRANCH_LEASE"


def test_an_overlapping_path_lease_is_refused(tmp_path: Path) -> None:
    lease_module.run_doctor(**_facts(tmp_path, holder="worker-a"))

    assert (
        _rejection(
            tmp_path,
            head_branch="tooling/other",
            current_branch="tooling/other",
            holder="worker-b",
            allowed_paths=["scripts/**"],
        )
        == "BLOCKED_BRANCH_LEASE"
    )


def test_a_disjoint_sibling_lease_is_admitted(tmp_path: Path) -> None:
    lease_module.run_doctor(**_facts(tmp_path, holder="worker-a"))
    sibling = lease_module.run_doctor(
        **_facts(
            tmp_path,
            head_branch="tooling/other",
            current_branch="tooling/other",
            holder="worker-b",
            allowed_paths=["docs/harness/git-town-doctor.md"],
        )
    )

    assert sibling["result"] == "PASS"


def test_an_expired_lease_cannot_be_renewed_but_frees_its_paths(tmp_path: Path) -> None:
    root = tmp_path / "leases"
    lease_module.run_doctor(**_facts(tmp_path, holder="worker-a", ttl_seconds=60))

    with pytest.raises(lease_module.DoctorRejected) as rejected:
        lease_module.renew_lease(
            root, branch="tooling/git-town-worktree-doctor", holder="worker-a", now=5_000.0
        )
    assert rejected.value.result == "BLOCKED_BRANCH_LEASE"
    assert lease_module.live_leases(root, 5_000.0) == []
    assert lease_module.run_doctor(**_facts(tmp_path, holder="worker-b", now=5_000.0))["result"] == "PASS"


def test_a_live_lease_renews_within_its_window(tmp_path: Path) -> None:
    root = tmp_path / "leases"
    lease_module.run_doctor(**_facts(tmp_path, holder="worker-a", ttl_seconds=60))
    renewed = lease_module.renew_lease(
        root, branch="tooling/git-town-worktree-doctor", holder="worker-a", now=1_030.0
    )

    assert renewed["expires_at"] == 1_090.0


def test_another_worker_cannot_renew_or_release_a_lease(tmp_path: Path) -> None:
    root = tmp_path / "leases"
    lease_module.run_doctor(**_facts(tmp_path, holder="worker-a"))

    for operation in (lease_module.renew_lease, lease_module.release_lease):
        with pytest.raises(lease_module.DoctorRejected) as rejected:
            if operation is lease_module.renew_lease:
                operation(root, branch="tooling/git-town-worktree-doctor", holder="thief", now=1_100.0)
            else:
                operation(root, branch="tooling/git-town-worktree-doctor", holder="thief")
        assert rejected.value.result == "BLOCKED_BRANCH_LEASE"


@pytest.mark.parametrize("absent", ["GIT_TERMINAL_PROMPT", "GIT_PAGER", "GIT_EDITOR"])
def test_missing_prompt_suppression_is_refused(tmp_path: Path, absent: str) -> None:
    environment = {name: value for name, value in PROMPT_POLICY.items() if name != absent}

    with pytest.raises(lease_module.DoctorRejected) as rejected:
        lease_module.run_doctor(**_facts(tmp_path, environment=environment))

    assert rejected.value.result == "BLOCKED_POLICY"
    assert absent in rejected.value.reason


def test_no_lease_is_taken_when_any_precondition_fails(tmp_path: Path) -> None:
    _rejection(tmp_path, dirty_entries=1)

    assert lease_module.live_leases(tmp_path / "leases", 1_000.0) == []


# --- doctor.sh against real worktrees ------------------------------------


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
    primary = tmp_path / "primary"
    primary.mkdir()
    _git(primary, "init", "--initial-branch", "main")
    _git(primary, "config", "user.email", "doctor@example.invalid")
    _git(primary, "config", "user.name", "doctor")
    _git(primary, "remote", "add", "origin", ADMITTED_REMOTE)
    (primary / "README.md").write_text("doctor fixture\n", encoding="utf-8")
    _git(primary, "add", "README.md")
    _git(primary, "commit", "-m", "fixture")
    return primary


def _run_doctor_sh(
    workdir: Path, *arguments: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    child = {**os.environ, **PROMPT_POLICY, "PYTHON": sys.executable}
    if environment is not None:
        child.update(environment)
    return subprocess.run(
        ["bash", str(DOCTOR_PATH), *arguments],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env=child,
    )


def test_doctor_sh_admits_a_real_linked_worktree(repository: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    _git(repository, "worktree", "add", "-b", "tooling/canary", str(linked))

    completed = _run_doctor_sh(
        linked,
        "--head-branch",
        "tooling/canary",
        "--allowed-path",
        "docs/harness/git-town-doctor.md",
        environment={"HOST_LLM_ARBITRAGE_LEASES": str(tmp_path / "leases")},
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["result"] == "PASS"
    assert receipt["remote"] == "ssh://github.com"


def test_doctor_sh_refuses_the_primary_checkout(repository: Path, tmp_path: Path) -> None:
    completed = _run_doctor_sh(
        repository,
        "--head-branch",
        "main",
        "--allowed-path",
        "README.md",
        environment={"HOST_LLM_ARBITRAGE_LEASES": str(tmp_path / "leases")},
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_POLICY"


def test_doctor_sh_reports_a_real_dirty_worktree(repository: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    _git(repository, "worktree", "add", "-b", "tooling/canary", str(linked))
    (linked / "drift.txt").write_text("uncommitted\n", encoding="utf-8")

    completed = _run_doctor_sh(
        linked,
        "--head-branch",
        "tooling/canary",
        "--allowed-path",
        "docs/harness/git-town-doctor.md",
        environment={"HOST_LLM_ARBITRAGE_LEASES": str(tmp_path / "leases")},
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_DIRTY"


def test_doctor_sh_refuses_a_detached_head(repository: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    _git(repository, "worktree", "add", "--detach", str(linked))

    completed = _run_doctor_sh(
        linked,
        "--head-branch",
        "tooling/canary",
        "--allowed-path",
        "docs/harness/git-town-doctor.md",
        environment={"HOST_LLM_ARBITRAGE_LEASES": str(tmp_path / "leases")},
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_ANCESTRY"


def test_doctor_sh_refuses_an_unresolved_lease_selector(repository: Path, tmp_path: Path) -> None:
    linked = tmp_path / "linked"
    _git(repository, "worktree", "add", "-b", "tooling/canary", str(linked))

    completed = _run_doctor_sh(
        linked,
        "--head-branch",
        "tooling/canary",
        "--allowed-path",
        "docs/harness/git-town-doctor.md",
        environment={"HOST_LLM_ARBITRAGE_LEASES": ""},
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_POLICY"
    assert "HOST_LLM_ARBITRAGE_LEASES" in completed.stderr


def test_doctor_sh_refuses_an_unsupported_argument(repository: Path, tmp_path: Path) -> None:
    completed = _run_doctor_sh(
        repository,
        "--run",
        "git town ship",
        environment={"HOST_LLM_ARBITRAGE_LEASES": str(tmp_path / "leases")},
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_POLICY"


def test_doctor_sh_never_places_the_remote_url_in_argv(repository: Path, tmp_path: Path) -> None:
    source = DOCTOR_PATH.read_text(encoding="utf-8")

    assert "--remote-url-from-stdin" in source
    assert "--remote-url " not in source
    assert "git remote get-url origin | " in source


def test_the_bundled_selftests_pass() -> None:
    for command in (
        [sys.executable, str(LEASE_PATH), "--selftest"],
        ["bash", str(DOCTOR_PATH), "--selftest"],
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
