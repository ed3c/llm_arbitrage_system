from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.cli import main as legacy_main
from llm_arbitrage_system.experiments.decision_request import load_decision_request
from llm_arbitrage_system.experiments.decision_request_signing import (
    sign_decision_request,
    verify_decision_request_attestation,
)
from llm_arbitrage_system.experiments.review_evidence import (
    load_review_record,
    sign_review_record,
    verify_review_record_attestation,
)
from llm_arbitrage_system.experiments.review_quorum import (
    build_review_quorum,
    load_review_quorum_envelope,
    load_review_quorum_inputs,
)
from llm_arbitrage_system.experiments.review_quorum_signing import (
    sign_review_quorum_envelope,
    verify_review_quorum_attestation,
)

_PHASE8_COMMANDS = frozenset(
    {
        "build-review-quorum",
        "sign-decision-request",
        "sign-review-quorum",
        "sign-review-record",
        "validate-decision-request",
        "validate-review-quorum",
        "validate-review-quorum-inputs",
        "validate-review-record",
        "verify-decision-request",
        "verify-review-quorum",
        "verify-review-record",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-arbitrage",
        description="Offline research evidence and separation-of-duties operator.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_request = subparsers.add_parser("validate-decision-request")
    validate_request.add_argument("request", type=Path)

    sign_request = subparsers.add_parser("sign-decision-request")
    sign_request.add_argument("--request", type=Path, required=True)
    sign_request.add_argument("--private-key", type=Path, required=True)
    sign_request.add_argument("--output", type=Path, required=True)
    sign_request.add_argument("--force", action="store_true")

    verify_request = subparsers.add_parser("verify-decision-request")
    verify_request.add_argument("--request", type=Path, required=True)
    verify_request.add_argument("--attestation", type=Path, required=True)
    verify_request.add_argument("--trusted-public-key", type=Path, required=True)

    validate_review = subparsers.add_parser("validate-review-record")
    validate_review.add_argument("record", type=Path)

    sign_review = subparsers.add_parser("sign-review-record")
    _add_review_context_arguments(sign_review)
    sign_review.add_argument("--reviewer-private-key", type=Path, required=True)
    sign_review.add_argument("--output", type=Path, required=True)
    sign_review.add_argument("--force", action="store_true")

    verify_review = subparsers.add_parser("verify-review-record")
    _add_review_context_arguments(verify_review)
    verify_review.add_argument("--attestation", type=Path, required=True)
    verify_review.add_argument(
        "--trusted-reviewer-public-key",
        type=Path,
        required=True,
    )

    validate_inputs = subparsers.add_parser("validate-review-quorum-inputs")
    validate_inputs.add_argument("inputs", type=Path)

    build_quorum = subparsers.add_parser("build-review-quorum")
    build_quorum.add_argument("--inputs", type=Path, required=True)
    build_quorum.add_argument("--output", type=Path, required=True)
    build_quorum.add_argument("--force", action="store_true")

    validate_quorum = subparsers.add_parser("validate-review-quorum")
    validate_quorum.add_argument("envelope", type=Path)

    sign_quorum = subparsers.add_parser("sign-review-quorum")
    sign_quorum.add_argument("--envelope", type=Path, required=True)
    sign_quorum.add_argument("--private-key", type=Path, required=True)
    sign_quorum.add_argument("--output", type=Path, required=True)
    sign_quorum.add_argument("--force", action="store_true")

    verify_quorum = subparsers.add_parser("verify-review-quorum")
    verify_quorum.add_argument("--envelope", type=Path, required=True)
    verify_quorum.add_argument("--attestation", type=Path, required=True)
    verify_quorum.add_argument("--trusted-public-key", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in _PHASE8_COMMANDS:
        return legacy_main(arguments)
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
    if command == "validate-decision-request":
        return load_decision_request(arguments.request).summary()
    if command == "sign-decision-request":
        document = sign_decision_request(
            arguments.request,
            arguments.private_key,
            arguments.output,
            force=bool(arguments.force),
        )
        payload = _object(document.get("payload"), "decision request signer payload")
        request = _object(payload.get("request"), "decision request identity")
        return {
            "attestation": str(Path(arguments.output).resolve()),
            "request_id": request["request_id"],
            "request_sha256": request["canonical_sha256"],
            "key_id": payload["key_id"],
            "deployment_authorized": False,
            "trading_authorized": False,
        }
    if command == "verify-decision-request":
        return verify_decision_request_attestation(
            arguments.request,
            arguments.attestation,
            trusted_public_key_path=arguments.trusted_public_key,
        ).as_dict()
    if command == "validate-review-record":
        return load_review_record(arguments.record).summary()
    if command == "sign-review-record":
        document = sign_review_record(
            record_path=arguments.record,
            request_path=arguments.request,
            request_attestation_path=arguments.request_attestation,
            trusted_requester_public_key_path=(
                arguments.trusted_requester_public_key
            ),
            dossier_path=arguments.dossier,
            dossier_attestation_path=arguments.dossier_attestation,
            trusted_dossier_public_key_path=arguments.trusted_dossier_public_key,
            reviewer_private_key_path=arguments.reviewer_private_key,
            output_path=arguments.output,
            force=bool(arguments.force),
        )
        payload = _object(document.get("payload"), "review signer payload")
        review = _object(payload.get("review"), "review identity")
        return {
            "attestation": str(Path(arguments.output).resolve()),
            "record_id": review["record_id"],
            "record_sha256": review["canonical_sha256"],
            "decision": review["decision"],
            "key_id": payload["key_id"],
            "deployment_authorized": False,
            "trading_authorized": False,
        }
    if command == "verify-review-record":
        return verify_review_record_attestation(
            record_path=arguments.record,
            attestation_path=arguments.attestation,
            trusted_reviewer_public_key_path=(
                arguments.trusted_reviewer_public_key
            ),
            request_path=arguments.request,
            request_attestation_path=arguments.request_attestation,
            trusted_requester_public_key_path=(
                arguments.trusted_requester_public_key
            ),
            dossier_path=arguments.dossier,
            dossier_attestation_path=arguments.dossier_attestation,
            trusted_dossier_public_key_path=arguments.trusted_dossier_public_key,
        ).as_dict()
    if command == "validate-review-quorum-inputs":
        return load_review_quorum_inputs(arguments.inputs).summary()
    if command == "build-review-quorum":
        output = _available_output(arguments.output, force=bool(arguments.force))
        envelope = build_review_quorum(arguments.inputs)
        write_json(output, envelope.as_dict())
        return {"output": str(output), **envelope.as_dict()}
    if command == "validate-review-quorum":
        return load_review_quorum_envelope(arguments.envelope).summary()
    if command == "sign-review-quorum":
        document = sign_review_quorum_envelope(
            arguments.envelope,
            arguments.private_key,
            arguments.output,
            force=bool(arguments.force),
        )
        payload = _object(document.get("payload"), "review quorum signer payload")
        envelope_identity = _object(payload.get("envelope"), "review quorum identity")
        return {
            "attestation": str(Path(arguments.output).resolve()),
            "envelope_id": envelope_identity["envelope_id"],
            "envelope_sha256": envelope_identity["envelope_sha256"],
            "status": envelope_identity["status"],
            "key_id": payload["key_id"],
            "deployment_authorized": False,
            "trading_authorized": False,
            "release_authorized": False,
        }
    if command == "verify-review-quorum":
        return verify_review_quorum_attestation(
            arguments.envelope,
            arguments.attestation,
            trusted_public_key_path=arguments.trusted_public_key,
        ).as_dict()
    raise RuntimeError(f"unsupported Phase 8 command: {command}")


def _add_review_context_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-attestation", type=Path, required=True)
    parser.add_argument(
        "--trusted-requester-public-key",
        type=Path,
        required=True,
    )
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--dossier-attestation", type=Path, required=True)
    parser.add_argument(
        "--trusted-dossier-public-key",
        type=Path,
        required=True,
    )


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
