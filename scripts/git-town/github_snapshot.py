#!/usr/bin/env python3
"""Trusted GitHub state snapshot and the publication gate (issue #20).

Two typed operations:

``validate``  check a snapshot document against the closed schema
``evaluate``  decide one publication intent from a local receipt + snapshot

The gate is offline. It never calls GitHub: a snapshot is captured out of band
and handed in, so the decision is reproducible and a network hiccup cannot be
mistaken for a policy answer. One `ALLOW` authorizes exactly one operation, and
`publish.sh` records the decision digest so it cannot be spent twice.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))

from task_packet import canonical_bytes

SNAPSHOT_SCHEMA = "llm-arbitrage/github-snapshot/v1"
DECISION_SCHEMA = "llm-arbitrage/publication-decision/v1"

REPOSITORY = "ed3c/llm_arbitrage_system"
PERENNIAL_BRANCHES = frozenset({"main"})

ALLOWED_INTENTS = ("initial-pr", "ready-for-review", "batched-repair")
INTENT_DECISIONS = {
    "initial-pr": "ALLOW_INITIAL_PR",
    "ready-for-review": "ALLOW_READY_FOR_REVIEW",
    "batched-repair": "ALLOW_BATCHED_REPAIR",
}

BLOCKED_POLICY = "BLOCKED_POLICY"
BLOCKED_STALE_EVIDENCE = "BLOCKED_STALE_EVIDENCE"
BLOCKED_BILLING = "BLOCKED_BILLING"
BLOCKED_FEEDBACK = "BLOCKED_FEEDBACK"

_SNAPSHOT_FIELDS = {
    "schema",
    "repository",
    "pull_request_number",
    "base_branch",
    "head_branch",
    "head_sha",
    "draft",
    "feedback_cursor",
    "workflow",
    "billing",
}
_WORKFLOW_FIELDS = {"head_sha", "conclusion", "run_id"}
_BILLING_FIELDS = {"circuit", "reason"}

ACCEPTED_LOCAL_RESULTS = frozenset({"SYNCED", "NO_CHANGE"})


class GateRejected(Exception):
    """One stable blocked decision plus a human-readable reason."""

    def __init__(self, decision: str, reason: str) -> None:
        super().__init__(reason)
        self.decision = decision
        self.reason = reason


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GateRejected(BLOCKED_POLICY, f"{name} must be a mapping")
    return value


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise GateRejected(BLOCKED_POLICY, f"{name} declares unknown fields: {', '.join(unknown)}")


def _require(payload: Mapping[str, Any], name: str, field: str) -> Any:
    if field not in payload:
        raise GateRejected(BLOCKED_POLICY, f"{name}.{field} is missing from the trusted snapshot")
    return payload[field]


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or not all(c in "0123456789abcdef" for c in value):
        raise GateRejected(BLOCKED_POLICY, f"{name} must be a 40-character lowercase hex SHA")
    return value


def validate_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Every guard field must be present. A missing guard is not a soft state."""

    snapshot = _mapping(payload, "snapshot")
    _reject_unknown(snapshot, _SNAPSHOT_FIELDS, "snapshot")
    for field in _SNAPSHOT_FIELDS:
        _require(snapshot, "snapshot", field)

    if snapshot["schema"] != SNAPSHOT_SCHEMA:
        raise GateRejected(BLOCKED_POLICY, f"snapshot schema must be {SNAPSHOT_SCHEMA}")
    if snapshot["repository"] != REPOSITORY:
        raise GateRejected(BLOCKED_POLICY, f"snapshot repository must be {REPOSITORY}")

    head_branch = snapshot["head_branch"]
    if not isinstance(head_branch, str) or not head_branch.strip():
        raise GateRejected(BLOCKED_POLICY, "snapshot head_branch must be a non-empty string")
    if head_branch in PERENNIAL_BRANCHES:
        raise GateRejected(BLOCKED_POLICY, f"a perennial branch cannot be a publication head: {head_branch}")

    base_branch = snapshot["base_branch"]
    if not isinstance(base_branch, str) or not base_branch.strip():
        raise GateRejected(BLOCKED_POLICY, "snapshot base_branch must be a non-empty string")
    if base_branch == head_branch:
        raise GateRejected(BLOCKED_POLICY, "snapshot base_branch cannot equal head_branch")

    _sha(snapshot["head_sha"], "snapshot.head_sha")

    number = snapshot["pull_request_number"]
    if number is not None and (isinstance(number, bool) or not isinstance(number, int) or number <= 0):
        raise GateRejected(BLOCKED_POLICY, "snapshot pull_request_number must be a positive integer or null")
    if not isinstance(snapshot["draft"], bool):
        raise GateRejected(BLOCKED_POLICY, "snapshot draft must be a boolean")
    if not isinstance(snapshot["feedback_cursor"], str) or not snapshot["feedback_cursor"].strip():
        raise GateRejected(BLOCKED_POLICY, "snapshot feedback_cursor must be a non-empty string")

    workflow = _mapping(_require(snapshot, "snapshot", "workflow"), "snapshot.workflow")
    _reject_unknown(workflow, _WORKFLOW_FIELDS, "snapshot.workflow")
    for field in _WORKFLOW_FIELDS:
        _require(workflow, "snapshot.workflow", field)
    _sha(workflow["head_sha"], "snapshot.workflow.head_sha")

    billing = _mapping(_require(snapshot, "snapshot", "billing"), "snapshot.billing")
    _reject_unknown(billing, _BILLING_FIELDS, "snapshot.billing")
    for field in _BILLING_FIELDS:
        _require(billing, "snapshot.billing", field)
    if billing["circuit"] not in {"open", "closed"}:
        raise GateRejected(BLOCKED_POLICY, "snapshot billing circuit must be open or closed")

    return dict(snapshot)


def evaluate_publication(
    *,
    intent: str,
    local_head_sha: str,
    local_receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    processed_feedback_cursors: Sequence[str] = (),
    background: bool = False,
) -> dict[str, Any]:
    """Return one `ALLOW_*` decision, or raise with one stable blocked state."""

    validated = validate_snapshot(snapshot)

    if background:
        # docs/git/REPO_PROFILE.md: background_push, background_pr_ready_transition
        # and background_workflow_rerun are all denied. There is no intent a
        # background worker may request.
        raise GateRejected(
            BLOCKED_POLICY, "background operation may prepare a proposal but never request an intent"
        )
    if intent not in ALLOWED_INTENTS:
        raise GateRejected(BLOCKED_POLICY, f"publication intent must be one of {list(ALLOWED_INTENTS)}")

    local_head = _sha(local_head_sha, "local head")

    receipt = _mapping(local_receipt, "local receipt")
    if receipt.get("result") not in ACCEPTED_LOCAL_RESULTS:
        raise GateRejected(
            BLOCKED_POLICY, f"local receipt result {receipt.get('result')} does not authorize publication"
        )
    if receipt.get("after_subject") != local_head:
        raise GateRejected(
            BLOCKED_STALE_EVIDENCE,
            "the local receipt describes a different head than the working repository",
        )
    if receipt.get("head_branch") != validated["head_branch"]:
        raise GateRejected(BLOCKED_POLICY, "the local receipt and the snapshot describe different branches")

    if validated["head_sha"] != local_head:
        raise GateRejected(
            BLOCKED_STALE_EVIDENCE, "the trusted snapshot was taken at a different head than the local one"
        )
    if validated["workflow"]["head_sha"] != local_head:
        raise GateRejected(
            BLOCKED_STALE_EVIDENCE, "the observed workflow ran against an older subject than the local head"
        )

    if validated["billing"]["circuit"] == "open":
        raise GateRejected(
            BLOCKED_BILLING, f"the billing circuit is open: {validated['billing']['reason']}"
        )
    if validated["feedback_cursor"] in set(processed_feedback_cursors):
        raise GateRejected(
            BLOCKED_FEEDBACK, "this feedback cursor was already answered; repeating it is not a new operation"
        )

    _check_intent_preconditions(intent, validated)

    decision = {
        "schema": DECISION_SCHEMA,
        "decision": INTENT_DECISIONS[intent],
        "intent": intent,
        "repository": REPOSITORY,
        "head_branch": validated["head_branch"],
        "base_branch": validated["base_branch"],
        "head_sha": local_head,
        "pull_request_number": validated["pull_request_number"],
        "feedback_cursor": validated["feedback_cursor"],
        "workflow_run_id": validated["workflow"]["run_id"],
        "authorizes_operations": 1,
        "requires_human_admit_for": [
            "merge",
            "permission change",
            "billing recovery",
            "release promotion",
            "production deployment",
        ],
    }
    decision["decision_sha256"] = _digest(decision)
    return decision


def _check_intent_preconditions(intent: str, snapshot: Mapping[str, Any]) -> None:
    number = snapshot["pull_request_number"]
    if intent == "initial-pr":
        if number is not None:
            raise GateRejected(BLOCKED_POLICY, f"pull request #{number} already exists for this head")
        return
    if number is None:
        raise GateRejected(BLOCKED_POLICY, f"{intent} requires an existing pull request")
    if intent == "ready-for-review":
        if not snapshot["draft"]:
            raise GateRejected(BLOCKED_POLICY, f"pull request #{number} is already out of draft")
        if snapshot["workflow"]["conclusion"] != "success":
            raise GateRejected(
                BLOCKED_POLICY,
                f"the trusted check concluded {snapshot['workflow']['conclusion']}, not success",
            )


def _digest(payload: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _blocked_decision(decision: str) -> dict[str, Any]:
    return {
        "schema": DECISION_SCHEMA,
        "decision": decision,
        "intent": None,
        "repository": REPOSITORY,
        "head_branch": None,
        "base_branch": None,
        "head_sha": None,
        "pull_request_number": None,
        "feedback_cursor": None,
        "workflow_run_id": None,
        "authorizes_operations": 0,
        "requires_human_admit_for": [],
        "decision_sha256": None,
    }


# --- entrypoint ----------------------------------------------------------


def _read_json(path: Path, label: str) -> Mapping[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GateRejected(BLOCKED_POLICY, f"{label} is unreadable: {error}") from error
    return _mapping(loaded, label)


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="github_snapshot.py", description="Trusted GitHub snapshot validation and publication gate."
    )
    parser.add_argument("operation", nargs="?", choices=("validate", "evaluate"))
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--receipt", type=Path, help="local sync receipt from receipt.py append")
    parser.add_argument("--local-head-sha")
    parser.add_argument("--intent", choices=ALLOWED_INTENTS)
    parser.add_argument("--processed-feedback", action="append", default=[])
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    return parser.parse_args(list(argv))


def _require_option(value: Any, name: str) -> Any:
    if value is None:
        raise GateRejected(BLOCKED_POLICY, f"{name} is required for this operation")
    return value


def _example_snapshot(**overrides: Any) -> dict[str, Any]:
    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "repository": REPOSITORY,
        "pull_request_number": None,
        "base_branch": "main",
        "head_branch": "tooling/git-town-publication-gate",
        "head_sha": "a" * 40,
        "draft": True,
        "feedback_cursor": "review-comment-1",
        "workflow": {"head_sha": "a" * 40, "conclusion": "success", "run_id": 1},
        "billing": {"circuit": "closed", "reason": "within budget"},
    }
    snapshot.update(overrides)
    return snapshot


def _example_receipt(**overrides: Any) -> dict[str, Any]:
    receipt = {
        "head_branch": "tooling/git-town-publication-gate",
        "after_subject": "a" * 40,
        "result": "SYNCED",
    }
    receipt.update(overrides)
    return receipt


def _run_selftest() -> int:
    allowed = evaluate_publication(
        intent="initial-pr",
        local_head_sha="a" * 40,
        local_receipt=_example_receipt(),
        snapshot=_example_snapshot(),
    )
    assert allowed["decision"] == "ALLOW_INITIAL_PR"
    assert allowed["authorizes_operations"] == 1
    assert len(allowed["decision_sha256"]) == 64

    for kwargs, expected in (
        ({"background": True}, BLOCKED_POLICY),
        ({"intent": "ship"}, BLOCKED_POLICY),
        ({"local_receipt": _example_receipt(after_subject="b" * 40)}, BLOCKED_STALE_EVIDENCE),
        (
            {
                "snapshot": _example_snapshot(
                    workflow={"head_sha": "b" * 40, "conclusion": "success", "run_id": 2}
                )
            },
            BLOCKED_STALE_EVIDENCE,
        ),
        (
            {"snapshot": _example_snapshot(billing={"circuit": "open", "reason": "quota"})},
            BLOCKED_BILLING,
        ),
        ({"processed_feedback_cursors": ["review-comment-1"]}, BLOCKED_FEEDBACK),
        ({"snapshot": _example_snapshot(pull_request_number=7)}, BLOCKED_POLICY),
    ):
        call = {
            "intent": "initial-pr",
            "local_head_sha": "a" * 40,
            "local_receipt": _example_receipt(),
            "snapshot": _example_snapshot(),
            **kwargs,
        }
        try:
            evaluate_publication(**call)
        except GateRejected as rejected:
            assert rejected.decision == expected, (rejected.decision, expected)
        else:  # pragma: no cover - a silent pass here is the defect being guarded
            raise AssertionError(f"{kwargs} should have been refused with {expected}")

    incomplete = _example_snapshot()
    del incomplete["billing"]
    try:
        validate_snapshot(incomplete)
    except GateRejected as rejected:
        assert rejected.decision == BLOCKED_POLICY
    else:  # pragma: no cover
        raise AssertionError("a missing guard must block")

    print("github_snapshot selftest: PASS", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.selftest:
        return _run_selftest()
    if arguments.operation is None:
        print("an operation is required unless --selftest is requested", file=sys.stderr)
        return 2
    try:
        snapshot = _read_json(Path(_require_option(arguments.snapshot, "--snapshot")), "snapshot")
        if arguments.operation == "validate":
            payload: dict[str, Any] = {**validate_snapshot(snapshot), "result": "PASS"}
        else:
            payload = evaluate_publication(
                intent=_require_option(arguments.intent, "--intent"),
                local_head_sha=_require_option(arguments.local_head_sha, "--local-head-sha"),
                local_receipt=_read_json(
                    Path(_require_option(arguments.receipt, "--receipt")), "local receipt"
                ),
                snapshot=snapshot,
                processed_feedback_cursors=arguments.processed_feedback,
                background=arguments.background,
            )
    except GateRejected as rejected:
        print(rejected.reason, file=sys.stderr)
        sys.stdout.write(canonical_bytes(_blocked_decision(rejected.decision)).decode() + "\n")
        return 1
    sys.stdout.write(canonical_bytes(payload).decode() + "\n")
    return 0


def _entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
