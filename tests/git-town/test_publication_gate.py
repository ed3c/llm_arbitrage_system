"""E11 and E12 evals for the publication gate and remote verifier (issue #20).

The gate is offline by construction, so its controls are pure data. The remote
verifier is exercised against a real bare repository standing in for `origin`,
because "the push worked" is exactly the claim it exists to distrust.
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
GATE_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "github_snapshot.py"
REMOTE_VERIFY_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "remote_verify.py"
PUBLISH_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "publish.sh"

ADMITTED_REMOTE = "git@github.com:ed3c/llm_arbitrage_system.git"
HEAD_SHA = "a" * 40


def _load(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


gate = _load("git_town_gate", GATE_PATH)
remote_verify = _load("git_town_remote_verify", REMOTE_VERIFY_PATH)


def _snapshot(**overrides: Any) -> dict[str, Any]:
    snapshot = {
        "schema": "llm-arbitrage/github-snapshot/v1",
        "repository": "ed3c/llm_arbitrage_system",
        "pull_request_number": None,
        "base_branch": "main",
        "head_branch": "tooling/git-town-publication-gate",
        "head_sha": HEAD_SHA,
        "draft": True,
        "feedback_cursor": "review-comment-1",
        "workflow": {"head_sha": HEAD_SHA, "conclusion": "success", "run_id": 11},
        "billing": {"circuit": "closed", "reason": "within budget"},
    }
    snapshot.update(overrides)
    return snapshot


def _receipt(**overrides: Any) -> dict[str, Any]:
    receipt = {
        "head_branch": "tooling/git-town-publication-gate",
        "after_subject": HEAD_SHA,
        "result": "SYNCED",
    }
    receipt.update(overrides)
    return receipt


def _evaluate(**overrides: Any) -> dict[str, Any]:
    call: dict[str, Any] = {
        "intent": "initial-pr",
        "local_head_sha": HEAD_SHA,
        "local_receipt": _receipt(),
        "snapshot": _snapshot(),
    }
    call.update(overrides)
    result: dict[str, Any] = gate.evaluate_publication(**call)
    return result


def _blocked(**overrides: Any) -> str:
    with pytest.raises(gate.GateRejected) as rejected:
        _evaluate(**overrides)
    decision: str = rejected.value.decision
    return decision


# --- positive assertions -------------------------------------------------


@pytest.mark.parametrize(
    ("intent", "expected", "snapshot_overrides"),
    [
        ("initial-pr", "ALLOW_INITIAL_PR", {}),
        ("ready-for-review", "ALLOW_READY_FOR_REVIEW", {"pull_request_number": 62}),
        ("batched-repair", "ALLOW_BATCHED_REPAIR", {"pull_request_number": 62}),
    ],
)
def test_each_admitted_intent_returns_its_own_decision(
    intent: str, expected: str, snapshot_overrides: dict[str, Any]
) -> None:
    decision = _evaluate(intent=intent, snapshot=_snapshot(**snapshot_overrides))

    assert decision["decision"] == expected
    assert decision["authorizes_operations"] == 1
    assert len(decision["decision_sha256"]) == 64
    assert "merge" in decision["requires_human_admit_for"]


def test_the_decision_digest_changes_with_the_head() -> None:
    first = _evaluate()
    second = _evaluate(
        local_head_sha="b" * 40,
        local_receipt=_receipt(after_subject="b" * 40),
        snapshot=_snapshot(
            head_sha="b" * 40,
            workflow={"head_sha": "b" * 40, "conclusion": "success", "run_id": 11},
        ),
    )

    assert first["decision_sha256"] != second["decision_sha256"]


# --- mutation controls ---------------------------------------------------


def test_a_stale_local_receipt_is_blocked() -> None:
    assert _blocked(local_receipt=_receipt(after_subject="b" * 40)) == "BLOCKED_STALE_EVIDENCE"


def test_a_snapshot_taken_at_another_head_is_blocked() -> None:
    assert _blocked(snapshot=_snapshot(head_sha="b" * 40)) == "BLOCKED_STALE_EVIDENCE"


def test_an_old_sha_workflow_result_is_blocked() -> None:
    stale = _snapshot(workflow={"head_sha": "b" * 40, "conclusion": "success", "run_id": 9})

    assert _blocked(snapshot=stale) == "BLOCKED_STALE_EVIDENCE"


def test_a_repeated_feedback_cursor_is_blocked() -> None:
    assert _blocked(processed_feedback_cursors=["review-comment-1"]) == "BLOCKED_FEEDBACK"


def test_an_open_billing_circuit_is_blocked() -> None:
    stopped = _snapshot(billing={"circuit": "open", "reason": "monthly minutes exhausted"})

    assert _blocked(snapshot=stopped) == "BLOCKED_BILLING"


@pytest.mark.parametrize("intent", ["ship", "merge", "draft-checkpoint", "none", ""])
def test_an_unrecognized_intent_is_blocked(intent: str) -> None:
    assert _blocked(intent=intent) == "BLOCKED_POLICY"


def test_a_background_worker_may_not_request_any_intent() -> None:
    assert _blocked(background=True) == "BLOCKED_POLICY"


def test_an_initial_pr_intent_for_an_existing_pull_request_is_blocked() -> None:
    assert _blocked(snapshot=_snapshot(pull_request_number=62)) == "BLOCKED_POLICY"


@pytest.mark.parametrize("intent", ["ready-for-review", "batched-repair"])
def test_an_intent_that_needs_a_pull_request_is_blocked_without_one(intent: str) -> None:
    assert _blocked(intent=intent) == "BLOCKED_POLICY"


def test_a_ready_for_review_intent_needs_a_successful_trusted_check() -> None:
    failing = _snapshot(
        pull_request_number=62,
        workflow={"head_sha": HEAD_SHA, "conclusion": "failure", "run_id": 11},
    )

    assert _blocked(intent="ready-for-review", snapshot=failing) == "BLOCKED_POLICY"


def test_a_pull_request_already_out_of_draft_cannot_be_readied_again() -> None:
    published = _snapshot(pull_request_number=62, draft=False)

    assert _blocked(intent="ready-for-review", snapshot=published) == "BLOCKED_POLICY"


def test_a_local_receipt_that_did_not_pass_cannot_authorize_publication() -> None:
    assert _blocked(local_receipt=_receipt(result="FAILED_EVAL")) == "BLOCKED_POLICY"


def test_a_receipt_and_snapshot_describing_different_branches_are_blocked() -> None:
    assert _blocked(local_receipt=_receipt(head_branch="tooling/other")) == "BLOCKED_POLICY"


@pytest.mark.parametrize(
    "field",
    [
        "repository",
        "pull_request_number",
        "base_branch",
        "head_branch",
        "head_sha",
        "draft",
        "feedback_cursor",
        "workflow",
        "billing",
    ],
)
def test_every_missing_guard_field_is_blocked(field: str) -> None:
    incomplete = _snapshot()
    del incomplete[field]

    with pytest.raises(gate.GateRejected) as rejected:
        gate.validate_snapshot(incomplete)

    assert rejected.value.decision == "BLOCKED_POLICY"


def test_an_undeclared_snapshot_field_is_blocked() -> None:
    with pytest.raises(gate.GateRejected) as rejected:
        gate.validate_snapshot({**_snapshot(), "command": "gh pr merge"})

    assert rejected.value.decision == "BLOCKED_POLICY"


def test_a_snapshot_for_another_repository_is_blocked() -> None:
    with pytest.raises(gate.GateRejected) as rejected:
        gate.validate_snapshot(_snapshot(repository="someone-else/llm_arbitrage_system"))

    assert rejected.value.decision == "BLOCKED_POLICY"


def test_a_perennial_branch_cannot_be_a_publication_head() -> None:
    with pytest.raises(gate.GateRejected) as rejected:
        gate.validate_snapshot(_snapshot(head_branch="main", base_branch="main"))

    assert rejected.value.decision == "BLOCKED_POLICY"


# --- one ALLOW authorizes one operation ----------------------------------


def _write(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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
def published_repository(tmp_path: Path) -> dict[str, Any]:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True, timeout=120)
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "--initial-branch", "main")
    _git(work, "config", "user.email", "gate@example.invalid")
    _git(work, "config", "user.name", "gate")
    _git(work, "remote", "add", "origin", str(bare))
    (work / "file.txt").write_text("base\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "base")
    _git(work, "push", "-q", "origin", "main")
    main_sha = _git(work, "rev-parse", "HEAD")
    _git(work, "checkout", "-q", "-b", "tooling/owned")
    (work / "file.txt").write_text("owned\n", encoding="utf-8")
    _git(work, "commit", "-q", "-am", "owned change")
    _git(work, "push", "-q", "origin", "tooling/owned")
    return {
        "work": work,
        "bare": bare,
        "main_sha": main_sha,
        "head_sha": _git(work, "rev-parse", "HEAD"),
    }


def _run_publish(
    workdir: Path, *arguments: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    child = {**os.environ, "PYTHON": sys.executable}
    if environment is not None:
        child.update(environment)
    return subprocess.run(
        ["bash", str(PUBLISH_PATH), *arguments],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=child,
    )


def test_one_allow_cannot_be_spent_twice(published_repository: dict[str, Any], tmp_path: Path) -> None:
    work = published_repository["work"]
    head = published_repository["head_sha"]
    snapshot = _write(
        tmp_path / "snapshot.json",
        _snapshot(
            head_branch="tooling/owned",
            head_sha=head,
            workflow={"head_sha": head, "conclusion": "success", "run_id": 11},
        ),
    )
    receipt = _write(
        tmp_path / "receipt.json", _receipt(head_branch="tooling/owned", after_subject=head)
    )
    ledger = tmp_path / "decisions"

    first = _run_publish(
        work,
        "--intent", "initial-pr",
        "--head-branch", "tooling/owned",
        "--receipt", str(receipt),
        "--snapshot", str(snapshot),
        "--decisions-ledger", str(ledger),
    )
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout)["decision"] == "ALLOW_INITIAL_PR"

    second = _run_publish(
        work,
        "--intent", "initial-pr",
        "--head-branch", "tooling/owned",
        "--receipt", str(receipt),
        "--snapshot", str(snapshot),
        "--decisions-ledger", str(ledger),
    )
    assert second.returncode == 1
    assert json.loads(second.stdout)["decision"] == "BLOCKED_POLICY"
    assert "already spent" in second.stderr


def test_the_gate_blocks_when_the_repository_is_on_another_branch(
    published_repository: dict[str, Any], tmp_path: Path
) -> None:
    work = published_repository["work"]
    _git(work, "checkout", "-q", "main")

    completed = _run_publish(
        work,
        "--intent", "initial-pr",
        "--head-branch", "tooling/owned",
        "--receipt", str(_write(tmp_path / "r.json", _receipt())),
        "--snapshot", str(_write(tmp_path / "s.json", _snapshot())),
        "--decisions-ledger", str(tmp_path / "decisions"),
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["decision"] == "BLOCKED_POLICY"


def test_the_gate_blocks_without_a_resolved_decisions_selector(
    published_repository: dict[str, Any], tmp_path: Path
) -> None:
    completed = _run_publish(
        published_repository["work"],
        "--intent", "initial-pr",
        "--head-branch", "tooling/owned",
        "--receipt", str(_write(tmp_path / "r.json", _receipt())),
        "--snapshot", str(_write(tmp_path / "s.json", _snapshot())),
        environment={"HOST_LLM_ARBITRAGE_DECISIONS": ""},
    )

    assert completed.returncode == 1
    assert "HOST_LLM_ARBITRAGE_DECISIONS" in completed.stderr


def test_publish_refuses_an_unsupported_argument(published_repository: dict[str, Any]) -> None:
    completed = _run_publish(published_repository["work"], "--push")

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["decision"] == "BLOCKED_POLICY"


def test_publish_never_pushes_or_merges() -> None:
    source = PUBLISH_PATH.read_text(encoding="utf-8")

    for forbidden in ("git push", "gh pr merge", "gh pr ready", "gh workflow run", "--force"):
        assert forbidden not in source


# --- remote verification -------------------------------------------------


def _admit_local_origin(
    published_repository: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Treat the local bare repository as the admitted remote for one test.

    `git remote get-url` resolves `insteadOf` rewrites, so the admission check
    sees the *effective* URL. That behaviour is worth keeping — a host-level
    redirect must not smuggle an unadmitted remote past the policy — so these
    tests widen the admitted set instead of redirecting an admitted URL.
    """

    monkeypatch.setattr(remote_verify, "ADMITTED_REMOTES", (str(published_repository["bare"]),))
    monkeypatch.setattr(remote_verify, "redact_remote", lambda url: "ssh://github.com")
    return published_repository["work"]


def test_a_matching_remote_head_verifies(
    published_repository: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _admit_local_origin(published_repository, monkeypatch)

    verification = remote_verify.verify_remote(
        repository=work,
        remote="origin",
        head_branch="tooling/owned",
        expected_head_sha=published_repository["head_sha"],
        expected_parent_sha=published_repository["main_sha"],
        protected_before={"main": published_repository["main_sha"]},
    )

    assert verification["result"] == "PASS"
    assert verification["remote"] == "ssh://github.com"
    assert verification["observed_head_sha"] == published_repository["head_sha"]


def test_a_mismatched_remote_head_fails_the_eval(
    published_repository: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _admit_local_origin(published_repository, monkeypatch)

    verification = remote_verify.verify_remote(
        repository=work,
        remote="origin",
        head_branch="tooling/owned",
        expected_head_sha="b" * 40,
    )

    assert verification["result"] == "FAILED_EVAL"
    assert any("remote head is" in finding for finding in verification["findings"])


def test_a_rewritten_protected_ref_fails_the_eval(
    published_repository: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _admit_local_origin(published_repository, monkeypatch)
    # Someone rewrote the protected branch on the remote, out of band.
    _git(work, "push", "-q", "--force", "origin", "tooling/owned:main")

    verification = remote_verify.verify_remote(
        repository=work,
        remote="origin",
        head_branch="tooling/owned",
        expected_head_sha=published_repository["head_sha"],
        protected_before={"main": published_repository["main_sha"]},
    )

    assert verification["result"] == "FAILED_EVAL"
    assert any("was rewritten" in finding for finding in verification["findings"])


def test_a_branch_absent_from_the_remote_fails_the_eval(
    published_repository: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _admit_local_origin(published_repository, monkeypatch)

    verification = remote_verify.verify_remote(
        repository=work,
        remote="origin",
        head_branch="tooling/never-pushed",
        expected_head_sha=published_repository["head_sha"],
    )

    assert verification["result"] == "FAILED_EVAL"
    assert any("does not exist on the remote" in finding for finding in verification["findings"])


def test_an_unadmitted_remote_is_refused(published_repository: dict[str, Any]) -> None:
    work = published_repository["work"]
    _git(work, "remote", "set-url", "origin", "git@github.com:someone-else/repo.git")

    with pytest.raises(remote_verify.RemoteRejected) as rejected:
        remote_verify.verify_remote(
            repository=work,
            remote="origin",
            head_branch="tooling/owned",
            expected_head_sha=published_repository["head_sha"],
        )

    assert rejected.value.result == "BLOCKED_POLICY"


def test_remote_verification_requires_an_explicit_fetch() -> None:
    source = REMOTE_VERIFY_PATH.read_text(encoding="utf-8")

    # Without the fetch, every comparison reads stale local knowledge of the
    # remote and agrees with itself.
    assert '"fetch", "--prune", remote' in source


def test_the_bundled_selftests_pass() -> None:
    for command in (
        [sys.executable, str(GATE_PATH), "--selftest"],
        [sys.executable, str(REMOTE_VERIFY_PATH), "--selftest"],
        ["bash", str(PUBLISH_PATH), "--selftest"],
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
