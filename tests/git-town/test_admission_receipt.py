"""Controls for the GT-01 admission receipt builder (issue #15).

The property that matters is the one an admission receipt exists to protect:
`PASS` requires *every* required lane, and a lane nobody decided blocks
admission rather than defaulting into it. Each control below plants exactly one
disagreement and asserts the result goes red.
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
BUILDER_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "admission_receipt.py"
WIZARD_PATH = REPOSITORY_ROOT / "scripts" / "git-town" / "admit.sh"


def _load(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


admission = _load("git_town_admission_receipt", BUILDER_PATH)

PINS: dict[str, Any] = {
    "required_version": "v24.0.0",
    "upstream_repository": "git-town/git-town",
    "release_id": 358702660,
    "immutable_tag_commit": "0f3e55f5a6bae5b319dd713a0606263d0551af66",
    "host_os": "Darwin",
    "host_arch": "arm64",
    "artifact_name": "git-town_macos_arm_64.tar.gz",
    "artifact_sha256": "a" * 64,
    "executable_sha256": "b" * 64,
    "version_output": "git-town 24.0.0",
}


def _all_pass() -> dict[str, dict[str, str]]:
    return {name: {"state": "PASS", "detail": "ok"} for name in admission.REQUIRED_LANES}


def _build(lanes: dict[str, dict[str, str]], **overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = admission.build_receipt(lanes, **{**PINS, **overrides})
    return result


# --- positive assertion --------------------------------------------------


def test_every_lane_passing_admits_the_tool() -> None:
    receipt = _build(_all_pass())

    assert receipt["result"] == "PASS"
    assert receipt["live_execution_admitted"] is True
    assert receipt["blocked_lanes"] == []
    assert receipt["schema"] == "llm-arbitrage/git-town-admission-receipt/v1"
    assert receipt["repository"] == "ed3c/llm_arbitrage_system"


# --- one lane at a time --------------------------------------------------


@pytest.mark.parametrize("lane", admission.REQUIRED_LANES)
@pytest.mark.parametrize("state", ["FAIL", "NOT_EXERCISED"])
def test_any_single_lane_blocks_admission(lane: str, state: str) -> None:
    lanes = _all_pass()
    lanes[lane] = {"state": state, "detail": "planted"}

    receipt = _build(lanes)

    assert receipt["result"] == "BLOCKED_TOOL_ADMISSION"
    assert receipt["live_execution_admitted"] is False
    assert receipt["blocked_lanes"] == [lane]


def test_an_omitted_lane_becomes_not_exercised_rather_than_absent() -> None:
    receipt = _build({"repository_policy_pins": {"state": "PASS", "detail": "ok"}})

    assert set(receipt["lanes"]) == set(admission.REQUIRED_LANES)
    assert receipt["lanes"]["organization_legal_approval"]["state"] == "NOT_EXERCISED"
    assert receipt["result"] == "BLOCKED_TOOL_ADMISSION"


def test_fail_and_not_exercised_stay_distinguishable() -> None:
    lanes = _all_pass()
    lanes["sbom_or_transitive_review"] = {"state": "NOT_EXERCISED", "detail": "no named owner"}
    lanes["required_notices_review"] = {"state": "FAIL", "detail": "rejected by owner"}

    receipt = _build(lanes)

    assert receipt["lanes"]["sbom_or_transitive_review"]["state"] == "NOT_EXERCISED"
    assert receipt["lanes"]["required_notices_review"]["state"] == "FAIL"
    assert receipt["blocked_lanes"] == ["required_notices_review", "sbom_or_transitive_review"]


def test_the_human_owned_lanes_are_all_required() -> None:
    # These three are exactly what issue #15 defers to a person. If any of them
    # ever left the required set, a machine could admit the tool alone.
    for lane in (
        "artifact_acquisition",
        "sbom_or_transitive_review",
        "required_notices_review",
        "organization_legal_approval",
    ):
        assert lane in admission.REQUIRED_LANES


def test_a_direct_license_pass_alone_cannot_admit() -> None:
    # docs/git/GIT_TOWN_ADMISSION.md: the direct MIT license alone is insufficient.
    receipt = _build({"direct_license_identity": {"state": "PASS", "detail": "MIT reviewed"}})

    assert receipt["result"] == "BLOCKED_TOOL_ADMISSION"


# --- ledger parsing ------------------------------------------------------


def test_a_valid_ledger_round_trips() -> None:
    lanes = admission.parse_lanes(
        "repository_policy_pins\tPASS\tprofile agrees\n"
        "organization_legal_approval\tNOT_EXERCISED\tno named approver\n"
    )

    assert lanes["repository_policy_pins"]["state"] == "PASS"
    assert lanes["organization_legal_approval"]["detail"] == "no named approver"


@pytest.mark.parametrize(
    "line",
    [
        "name\tMAYBE\tdetail",
        "name\tpass\tdetail",
        "name\tPASS",
        "name",
    ],
)
def test_a_malformed_ledger_line_is_refused(line: str) -> None:
    with pytest.raises(ValueError):
        admission.parse_lanes(line)


# --- receipt file --------------------------------------------------------


def test_the_receipt_is_content_addressed_read_only_and_idempotent(tmp_path: Path) -> None:
    receipt = _build(_all_pass())
    path = admission.write_receipt(receipt, tmp_path)

    assert path.name.endswith(".json")
    assert path.stat().st_mode & 0o222 == 0
    assert json.loads(path.read_text(encoding="utf-8"))["result"] == "PASS"
    assert admission.write_receipt(receipt, tmp_path) == path

    blocked = _build({})
    other = admission.write_receipt(blocked, tmp_path)
    assert other != path
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_a_receipt_carries_no_absolute_host_path(tmp_path: Path) -> None:
    receipt = _build(_all_pass())
    serialized = json.dumps(receipt)

    assert str(tmp_path) not in serialized
    assert "/Users/" not in serialized
    assert "/home/" not in serialized


# --- the wizard ----------------------------------------------------------


def test_the_wizard_never_defaults_a_lane_to_pass() -> None:
    source = WIZARD_PATH.read_text(encoding="utf-8")

    # Every human-decision stage must have a SKIP path that records
    # NOT_EXERCISED rather than falling through to a pass.
    for lane in (
        "artifact_acquisition",
        "sbom_or_transitive_review",
        "required_notices_review",
        "organization_legal_approval",
    ):
        assert f'record_lane "{lane}" "NOT_EXERCISED"' in source, lane


def test_the_wizard_commits_no_binary_and_deletes_no_evidence() -> None:
    source = WIZARD_PATH.read_text(encoding="utf-8")

    for forbidden in ("git add", "git commit", "rm -rf", "rm -r "):
        assert forbidden not in source, forbidden


def test_the_wizard_refuses_a_mutable_acquisition_selector() -> None:
    source = WIZARD_PATH.read_text(encoding="utf-8")

    assert "releases/latest" not in source
    assert "358702660" in source


# --- reporting -----------------------------------------------------------
#
# The first version of this reporting path shipped a SyntaxError that only
# fired when a lane was blocked, because nothing had ever rendered a blocked
# receipt. These controls exist so that cannot recur.


def test_explaining_an_admitted_receipt_lists_nothing() -> None:
    assert admission.explain(_build(_all_pass())) == []


def test_explaining_a_blocked_receipt_lists_every_non_passing_lane() -> None:
    lanes = _all_pass()
    lanes["organization_legal_approval"] = {"state": "NOT_EXERCISED", "detail": "no named approver"}
    lanes["required_notices_review"] = {"state": "FAIL", "detail": "rejected by owner"}

    lines = admission.explain(_build(lanes))

    assert len(lines) == 2
    assert any("organization_legal_approval" in line and "NOT_EXERCISED" in line for line in lines)
    assert any("required_notices_review" in line and "FAIL" in line for line in lines)


def test_explain_reports_in_the_required_lane_order() -> None:
    lines = admission.explain(_build({}))

    assert len(lines) == len(admission.REQUIRED_LANES)
    order = [line.split()[1] for line in lines]
    assert order == list(admission.REQUIRED_LANES)


@pytest.mark.parametrize("mode", ["--result", "--explain"])
def test_the_entrypoint_reads_a_blocked_receipt_without_crashing(tmp_path: Path, mode: str) -> None:
    path = admission.write_receipt(_build({}), tmp_path)

    completed = subprocess.run(
        [sys.executable, str(BUILDER_PATH), mode, str(path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Traceback" not in completed.stderr
    if mode == "--result":
        assert completed.stdout.strip() == "BLOCKED_TOOL_ADMISSION"
    else:
        assert completed.stdout.count("\n") == len(admission.REQUIRED_LANES)


def test_reading_a_document_that_is_not_a_receipt_is_refused(tmp_path: Path) -> None:
    impostor = tmp_path / "not-a-receipt.json"
    impostor.write_text('{"schema": "something/else", "result": "PASS"}', encoding="utf-8")

    with pytest.raises(ValueError):
        admission.read_receipt(impostor)


def test_the_wizard_reads_receipts_through_the_module_not_an_inline_snippet() -> None:
    source = WIZARD_PATH.read_text(encoding="utf-8")

    assert "admission_receipt.py" in source
    assert "--result" in source
    assert "--explain" in source
    # An inline snippet is what broke before: quoting a nested f-string through
    # the shell is not something to re-attempt.
    assert "python3 -c" not in source


def test_the_bundled_selftest_passes() -> None:
    completed = subprocess.run(
        [sys.executable, str(BUILDER_PATH), "--selftest"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
        env={**os.environ},
    )

    assert completed.returncode == 0, completed.stderr
    assert "PASS" in completed.stderr
