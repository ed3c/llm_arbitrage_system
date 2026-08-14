#!/usr/bin/env python3
"""Typed task-packet validator for the Git Town Worker (issue #16).

This is a fixed entrypoint, not a command runner. It reads one task packet,
applies the validation laws in ``docs/git/TASK_PACKET.md``, and emits the
canonical receipt from that document on stdout. Diagnosis goes to stderr so
stdout stays byte-stable for digesting.

Exit status is 0 only for ``PASS``; every rejection maps to one stable result
in the vocabulary shared with ``docs/git/WORKER_PROTOCOL.md``.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import yaml

PACKET_SCHEMA = "llm-arbitrage/task-packet/v1"
RECEIPT_SCHEMA = "llm-arbitrage/task-packet-receipt/v1"
LEASE_SCHEMA = "llm-arbitrage/path-lease/v1"

REPOSITORY = "ed3c/llm_arbitrage_system"
REQUIRED_TOOL_PROFILE = "docs/git/REPO_PROFILE.md"
PERENNIAL_BRANCHES = frozenset({"main"})
STACK_CLASSES = frozenset({"foundation", "child", "sibling", "convergence"})
PUBLICATION_INTENTS = frozenset({"none", "initial-pr", "ready-for-review", "batched-repair"})

MAX_TIMEOUT_SECONDS = 3600
MAX_BACKGROUND_ITERATIONS = 100
MAX_LEASE_TTL_SECONDS = 86400

RESULT_PASS = "PASS"
RESULT_TASK_PACKET = "BLOCKED_TASK_PACKET"
RESULT_ANCESTRY = "BLOCKED_ANCESTRY"
RESULT_BRANCH_LEASE = "BLOCKED_BRANCH_LEASE"
RESULT_POLICY = "BLOCKED_POLICY"
RESULT_TOOL_ADMISSION = "BLOCKED_TOOL_ADMISSION"

# Excluded even when a packet omits them: repository policy, the Git directory
# itself, and conventional secret locations.
POLICY_EXCLUDED = (
    ".git/**",
    ".git-town.toml",
    ".env",
    ".env.*",
    "secrets/**",
    "**/*.pem",
    "**/*.key",
)

_CREDENTIAL_URL = re.compile(r"[a-z][a-z0-9+.-]*://[^/\s@]*:[^/\s@]*@", re.IGNORECASE)
_BRANCH_NAME = re.compile(r"\A[A-Za-z0-9](?:[A-Za-z0-9._/-]*[A-Za-z0-9])?\Z")

_SECTIONS = {
    "identity": {
        "issue_number",
        "parent_issue_number",
        "title",
        "repository",
        "requested_by",
    },
    "objective": {"goal", "non_goals", "evidence_boundary"},
    "stack": {
        "base_branch",
        "parent_branch",
        "head_branch",
        "stack_class",
        "dependencies",
        "parallel_safe_siblings",
    },
    "leases": {
        "branch_lease",
        "worktree_selector",
        "allowed_paths",
        "excluded_paths",
        "lease_ttl_seconds",
        "renewal_policy",
    },
    "execution": {
        "required_tool_profile",
        "exact_tool_admission_required",
        "dry_run_first",
        "non_interactive",
        "automatic_conflict_resolution",
        "push_allowed",
        "timeout_seconds",
        "max_background_iterations",
    },
    "evals": {"positive", "negative_or_mutation", "exact_subject_binding"},
    "publication": {
        "requested_intent",
        "expected_pr_number",
        "expected_pr_base",
        "expected_pr_head",
        "draft_required",
        "trusted_snapshot_required",
    },
    "cleanup": {"contract", "safe_to_remove_on_success", "preserve_on_block"},
    "rollback": {"subject", "drift_policy", "unattended_undo_or_force"},
}
_TOP_LEVEL = {"schema", *_SECTIONS, "human_owned_operations"}


class PacketRejected(Exception):
    """One stable rejection result plus a human-readable reason."""

    def __init__(self, result: str, reason: str) -> None:
        super().__init__(reason)
        self.result = result
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ValidatedPacket:
    """The subset of an admitted packet the receipt and lease manifest bind to."""

    canonical: dict[str, Any]
    issue_number: int
    head_branch: str
    parent_branch: str
    allowed_paths: tuple[str, ...]
    excluded_paths: tuple[str, ...]
    lease_ttl_seconds: int
    dependencies: tuple[int, ...]


# --- typed field readers -------------------------------------------------


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PacketRejected(RESULT_TASK_PACKET, f"{name} must be a mapping")
    for key in value:
        if not isinstance(key, str):
            raise PacketRejected(RESULT_TASK_PACKET, f"{name} keys must be strings")
    return value


def _section(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    if name not in payload:
        raise PacketRejected(RESULT_TASK_PACKET, f"{name} section is missing")
    section = _mapping(payload[name], name)
    _reject_unknown(section, _SECTIONS[name], name)
    for field in _SECTIONS[name]:
        if field not in section:
            raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} is missing")
    return section


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        # An undeclared field is how a generic shell command would enter a
        # packet that is supposed to select typed entrypoints only.
        raise PacketRejected(
            RESULT_POLICY,
            f"{name} declares fields outside the typed schema: {', '.join(unknown)}",
        )


def _require(section: Mapping[str, Any], name: str, field: str) -> Any:
    """Single missing-field exit, so no reader can raise a bare ``KeyError``."""

    if field not in section:
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} is missing")
    return section[field]


def _text(section: Mapping[str, Any], name: str, field: str) -> str:
    value = _require(section, name, field)
    if not isinstance(value, str) or not value.strip():
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} must be a non-empty string")
    return value


def _flag(section: Mapping[str, Any], name: str, field: str, expected: bool, result: str) -> bool:
    value = _require(section, name, field)
    if not isinstance(value, bool):
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} must be a boolean")
    if value is not expected:
        raise PacketRejected(
            result, f"{name}.{field} must remain {str(expected).lower()} under repository policy"
        )
    return value


def _bounded_integer(section: Mapping[str, Any], name: str, field: str, maximum: int) -> int:
    value = _require(section, name, field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} must be an integer")
    if not 1 <= value <= maximum:
        raise PacketRejected(
            RESULT_POLICY, f"{name}.{field} must be a positive integer bounded by {maximum}"
        )
    return value


def _text_list(section: Mapping[str, Any], name: str, field: str, minimum: int) -> tuple[str, ...]:
    value = _require(section, name, field)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} must be a list")
    entries: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PacketRejected(
                RESULT_TASK_PACKET, f"{name}.{field} entries must be non-empty strings"
            )
        entries.append(item)
    if len(entries) < minimum:
        raise PacketRejected(
            RESULT_TASK_PACKET, f"{name}.{field} requires at least {minimum} entry"
        )
    if len(set(entries)) != len(entries):
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} contains duplicate entries")
    return tuple(entries)


def _issue_list(section: Mapping[str, Any], name: str, field: str) -> tuple[int, ...]:
    value = _require(section, name, field)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} must be a list")
    numbers: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise PacketRejected(
                RESULT_TASK_PACKET, f"{name}.{field} entries must be positive issue numbers"
            )
        numbers.append(item)
    if len(set(numbers)) != len(numbers):
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} contains duplicate issue numbers")
    return tuple(numbers)


def _issue_number(section: Mapping[str, Any], name: str, field: str, *, optional: bool) -> int | None:
    value = _require(section, name, field)
    if value is None:
        if optional:
            return None
        raise PacketRejected(RESULT_TASK_PACKET, f"{name}.{field} is required")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PacketRejected(
            RESULT_TASK_PACKET, f"{name}.{field} must be a positive issue number"
        )
    return value


def _branch(section: Mapping[str, Any], name: str, field: str) -> str:
    value = _text(section, name, field)
    if not _BRANCH_NAME.match(value):
        raise PacketRejected(RESULT_ANCESTRY, f"{name}.{field} is not a valid branch name: {value}")
    return value


# --- lease geometry ------------------------------------------------------


def _covers(pattern: str, path: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        return path == prefix or path.startswith(f"{prefix}/")
    return fnmatch.fnmatchcase(path, pattern)


def _leases_overlap(left: str, right: str) -> bool:
    return left == right or _covers(left, right) or _covers(right, left)


def _validate_lease_path(path: str) -> None:
    if path.startswith(("/", "~")) or re.match(r"\A[A-Za-z]:[\\/]", path):
        raise PacketRejected(
            RESULT_POLICY, f"lease path must be repository-relative, not a host path: {path}"
        )
    if "\\" in path:
        raise PacketRejected(RESULT_POLICY, f"lease path must use POSIX separators: {path}")
    if any(segment in {"..", "."} for segment in path.split("/")):
        raise PacketRejected(RESULT_POLICY, f"lease path must be normalized: {path}")
    for excluded in POLICY_EXCLUDED:
        if _leases_overlap(excluded, path):
            raise PacketRejected(
                RESULT_POLICY, f"lease path {path} intersects the always-excluded pattern {excluded}"
            )


# --- secret scanning -----------------------------------------------------


def _reject_secret_material(node: Any, trail: str = "packet") -> None:
    if isinstance(node, Mapping):
        for key, value in node.items():
            _reject_secret_material(value, f"{trail}.{key}")
        return
    if isinstance(node, Sequence) and not isinstance(node, str | bytes):
        for index, value in enumerate(node):
            _reject_secret_material(value, f"{trail}[{index}]")
        return
    if isinstance(node, str) and _CREDENTIAL_URL.search(node):
        raise PacketRejected(RESULT_POLICY, f"{trail} contains a credential-bearing URL")


# --- validation ----------------------------------------------------------


def validate_packet(
    payload: Mapping[str, Any],
    *,
    repository_root: Path,
    sibling_leases: Sequence[Mapping[str, Any]] = (),
) -> ValidatedPacket:
    """Apply every law in ``docs/git/TASK_PACKET.md`` or raise ``PacketRejected``."""

    packet = _mapping(payload, "packet")
    _reject_unknown(packet, _TOP_LEVEL, "packet")
    _reject_secret_material(packet)

    if packet.get("schema") != PACKET_SCHEMA:
        raise PacketRejected(RESULT_TASK_PACKET, f"schema must be {PACKET_SCHEMA}")

    identity = _section(packet, "identity")
    objective = _section(packet, "objective")
    stack = _section(packet, "stack")
    leases = _section(packet, "leases")
    execution = _section(packet, "execution")
    evals = _section(packet, "evals")
    publication = _section(packet, "publication")
    cleanup = _section(packet, "cleanup")
    rollback = _section(packet, "rollback")

    human_owned = _text_list(packet, "packet", "human_owned_operations", 1)

    # Identity and graph.
    if _text(identity, "identity", "repository") != REPOSITORY:
        raise PacketRejected(RESULT_POLICY, f"identity.repository must be {REPOSITORY}")
    issue_number = _issue_number(identity, "identity", "issue_number", optional=False)
    assert issue_number is not None  # narrowed by optional=False
    parent_issue = _issue_number(identity, "identity", "parent_issue_number", optional=True)
    if parent_issue == issue_number:
        raise PacketRejected(RESULT_ANCESTRY, "identity.parent_issue_number cannot be the issue itself")
    _text(identity, "identity", "title")
    _text(identity, "identity", "requested_by")

    _text(objective, "objective", "goal")
    _text(objective, "objective", "evidence_boundary")
    _text_list(objective, "objective", "non_goals", 1)

    base_branch = _branch(stack, "stack", "base_branch")
    parent_branch = _branch(stack, "stack", "parent_branch")
    head_branch = _branch(stack, "stack", "head_branch")
    stack_class = _text(stack, "stack", "stack_class")
    if stack_class not in STACK_CLASSES:
        raise PacketRejected(
            RESULT_TASK_PACKET, f"stack.stack_class must be one of {sorted(STACK_CLASSES)}"
        )
    dependencies = _issue_list(stack, "stack", "dependencies")
    siblings = _issue_list(stack, "stack", "parallel_safe_siblings")
    if issue_number in dependencies:
        raise PacketRejected(RESULT_ANCESTRY, "stack.dependencies cannot contain the issue itself")

    if head_branch in PERENNIAL_BRANCHES:
        raise PacketRejected(RESULT_POLICY, f"stack.head_branch cannot be a perennial branch: {head_branch}")
    if head_branch in {base_branch, parent_branch}:
        raise PacketRejected(RESULT_ANCESTRY, "stack.head_branch must differ from its base and parent")
    if stack_class == "foundation" and parent_branch not in PERENNIAL_BRANCHES:
        raise PacketRejected(
            RESULT_ANCESTRY, "a foundation packet must parent onto a perennial branch"
        )
    if stack_class != "foundation" and parent_branch in PERENNIAL_BRANCHES:
        raise PacketRejected(
            RESULT_ANCESTRY, f"a {stack_class} packet cannot parent directly onto a perennial branch"
        )
    if stack_class == "convergence" and not dependencies:
        raise PacketRejected(
            RESULT_ANCESTRY, "a convergence packet must declare every integrated leaf dependency"
        )
    if stack_class == "sibling" and not siblings:
        raise PacketRejected(
            RESULT_ANCESTRY, "a sibling packet must declare its parallel-safe siblings"
        )

    # Path leases.
    if _text(leases, "leases", "branch_lease") != head_branch:
        raise PacketRejected(RESULT_BRANCH_LEASE, "leases.branch_lease must equal the head branch")
    _text(leases, "leases", "worktree_selector")
    _text(leases, "leases", "renewal_policy")
    allowed_paths = _text_list(leases, "leases", "allowed_paths", 1)
    excluded_paths = _text_list(leases, "leases", "excluded_paths", 0)
    lease_ttl = _bounded_integer(leases, "leases", "lease_ttl_seconds", MAX_LEASE_TTL_SECONDS)
    for path in (*allowed_paths, *excluded_paths):
        _validate_lease_path(path)
    _reject_sibling_overlap(head_branch, allowed_paths, sibling_leases)

    # Execution.
    if _text(execution, "execution", "required_tool_profile") != REQUIRED_TOOL_PROFILE:
        raise PacketRejected(
            RESULT_TOOL_ADMISSION, f"execution.required_tool_profile must be {REQUIRED_TOOL_PROFILE}"
        )
    if not (repository_root / REQUIRED_TOOL_PROFILE).is_file():
        raise PacketRejected(
            RESULT_TOOL_ADMISSION, f"{REQUIRED_TOOL_PROFILE} is absent from the repository"
        )
    _flag(execution, "execution", "exact_tool_admission_required", True, RESULT_TOOL_ADMISSION)
    _flag(execution, "execution", "dry_run_first", True, RESULT_POLICY)
    _flag(execution, "execution", "non_interactive", True, RESULT_POLICY)
    _flag(execution, "execution", "automatic_conflict_resolution", False, RESULT_POLICY)
    _flag(execution, "execution", "push_allowed", False, RESULT_POLICY)
    _bounded_integer(execution, "execution", "timeout_seconds", MAX_TIMEOUT_SECONDS)
    _bounded_integer(execution, "execution", "max_background_iterations", MAX_BACKGROUND_ITERATIONS)

    # Evals and controls.
    _text_list(evals, "evals", "positive", 1)
    _text_list(evals, "evals", "negative_or_mutation", 1)
    _flag(evals, "evals", "exact_subject_binding", True, RESULT_POLICY)

    _validate_publication(publication, head_branch)

    _text(cleanup, "cleanup", "contract")
    _text_list(cleanup, "cleanup", "safe_to_remove_on_success", 0)
    _text_list(cleanup, "cleanup", "preserve_on_block", 0)

    _text(rollback, "rollback", "subject")
    if _text(rollback, "rollback", "drift_policy") != "refuse":
        raise PacketRejected(RESULT_POLICY, "rollback.drift_policy must be refuse")
    _flag(rollback, "rollback", "unattended_undo_or_force", False, RESULT_POLICY)

    canonical = {
        "schema": PACKET_SCHEMA,
        "identity": {
            "issue_number": issue_number,
            "parent_issue_number": parent_issue,
            "title": identity["title"],
            "repository": REPOSITORY,
            "requested_by": identity["requested_by"],
        },
        "objective": {
            "goal": objective["goal"],
            "non_goals": list(objective["non_goals"]),
            "evidence_boundary": objective["evidence_boundary"],
        },
        "stack": {
            "base_branch": base_branch,
            "parent_branch": parent_branch,
            "head_branch": head_branch,
            "stack_class": stack_class,
            "dependencies": sorted(dependencies),
            "parallel_safe_siblings": sorted(siblings),
        },
        "leases": {
            "branch_lease": head_branch,
            "worktree_selector": leases["worktree_selector"],
            "allowed_paths": sorted(allowed_paths),
            "excluded_paths": sorted(excluded_paths),
            "lease_ttl_seconds": lease_ttl,
            "renewal_policy": leases["renewal_policy"],
        },
        "execution": dict(sorted(execution.items())),
        "evals": {
            "positive": list(evals["positive"]),
            "negative_or_mutation": list(evals["negative_or_mutation"]),
            "exact_subject_binding": True,
        },
        "publication": dict(sorted(publication.items())),
        "cleanup": dict(sorted(cleanup.items())),
        "rollback": dict(sorted(rollback.items())),
        "human_owned_operations": sorted(human_owned),
    }

    return ValidatedPacket(
        canonical=canonical,
        issue_number=issue_number,
        head_branch=head_branch,
        parent_branch=parent_branch,
        allowed_paths=tuple(sorted(allowed_paths)),
        excluded_paths=tuple(sorted(excluded_paths)),
        lease_ttl_seconds=lease_ttl,
        dependencies=tuple(sorted(dependencies)),
    )


def _validate_publication(publication: Mapping[str, Any], head_branch: str) -> None:
    intent = _text(publication, "publication", "requested_intent")
    if intent not in PUBLICATION_INTENTS:
        raise PacketRejected(
            RESULT_POLICY, f"publication.requested_intent must be one of {sorted(PUBLICATION_INTENTS)}"
        )
    if not isinstance(publication["draft_required"], bool):
        raise PacketRejected(RESULT_TASK_PACKET, "publication.draft_required must be a boolean")
    _flag(publication, "publication", "trusted_snapshot_required", True, RESULT_POLICY)

    number = publication["expected_pr_number"]
    base = publication["expected_pr_base"]
    head = publication["expected_pr_head"]
    if intent == "none":
        if not (number is None and base is None and head is None):
            raise PacketRejected(
                RESULT_POLICY, "publication.expected_pr_* must be null when no intent is requested"
            )
        return
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise PacketRejected(
            RESULT_TASK_PACKET, "publication.expected_pr_number is required for a publication intent"
        )
    if not isinstance(base, str) or not base.strip():
        raise PacketRejected(
            RESULT_TASK_PACKET, "publication.expected_pr_base is required for a publication intent"
        )
    if head != head_branch:
        raise PacketRejected(
            RESULT_ANCESTRY, "publication.expected_pr_head must equal the packet head branch"
        )


def _reject_sibling_overlap(
    head_branch: str,
    allowed_paths: Sequence[str],
    sibling_leases: Sequence[Mapping[str, Any]],
) -> None:
    for lease in sibling_leases:
        sibling_branch = lease.get("head_branch")
        if sibling_branch == head_branch:
            raise PacketRejected(
                RESULT_BRANCH_LEASE, f"branch lease {head_branch} is already held by a live worker"
            )
        sibling_paths = lease.get("allowed_paths")
        if not isinstance(sibling_paths, Sequence) or isinstance(sibling_paths, str):
            raise PacketRejected(
                RESULT_BRANCH_LEASE, "sibling lease manifest is missing an allowed_paths list"
            )
        for mine in allowed_paths:
            for theirs in sibling_paths:
                if isinstance(theirs, str) and _leases_overlap(mine, theirs):
                    raise PacketRejected(
                        RESULT_BRANCH_LEASE,
                        f"allowed path {mine} overlaps live lease {theirs} on {sibling_branch}",
                    )


# --- canonical output ----------------------------------------------------


def canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _digest(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def build_receipt(packet: ValidatedPacket, result: str) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "packet_sha256": _digest(packet.canonical),
        "repository": REPOSITORY,
        "issue_number": packet.issue_number,
        "head_branch": packet.head_branch,
        "parent_branch": packet.parent_branch,
        "allowed_paths_sha256": _digest(list(packet.allowed_paths)),
        "dependencies_sha256": _digest(list(packet.dependencies)),
        "result": result,
    }


def _rejected_receipt(result: str) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "packet_sha256": None,
        "repository": REPOSITORY,
        "issue_number": None,
        "head_branch": None,
        "parent_branch": None,
        "allowed_paths_sha256": None,
        "dependencies_sha256": None,
        "result": result,
    }


def build_lease_manifest(packet: ValidatedPacket) -> dict[str, Any]:
    return {
        "schema": LEASE_SCHEMA,
        "head_branch": packet.head_branch,
        "issue_number": packet.issue_number,
        "allowed_paths": list(packet.allowed_paths),
        "excluded_paths": list(packet.excluded_paths),
        "lease_ttl_seconds": packet.lease_ttl_seconds,
        "allowed_paths_sha256": _digest(list(packet.allowed_paths)),
    }


def load_yaml_mapping(path: Path, label: str) -> Mapping[str, Any]:
    if not path.is_file():
        raise PacketRejected(RESULT_TASK_PACKET, f"{label} is absent: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise PacketRejected(RESULT_TASK_PACKET, f"{label} is not parseable YAML: {error}") from error
    if loaded is None:
        raise PacketRejected(RESULT_TASK_PACKET, f"{label} is empty: {path}")
    return _mapping(loaded, label)


# --- entrypoint ----------------------------------------------------------


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="task_packet.py",
        description="Validate one Git Town task packet against docs/git/TASK_PACKET.md.",
    )
    parser.add_argument("--packet", type=Path, help="task packet YAML to validate")
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root used to resolve the required tool profile",
    )
    parser.add_argument(
        "--sibling-lease",
        type=Path,
        action="append",
        default=[],
        help="live sibling path-lease manifest (repeatable)",
    )
    parser.add_argument("--emit-canonical", type=Path, help="write the canonical packet JSON here")
    parser.add_argument("--emit-lease", type=Path, help="write this packet's path-lease manifest here")
    parser.add_argument(
        "--selftest", action="store_true", help="run the built-in contract checks and exit"
    )
    return parser.parse_args(list(argv))


def _run_selftest() -> int:
    root = Path(__file__).resolve().parents[2]
    packet = validate_packet(example_packet(), repository_root=root)
    receipt = build_receipt(packet, RESULT_PASS)
    assert receipt["result"] == RESULT_PASS
    assert len(receipt["packet_sha256"]) == 64
    # The digest must not depend on how the source YAML happened to be ordered.
    shuffled = dict(reversed(list(example_packet().items())))
    assert build_receipt(validate_packet(shuffled, repository_root=root), RESULT_PASS) == receipt

    for mutate, expected in (
        (lambda p: p["execution"].__setitem__("push_allowed", True), RESULT_POLICY),
        (lambda p: p["stack"].__setitem__("parent_branch", "main"), RESULT_ANCESTRY),
        (lambda p: p["leases"].__setitem__("branch_lease", "other"), RESULT_BRANCH_LEASE),
        (lambda p: p["identity"].pop("title"), RESULT_TASK_PACKET),
        (lambda p: p.__setitem__("command", "rm -rf /"), RESULT_POLICY),
    ):
        candidate = example_packet()
        mutate(candidate)
        try:
            validate_packet(candidate, repository_root=root)
        except PacketRejected as rejected:
            assert rejected.result == expected, (rejected.result, expected)
        else:  # pragma: no cover - a silent pass here is the defect being guarded
            raise AssertionError(f"mutation expected {expected} but validated")

    print("task_packet selftest: PASS", file=sys.stderr)
    return 0


def example_packet() -> dict[str, Any]:
    """The packet this validator's own issue would submit.

    Used by ``--selftest`` and by the test module as the admitted baseline that
    every mutation control is derived from.
    """

    return {
        "schema": PACKET_SCHEMA,
        "identity": {
            "issue_number": 16,
            "parent_issue_number": 11,
            "title": "GT-02: task-packet and path-lease validator",
            "repository": REPOSITORY,
            "requested_by": "repository-owner",
        },
        "objective": {
            "goal": "refuse branch work until a complete typed task packet exists",
            "non_goals": ["no runtime or strategy change", "no publication or merge authority"],
            "evidence_boundary": "mechanism selftest only; live Worker lanes stay NOT_EXERCISED",
        },
        "stack": {
            "base_branch": "docs/readme-state-flow-index",
            "parent_branch": "docs/readme-state-flow-index",
            "head_branch": "tooling/git-town-task-packet-validator",
            "stack_class": "child",
            "dependencies": [15],
            "parallel_safe_siblings": [],
        },
        "leases": {
            "branch_lease": "tooling/git-town-task-packet-validator",
            "worktree_selector": "host_llm_arbitrage_worktrees",
            "allowed_paths": [
                "docs/git/TASK_PACKET.md",
                "docs/harness/git-town-task-packet.md",
                "scripts/git-town/task_packet.py",
                "tests/git-town/test_task_packet.py",
            ],
            "excluded_paths": ["src/**", ".github/**"],
            "lease_ttl_seconds": 3600,
            "renewal_policy": "renew once per bounded execution window under human review",
        },
        "execution": {
            "required_tool_profile": REQUIRED_TOOL_PROFILE,
            "exact_tool_admission_required": True,
            "dry_run_first": True,
            "non_interactive": True,
            "automatic_conflict_resolution": False,
            "push_allowed": False,
            "timeout_seconds": 900,
            "max_background_iterations": 3,
        },
        "evals": {
            "positive": ["complete packet validates to PASS with a stable digest"],
            "negative_or_mutation": [
                "each required field removed individually yields BLOCKED_TASK_PACKET",
                "an overlapping sibling path yields BLOCKED_BRANCH_LEASE",
            ],
            "exact_subject_binding": True,
        },
        "publication": {
            "requested_intent": "none",
            "expected_pr_number": None,
            "expected_pr_base": None,
            "expected_pr_head": None,
            "draft_required": True,
            "trusted_snapshot_required": True,
        },
        "cleanup": {
            "contract": "temporary packets and lease manifests are removed after a PASS",
            "safe_to_remove_on_success": ["temporary packet files", "temporary lease manifests"],
            "preserve_on_block": ["the rejected packet and its stderr diagnosis"],
        },
        "rollback": {
            "subject": "docs/readme-state-flow-index at the recorded base SHA",
            "drift_policy": "refuse",
            "unattended_undo_or_force": False,
        },
        "human_owned_operations": [
            "legal acceptance",
            "merge or merge-queue admission",
            "permission, billing or secret changes",
            "release and production promotion",
            "semantic conflict resolution",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.selftest:
        return _run_selftest()
    if arguments.packet is None:
        print("--packet is required unless --selftest is requested", file=sys.stderr)
        return 2

    try:
        payload = load_yaml_mapping(arguments.packet, "task packet")
        siblings = [
            load_yaml_mapping(path, "sibling lease manifest") for path in arguments.sibling_lease
        ]
        packet = validate_packet(
            payload,
            repository_root=arguments.repository_root,
            sibling_leases=siblings,
        )
    except PacketRejected as rejected:
        print(rejected.reason, file=sys.stderr)
        sys.stdout.write(canonical_bytes(_rejected_receipt(rejected.result)).decode() + "\n")
        return 1

    if arguments.emit_canonical is not None:
        arguments.emit_canonical.write_bytes(canonical_bytes(packet.canonical) + b"\n")
    if arguments.emit_lease is not None:
        arguments.emit_lease.write_bytes(canonical_bytes(build_lease_manifest(packet)) + b"\n")
    sys.stdout.write(canonical_bytes(build_receipt(packet, RESULT_PASS)).decode() + "\n")
    return 0


def _entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
