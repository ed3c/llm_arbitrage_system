from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.operator_cli import main as phase8_main
from llm_arbitrage_system.experiments.replication import build_replication_report
from llm_arbitrage_system.experiments.replication_inputs import (
    load_replication_inputs,
)
from llm_arbitrage_system.experiments.replication_plan import (
    load_replication_plan,
)
from llm_arbitrage_system.experiments.replication_signing import (
    load_replication_report,
    sign_replication_report,
    verify_replication_attestation,
)

_PHASE9_COMMANDS = frozenset(
    {
        "replication-report",
        "sign-replication-report",
        "validate-replication-inputs",
        "validate-replication-plan",
        "validate-replication-report",
        "verify-replication-report",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-arbitrage",
        description="Offline independent-replication evidence operator.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_plan = subparsers.add_parser("validate-replication-plan")
    validate_plan.add_argument("plan", type=Path)

    validate_inputs = subparsers.add_parser("validate-replication-inputs")
    validate_inputs.add_argument("inputs", type=Path)

    build_report = subparsers.add_parser("replication-report")
    build_report.add_argument("--plan", type=Path, required=True)
    build_report.add_argument("--inputs", type=Path, required=True)
    build_report.add_argument("--output", type=Path, required=True)
    build_report.add_argument("--force", action="store_true")

    validate_report = subparsers.add_parser("validate-replication-report")
    validate_report.add_argument("report", type=Path)

    sign_report = subparsers.add_parser("sign-replication-report")
    sign_report.add_argument("--report", type=Path, required=True)
    sign_report.add_argument("--private-key", type=Path, required=True)
    sign_report.add_argument("--output", type=Path, required=True)
    sign_report.add_argument("--force", action="store_true")

    verify_report = subparsers.add_parser("verify-replication-report")
    verify_report.add_argument("--report", type=Path, required=True)
    verify_report.add_argument("--attestation", type=Path, required=True)
    verify_report.add_argument("--trusted-public-key", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in _PHASE9_COMMANDS:
        return phase8_main(arguments)
    parsed = build_parser().parse_args(arguments)
    try:
        payload = _dispatch(parsed)
    except (OSError, KeyError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


def _dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    command = str(arguments.command)
    if command == "validate-replication-plan":
        return load_replication_plan(arguments.plan).summary()
    if command == "validate-replication-inputs":
        return load_replication_inputs(arguments.inputs).summary()
    if command == "replication-report":
        output = _available_output(arguments.output, force=bool(arguments.force))
        report = build_replication_report(
            plan_path=arguments.plan,
            inputs_path=arguments.inputs,
        )
        write_json(output, report.as_dict())
        return {"output": str(output), **report.as_dict()}
    if command == "validate-replication-report":
        return load_replication_report(arguments.report).summary()
    if command == "sign-replication-report":
        document = sign_replication_report(
            arguments.report,
            arguments.private_key,
            arguments.output,
            force=bool(arguments.force),
        )
        payload = _object(document.get("payload"), "replication signer payload")
        report = _object(payload.get("report"), "replication report identity")
        return {
            "attestation": str(Path(arguments.output).resolve()),
            "report_id": report["report_id"],
            "report_sha256": report["report_sha256"],
            "plan_id": report["plan_id"],
            "candidate_id": report["candidate_id"],
            "status": report["status"],
            "key_id": payload["key_id"],
            "selection": None,
            "promotion": None,
            "human_admit_required": True,
            "automatic_promotion": False,
            "release_authorized": False,
            "deployment_authorized": False,
            "trading_authorized": False,
        }
    if command == "verify-replication-report":
        return verify_replication_attestation(
            arguments.report,
            arguments.attestation,
            trusted_public_key_path=arguments.trusted_public_key,
        ).as_dict()
    raise RuntimeError(f"unsupported Phase 9 command: {command}")


def _available_output(path: Path, *, force: bool) -> Path:
    output = path.resolve()
    if output.exists() and not force:
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} must be an object")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
