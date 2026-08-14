from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.aggregation import aggregate_registry_matrix
from llm_arbitrage_system.experiments.bundle import verify_bundle
from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.evaluation import run_planned_evaluation
from llm_arbitrage_system.experiments.lineage import load_lineage_manifest
from llm_arbitrage_system.experiments.registry import ExperimentRegistry
from llm_arbitrage_system.experiments.runner import run_experiment
from llm_arbitrage_system.experiments.signing import (
    generate_signing_keypair,
    sign_bundle,
    verify_attestation,
)
from llm_arbitrage_system.experiments.walk_forward import load_sweep_spec, matrix_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llm-arbitrage",
        description="Credential-free reproducible paper experiment runner.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_dataset = subparsers.add_parser("validate-dataset")
    validate_dataset.add_argument("dataset", type=Path)
    validate_config = subparsers.add_parser("validate-config")
    validate_config.add_argument("config", type=Path)
    validate_lineage = subparsers.add_parser("validate-lineage")
    validate_lineage.add_argument("lineage", type=Path)

    run = subparsers.add_parser("run")
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--code-revision")
    run.add_argument("--force", action="store_true")

    verify = subparsers.add_parser("verify")
    verify.add_argument("bundle", type=Path)

    matrix = subparsers.add_parser("plan-matrix")
    matrix.add_argument("--dataset", type=Path, required=True)
    matrix.add_argument("--config", type=Path, required=True)
    matrix.add_argument("--sweep", type=Path, required=True)
    matrix.add_argument("--output", type=Path, required=True)

    keygen = subparsers.add_parser("keygen")
    keygen.add_argument("--private-key", type=Path, required=True)
    keygen.add_argument("--public-key", type=Path, required=True)
    keygen.add_argument("--force", action="store_true")

    sign = subparsers.add_parser("sign-bundle")
    sign.add_argument("--bundle", type=Path, required=True)
    sign.add_argument("--private-key", type=Path, required=True)
    sign.add_argument("--output", type=Path, required=True)
    sign.add_argument("--lineage", type=Path)
    sign.add_argument("--force", action="store_true")

    verify_signature = subparsers.add_parser("verify-attestation")
    verify_signature.add_argument("--bundle", type=Path, required=True)
    verify_signature.add_argument("--attestation", type=Path, required=True)
    verify_signature.add_argument("--trusted-public-key", type=Path)
    verify_signature.add_argument("--lineage-id")

    evaluation = subparsers.add_parser("run-evaluation")
    evaluation.add_argument("--dataset", type=Path, required=True)
    evaluation.add_argument("--config", type=Path, required=True)
    evaluation.add_argument("--matrix", type=Path, required=True)
    evaluation.add_argument("--evaluation-id", required=True)
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.add_argument("--code-revision")
    evaluation.add_argument("--lineage-id")
    evaluation.add_argument("--force", action="store_true")

    registry_init = subparsers.add_parser("registry-init")
    registry_init.add_argument("registry", type=Path)
    registry_trust = subparsers.add_parser("registry-trust-key")
    registry_trust.add_argument("registry", type=Path)
    registry_trust.add_argument("public_key", type=Path)
    registry_trust.add_argument("--label")
    registry_lineage = subparsers.add_parser("registry-import-lineage")
    registry_lineage.add_argument("registry", type=Path)
    registry_lineage.add_argument("lineage", type=Path)
    registry_bundle = subparsers.add_parser("registry-import-bundle")
    registry_bundle.add_argument("registry", type=Path)
    registry_bundle.add_argument("bundle", type=Path)
    registry_bundle.add_argument("attestation", type=Path)
    registry_bundle.add_argument("--allow-untrusted", action="store_true")
    registry_evaluation = subparsers.add_parser("registry-register-evaluation")
    registry_evaluation.add_argument("registry", type=Path)
    registry_evaluation.add_argument("--matrix", type=Path, required=True)
    registry_evaluation.add_argument("--evaluation-id", required=True)
    registry_evaluation.add_argument("--bundle", type=Path, required=True)
    registry_evaluation.add_argument("--attestation", type=Path, required=True)
    registry_evaluation.add_argument("--allow-untrusted", action="store_true")
    registry_verify = subparsers.add_parser("registry-verify")
    registry_verify.add_argument("registry", type=Path)
    registry_aggregate = subparsers.add_parser("registry-aggregate")
    registry_aggregate.add_argument("registry", type=Path)
    registry_aggregate.add_argument("--matrix", type=Path, required=True)
    registry_aggregate.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        payload = _dispatch(arguments)
    except (OSError, ValueError, RuntimeError, PermissionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


def _dispatch(arguments: argparse.Namespace) -> dict[str, Any]:
    command = str(arguments.command)
    if command == "validate-dataset":
        return load_jsonl_dataset(arguments.dataset).summary()
    if command == "validate-config":
        return load_experiment_config(arguments.config).summary()
    if command == "validate-lineage":
        return load_lineage_manifest(arguments.lineage).summary()
    if command == "verify":
        return verify_bundle(arguments.bundle).as_dict()
    if command == "run":
        return asyncio.run(
            run_experiment(
                dataset_path=arguments.dataset,
                config_path=arguments.config,
                output_root=arguments.output,
                code_revision=arguments.code_revision,
                force=bool(arguments.force),
            )
        ).as_dict()
    if command == "plan-matrix":
        dataset = load_jsonl_dataset(arguments.dataset)
        config = load_experiment_config(arguments.config)
        payload = matrix_payload(dataset, config.config, load_sweep_spec(arguments.sweep))
        output = Path(arguments.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json_bytes(payload) + b"\n")
        return {
            "output": str(output),
            "candidate_count": payload["candidate_count"],
            "window_count": payload["window_count"],
            "evaluation_count": payload["evaluation_count"],
        }
    if command == "keygen":
        return generate_signing_keypair(
            arguments.private_key,
            arguments.public_key,
            force=bool(arguments.force),
        ).as_dict()
    if command == "sign-bundle":
        lineage_id = None
        if arguments.lineage is not None:
            lineage_id = load_lineage_manifest(arguments.lineage).manifest.lineage_id
        document = sign_bundle(
            arguments.bundle,
            arguments.private_key,
            arguments.output,
            lineage_id=lineage_id,
            force=bool(arguments.force),
        )
        signed = document["payload"]
        if not isinstance(signed, dict):
            raise RuntimeError("signer returned an invalid payload")
        return {
            "attestation": str(Path(arguments.output).resolve()),
            "experiment_id": signed["experiment_id"],
            "key_id": signed["key_id"],
            "lineage_id": signed["lineage_id"],
        }
    if command == "verify-attestation":
        return verify_attestation(
            arguments.bundle,
            arguments.attestation,
            trusted_public_key_path=arguments.trusted_public_key,
            expected_lineage_id=arguments.lineage_id,
        ).as_dict()
    if command == "run-evaluation":
        return asyncio.run(
            run_planned_evaluation(
                dataset_path=arguments.dataset,
                config_path=arguments.config,
                matrix_path=arguments.matrix,
                evaluation_id=str(arguments.evaluation_id),
                output_root=arguments.output,
                code_revision=arguments.code_revision,
                lineage_id=arguments.lineage_id,
                force=bool(arguments.force),
            )
        ).as_dict()
    if command == "registry-init":
        with ExperimentRegistry(arguments.registry) as registry:
            return registry.verify().as_dict()
    if command == "registry-trust-key":
        with ExperimentRegistry(arguments.registry) as registry:
            return registry.trust_public_key(arguments.public_key, label=arguments.label)
    if command == "registry-import-lineage":
        with ExperimentRegistry(arguments.registry) as registry:
            return registry.import_lineage(arguments.lineage)
    if command == "registry-import-bundle":
        with ExperimentRegistry(arguments.registry) as registry:
            return registry.import_bundle(
                arguments.bundle,
                arguments.attestation,
                allow_untrusted=bool(arguments.allow_untrusted),
            )
    if command == "registry-register-evaluation":
        with ExperimentRegistry(arguments.registry) as registry:
            return registry.register_evaluation(
                matrix_path=arguments.matrix,
                evaluation_id=str(arguments.evaluation_id),
                bundle_path=arguments.bundle,
                attestation_path=arguments.attestation,
                allow_untrusted=bool(arguments.allow_untrusted),
            )
    if command == "registry-verify":
        with ExperimentRegistry(arguments.registry) as registry:
            return registry.verify().as_dict()
    if command == "registry-aggregate":
        payload = aggregate_registry_matrix(arguments.registry, arguments.matrix)
        if arguments.output is not None:
            write_json(Path(arguments.output).resolve(), payload)
        return payload
    raise RuntimeError(f"unsupported command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
