#!/usr/bin/env python3
"""Build the GT-01 host admission receipt from a lane ledger (issue #15).

`scripts/git-town/admit.sh` measures what can be measured and asks a human for
the decisions issue #15 defers to a person. This module turns the resulting
lane ledger into one content-addressed, read-only receipt.

The whole point is the last rule: the admission result is ``PASS`` only when
*every* repository-required lane is ``PASS``. A lane nobody decided is
``NOT_EXERCISED``, and `docs/git/GIT_TOWN_ADMISSION.md` is explicit that an
absent lane blocks admission rather than defaulting to it. Tool presence, a
version string and the direct MIT license are each insufficient on their own.

Inputs arrive through the environment so the shell never has to quote JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from collections.abc import Mapping, Sequence
from typing import Any

RECEIPT_SCHEMA = "llm-arbitrage/git-town-admission-receipt/v1"
REPOSITORY = "ed3c/llm_arbitrage_system"
BLOCKED = "BLOCKED_TOOL_ADMISSION"

VALID_STATES = frozenset({"PASS", "FAIL", "NOT_EXERCISED"})

# Every lane docs/git/GIT_TOWN_ADMISSION.md requires. Order is the reporting
# order; membership is the admission rule.
REQUIRED_LANES = (
    "repository_policy_pins",
    "host_platform_architecture",
    "artifact_acquisition",
    "checksums_manifest",
    "artifact_sha256",
    "installed_executable_sha256",
    "executable_version_output",
    "direct_license_identity",
    "sbom_or_transitive_review",
    "required_notices_review",
    "organization_legal_approval",
    "repository_config_compatibility",
)


def parse_lanes(text: str) -> dict[str, dict[str, str]]:
    """Read the tab-separated ledger the wizard appends to."""

    lanes: dict[str, dict[str, str]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            raise ValueError(f"lane ledger line {number} is not name/state/detail")
        name, state, detail = parts
        if state not in VALID_STATES:
            raise ValueError(f"lane {name} has state {state!r}, expected one of {sorted(VALID_STATES)}")
        lanes[name] = {"state": state, "detail": detail}
    return lanes


def build_receipt(
    lanes: Mapping[str, Mapping[str, str]],
    *,
    required_version: str,
    upstream_repository: str,
    release_id: int,
    immutable_tag_commit: str,
    host_os: str,
    host_arch: str,
    artifact_name: str | None,
    artifact_sha256: str | None,
    executable_sha256: str | None,
    version_output: str | None,
    required: Sequence[str] = REQUIRED_LANES,
) -> dict[str, Any]:
    """Assemble the receipt and decide the admission result."""

    resolved = {
        name: dict(lanes.get(name, {"state": "NOT_EXERCISED", "detail": "not reached"}))
        for name in required
    }
    # PASS demands every required lane. FAIL and NOT_EXERCISED both block, and
    # they stay distinguishable in the receipt so a reader can tell "we looked
    # and it was wrong" from "nobody looked".
    result = "PASS" if all(lane["state"] == "PASS" for lane in resolved.values()) else BLOCKED

    return {
        "schema": RECEIPT_SCHEMA,
        "repository": REPOSITORY,
        "required_version": required_version,
        "upstream_repository": upstream_repository,
        "release_id": release_id,
        "immutable_tag_commit": immutable_tag_commit,
        "host": {"os": host_os, "arch": host_arch},
        "artifact": {"name": artifact_name or None, "sha256": artifact_sha256 or None},
        "executable": {"sha256": executable_sha256 or None, "version_output": version_output or None},
        "lanes": resolved,
        "blocked_lanes": sorted(name for name, lane in resolved.items() if lane["state"] != "PASS"),
        "result": result,
        # Never inferred from anything weaker than the full lane set.
        "live_execution_admitted": result == "PASS",
    }


def write_receipt(receipt: Mapping[str, Any], receipt_dir: pathlib.Path) -> pathlib.Path:
    """Write one immutable, content-addressed receipt."""

    receipt_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    path = receipt_dir / f"{hashlib.sha256(body).hexdigest()}.json"
    if path.exists():
        return path
    path.write_bytes(body + b"\n")
    path.chmod(0o444)
    return path


def _from_environment() -> dict[str, Any]:
    ledger = pathlib.Path(os.environ["LANES_FILE"])
    return {
        "lanes": parse_lanes(ledger.read_text(encoding="utf-8")),
        "required_version": os.environ["REQUIRED_VERSION"],
        "upstream_repository": os.environ["UPSTREAM_REPO"],
        "release_id": int(os.environ["RELEASE_ID"]),
        "immutable_tag_commit": os.environ["TAG_COMMIT"],
        "host_os": os.environ["HOST_OS"],
        "host_arch": os.environ["HOST_ARCH"],
        "artifact_name": os.environ.get("ARTIFACT_NAME") or None,
        "artifact_sha256": os.environ.get("ARTIFACT_SHA") or None,
        "executable_sha256": os.environ.get("EXECUTABLE_SHA") or None,
        "version_output": os.environ.get("VERSION_OUTPUT") or None,
    }


def read_receipt(path: pathlib.Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, Mapping) or loaded.get("schema") != RECEIPT_SCHEMA:
        raise ValueError(f"{path.name} is not a {RECEIPT_SCHEMA} document")
    return dict(loaded)


def explain(receipt: Mapping[str, Any]) -> list[str]:
    """One line per lane that is not PASS, in reporting order."""

    lanes = receipt["lanes"]
    return [
        f"    {lanes[name]['state']:<15} {name}  -  {lanes[name]['detail']}"
        for name in REQUIRED_LANES
        if name in lanes and lanes[name]["state"] != "PASS"
    ]


def _run_selftest() -> int:
    every_lane_passes = {name: {"state": "PASS", "detail": "ok"} for name in REQUIRED_LANES}
    admitted = build_receipt(
        every_lane_passes,
        required_version="v24.0.0",
        upstream_repository="git-town/git-town",
        release_id=358702660,
        immutable_tag_commit="0" * 40,
        host_os="Darwin",
        host_arch="arm64",
        artifact_name="git-town_macos_arm_64.tar.gz",
        artifact_sha256="a" * 64,
        executable_sha256="b" * 64,
        version_output="git-town 24.0.0",
    )
    assert admitted["result"] == "PASS"
    assert admitted["live_execution_admitted"] is True
    assert admitted["blocked_lanes"] == []

    # One lane at a time: every required lane must be able to block admission
    # on its own, in both non-PASS states.
    for lane in REQUIRED_LANES:
        for state in ("FAIL", "NOT_EXERCISED"):
            degraded = dict(every_lane_passes)
            degraded[lane] = {"state": state, "detail": "planted"}
            receipt = build_receipt(
                degraded,
                required_version="v24.0.0",
                upstream_repository="git-town/git-town",
                release_id=358702660,
                immutable_tag_commit="0" * 40,
                host_os="Darwin",
                host_arch="arm64",
                artifact_name=None,
                artifact_sha256=None,
                executable_sha256=None,
                version_output=None,
            )
            assert receipt["result"] == BLOCKED, (lane, state)
            assert receipt["live_execution_admitted"] is False, (lane, state)
            assert receipt["blocked_lanes"] == [lane], (lane, state)

    # An omitted lane is NOT_EXERCISED, never silently absent.
    partial = build_receipt(
        {"repository_policy_pins": {"state": "PASS", "detail": "ok"}},
        required_version="v24.0.0",
        upstream_repository="git-town/git-town",
        release_id=358702660,
        immutable_tag_commit="0" * 40,
        host_os="Linux",
        host_arch="x86_64",
        artifact_name=None,
        artifact_sha256=None,
        executable_sha256=None,
        version_output=None,
    )
    assert set(partial["lanes"]) == set(REQUIRED_LANES)
    assert partial["lanes"]["organization_legal_approval"]["state"] == "NOT_EXERCISED"
    assert partial["result"] == BLOCKED

    for bad in ("name\tMAYBE\tdetail", "name\tPASS"):
        try:
            parse_lanes(bad)
        except ValueError:
            pass
        else:  # pragma: no cover - a silent pass here is the defect being guarded
            raise AssertionError(f"ledger line {bad!r} should have been rejected")

    # The reporting path is exercised too. Its first version shipped a
    # SyntaxError that only fired when a lane was blocked, because nothing
    # rendered a blocked receipt.
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        blocked_path = write_receipt(partial, pathlib.Path(scratch))
        reread = read_receipt(blocked_path)
        assert reread["result"] == BLOCKED
        lines = explain(reread)
        assert len(lines) == len(REQUIRED_LANES) - 1, lines
        assert all("NOT_EXERCISED" in line for line in lines)
        assert explain(admitted) == []

    print("admission_receipt selftest: PASS", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="admission_receipt.py",
        description="Build the GT-01 host admission receipt from a lane ledger.",
    )
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--result", type=pathlib.Path, metavar="RECEIPT", help="print a receipt's result")
    parser.add_argument(
        "--explain", type=pathlib.Path, metavar="RECEIPT", help="list a receipt's non-PASS lanes"
    )
    arguments = parser.parse_args(list(argv) if argv is not None else sys.argv[1:])
    if arguments.selftest:
        return _run_selftest()
    if arguments.result is not None:
        print(read_receipt(arguments.result)["result"])
        return 0
    if arguments.explain is not None:
        for line in explain(read_receipt(arguments.explain)):
            print(line)
        return 0

    receipt = build_receipt(**_from_environment())
    path = write_receipt(receipt, pathlib.Path(os.environ["RECEIPT_DIR"]))
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
