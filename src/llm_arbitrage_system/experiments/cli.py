from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.aggregation import aggregate_registry_matrix
from llm_arbitrage_system.experiments.bundle import verify_bundle
from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.bundle_validation import (
    json_object,
    nested_string,
)
from llm_arbitrage_system.experiments.campaign import load_campaign_spec
from llm_arbitrage_system.experiments.campaign_runner import (
    campaign_status,
    run_campaign,
)
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.evaluation import run_planned_evaluation
from llm_arbitrage_system.experiments.lineage import load_lineage_manifest
from llm_arbitrage_system.experiments.manifest import resolve_code_revision
from llm_arbitrage_system.experiments.oos_statistics import build_oos_statistics
from llm_arbitrage_system.experiments.registry import ExperimentRegistry
from llm_arbitrage_system.experiments.runner import run_experiment
from llm_arbitrage_system.experiments.selection_diagnostics import (
    build_selection_diagnostics,
)
from llm_arbitrage_system.experiments.selection_dossier import (
    build_selection_dossier,
)
from llm_arbitrage_system.experiments.selection_policy import load_selection_policy
from llm_arbitrage_system.experiments.selection_signing import (
    sign_selection_dossier,
    verify_selection_dossier_attestation,
)
from llm_arbitrage_system.experiments.signing import (
    generate_signing_keypair,
    sign_bundle,
    verify_attestation,
)
from llm_arbitrage_system.experiments.statistics_inputs import load_statistics_inputs
from llm_arbitrage_system.experiments.statistics_signing import (
    sign_statistics_report,
    verify_statistics_attestation,
)
from llm_arbitrage_system.experiments.valuation import (
    load_terminal_marks,
    value_bundle,
)
from llm_arbitrage_system.experiments.walk_forward import (
    load_sweep_spec,
    matrix_payload,
)


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
    validate_campaign = subparsers.add_parser("validate-campaign")
    validate_campaign.add_argument("campaign", type=Path)
    validate_marks = subparsers.add_parser("validate-marks")
    validate_marks.add_argument("marks", type=Path)
    validate_statistics = subparsers.add_parser("validate-statistics-inputs")
    validate_statistics.add_argument("inputs", type=Path)
    validate_selection_policy = subparsers.add_parser("validate-selection-policy")
    validate_selection_policy.add_argument("policy", type=Path)

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
    lineage_group = verify_signature.add_mutually_exclusive_group()
    lineage_group.add_argument("--lineage", type=Path)
    lineage_group.add_argument("--lineage-id")

    evaluation = subparsers.add_parser("run-evaluation")
    evaluation.add_argument("--dataset", type=Path, required=True)
    evaluation.add_argument("--config", type=Path, required=True)
    evaluation.add_argument("--matrix", type=Path, required=True)
    evaluation.add_argument("--evaluation-id", required=True)
    evaluation.add_argument("--output", type=Path, required=True)
    evaluation.add_argument("--code-revision")
    evaluation.add_argument("--lineage-id")
    evaluation.add_argument("--force", action="store_true")

    campaign = subparsers.add_parser("run-campaign")
    campaign.add_argument("--dataset", type=Path, required=True)
    campaign.add_argument("--config", type=Path, required=True)
    campaign.add_argument("--matrix", type=Path, required=True)
    campaign.add_argument("--campaign", type=Path, required=True)
    campaign.add_argument("--registry", type=Path, required=True)
    campaign.add_argument("--private-key", type=Path, required=True)
    campaign.add_argument("--output", type=Path, required=True)
    campaign.add_argument("--code-revision")
    campaign.add_argument("--lineage-id")
    campaign.add_argument("--retry-failed", action="store_true")

    campaign_summary = subparsers.add_parser("campaign-status")
    campaign_summary.add_argument("workspace", type=Path)

    valuation = subparsers.add_parser("value-bundle")
    valuation.add_argument("--bundle", type=Path, required=True)
    valuation.add_argument("--marks", type=Path, required=True)
    valuation.add_argument("--output", type=Path, required=True)
    valuation.add_argument("--code-revision")
    valuation.add_argument("--force", action="store_true")

    statistics = subparsers.add_parser("campaign-statistics")
    statistics.add_argument("--registry", type=Path, required=True)
    statistics.add_argument("--matrix", type=Path, required=True)
    statistics.add_argument("--inputs", type=Path, required=True)
    statistics.add_argument("--initial-equity", required=True)
    statistics.add_argument("--periods-per-year", type=int, required=True)
    statistics.add_argument("--output", type=Path, required=True)
    statistics.add_argument("--code-revision")
    statistics.add_argument("--force", action="store_true")

    sign_statistics = subparsers.add_parser("sign-statistics")
    sign_statistics.add_argument("--report", type=Path, required=True)
    sign_statistics.add_argument("--private-key", type=Path, required=True)
    sign_statistics.add_argument("--output", type=Path, required=True)
    sign_statistics.add_argument("--force", action="store_true")

    verify_statistics = subparsers.add_parser("verify-statistics")
    verify_statistics.add_argument("--report", type=Path, required=True)
    verify_statistics.add_argument("--attestation", type=Path, required=True)
    verify_statistics.add_argument("--trusted-public-key", type=Path)

    diagnostics = subparsers.add_parser("selection-diagnostics")
    diagnostics.add_argument("--policy", type=Path, required=True)
    diagnostics.add_argument("--statistics", type=Path, required=True)
    diagnostics.add_argument("--output", type=Path, required=True)
    diagnostics.add_argument("--code-revision")
    diagnostics.add_argument("--force", action="store_true")

    dossier = subparsers.add_parser("build-selection-dossier")
    dossier.add_argument("--policy", type=Path, required=True)
    dossier.add_argument("--statistics", type=Path, required=True)
    dossier.add_argument("--diagnostics", type=Path, required=True)
    dossier.add_argument("--output", type=Path, required=True)
    dossier.add_argument("--code-revision")
    dossier.add_argument("--force", action="store_true")

    sign_dossier = subparsers.add_parser("sign-selection-dossier")
    sign_dossier.add_argument("--dossier", type=Path, required=True)
    sign_dossier.add_argument("--private-key", type=Path, required=True)
    sign_dossier.add_argument("--output", type=Path, required=True)
    sign_dossier.add_argument("--force", action="store_true")

    verify_dossier = subparsers.add_parser("verify-selection-dossier")
    verify_dossier.add_argument("--dossier", type=Path, required=True)
    verify_dossier.add_argument("--attestation", type=Path, required=True)
    verify_dossier.add_argument("--trusted-public-key", type=Path)

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
    except (OSError, KeyError, ValueError, RuntimeError) as error:
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
    if command == "validate-campaign":
        return load_campaign_spec(arguments.campaign).summary()
    if command == "validate-marks":
        return load_terminal_marks(arguments.marks).summary()
    if command == "validate-statistics-inputs":
        return load_statistics_inputs(arguments.inputs).summary()
    if command == "validate-selection-policy":
        return load_selection_policy(arguments.policy).summary()
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
        payload = matrix_payload(
            dataset,
            config.config,
            load_sweep_spec(arguments.sweep),
        )
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
            lineage = load_lineage_manifest(arguments.lineage).manifest
            _verify_lineage_matches_bundle(
                arguments.bundle,
                lineage.dataset_semantic_sha256,
            )
            lineage_id = lineage.lineage_id
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
        expected_lineage_id = arguments.lineage_id
        if arguments.lineage is not None:
            lineage = load_lineage_manifest(arguments.lineage).manifest
            _verify_lineage_matches_bundle(
                arguments.bundle,
                lineage.dataset_semantic_sha256,
            )
            expected_lineage_id = lineage.lineage_id
        return verify_attestation(
            arguments.bundle,
            arguments.attestation,
            trusted_public_key_path=arguments.trusted_public_key,
            expected_lineage_id=expected_lineage_id,
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
    if command == "run-campaign":
        return asyncio.run(
            run_campaign(
                dataset_path=arguments.dataset,
                config_path=arguments.config,
                matrix_path=arguments.matrix,
                campaign_path=arguments.campaign,
                registry_path=arguments.registry,
                private_key_path=arguments.private_key,
                output_root=arguments.output,
                code_revision=arguments.code_revision,
                lineage_id=arguments.lineage_id,
                retry_failed=bool(arguments.retry_failed),
            )
        ).as_dict()
    if command == "campaign-status":
        return campaign_status(arguments.workspace)
    if command == "value-bundle":
        output = _available_output(arguments.output, force=bool(arguments.force))
        valuation_report = value_bundle(
            arguments.bundle,
            arguments.marks,
            code_revision=resolve_code_revision(
                arguments.code_revision,
                cwd=Path.cwd(),
            ),
        )
        write_json(output, valuation_report.as_dict())
        return {"output": str(output), **valuation_report.as_dict()}
    if command == "campaign-statistics":
        output = _available_output(arguments.output, force=bool(arguments.force))
        inputs = load_statistics_inputs(arguments.inputs)
        statistics_report = build_oos_statistics(
            registry_path=arguments.registry,
            matrix_path=arguments.matrix,
            candidate_ids=inputs.candidate_ids,
            valuation_inputs=inputs.valuation_inputs,
            initial_equity_usd=_decimal_argument(
                str(arguments.initial_equity),
                "initial-equity",
            ),
            periods_per_year=int(arguments.periods_per_year),
            code_revision=resolve_code_revision(
                arguments.code_revision,
                cwd=Path.cwd(),
            ),
        )
        write_json(output, statistics_report.as_dict())
        return {"output": str(output), **statistics_report.as_dict()}
    if command == "sign-statistics":
        document = sign_statistics_report(
            arguments.report,
            arguments.private_key,
            arguments.output,
            force=bool(arguments.force),
        )
        signing_payload = document.get("payload")
        if not isinstance(signing_payload, dict):
            raise RuntimeError("statistics signer returned an invalid payload")
        report_identity = signing_payload.get("report")
        if not isinstance(report_identity, dict):
            raise RuntimeError("statistics signer returned an invalid report identity")
        return {
            "attestation": str(Path(arguments.output).resolve()),
            "report_id": report_identity["report_id"],
            "report_sha256": report_identity["report_sha256"],
            "key_id": signing_payload["key_id"],
        }
    if command == "verify-statistics":
        return verify_statistics_attestation(
            arguments.report,
            arguments.attestation,
            trusted_public_key_path=arguments.trusted_public_key,
        ).as_dict()
    if command == "selection-diagnostics":
        diagnostics_output = _available_output(
            arguments.output,
            force=bool(arguments.force),
        )
        diagnostics_report = build_selection_diagnostics(
            policy_path=arguments.policy,
            statistics_report_path=arguments.statistics,
            code_revision=resolve_code_revision(
                arguments.code_revision,
                cwd=Path.cwd(),
            ),
        )
        write_json(diagnostics_output, diagnostics_report.as_dict())
        return {"output": str(diagnostics_output), **diagnostics_report.as_dict()}
    if command == "build-selection-dossier":
        dossier_output = _available_output(
            arguments.output,
            force=bool(arguments.force),
        )
        dossier_report = build_selection_dossier(
            policy_path=arguments.policy,
            statistics_report_path=arguments.statistics,
            diagnostics_path=arguments.diagnostics,
            code_revision=resolve_code_revision(
                arguments.code_revision,
                cwd=Path.cwd(),
            ),
        )
        write_json(dossier_output, dossier_report.as_dict())
        return {"output": str(dossier_output), **dossier_report.as_dict()}
    if command == "sign-selection-dossier":
        dossier_document = sign_selection_dossier(
            arguments.dossier,
            arguments.private_key,
            arguments.output,
            force=bool(arguments.force),
        )
        dossier_signing_payload = dossier_document.get("payload")
        if not isinstance(dossier_signing_payload, dict):
            raise RuntimeError("selection dossier signer returned an invalid payload")
        dossier_identity = dossier_signing_payload.get("dossier")
        if not isinstance(dossier_identity, dict):
            raise RuntimeError("selection dossier signer returned an invalid identity")
        return {
            "attestation": str(Path(arguments.output).resolve()),
            "dossier_id": dossier_identity["dossier_id"],
            "dossier_sha256": dossier_identity["dossier_sha256"],
            "key_id": dossier_signing_payload["key_id"],
        }
    if command == "verify-selection-dossier":
        return verify_selection_dossier_attestation(
            arguments.dossier,
            arguments.attestation,
            trusted_public_key_path=arguments.trusted_public_key,
        ).as_dict()
    if command == "registry-init":
        with ExperimentRegistry(arguments.registry) as registry:
            return registry.verify().as_dict()
    if command == "registry-trust-key":
        with ExperimentRegistry(arguments.registry) as registry:
            return registry.trust_public_key(
                arguments.public_key,
                label=arguments.label,
            )
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
        payload = aggregate_registry_matrix(
            arguments.registry,
            arguments.matrix,
        )
        if arguments.output is not None:
            write_json(Path(arguments.output).resolve(), payload)
        return payload
    raise RuntimeError(f"unsupported command: {command}")


def _verify_lineage_matches_bundle(bundle: Path, dataset_hash: str) -> None:
    root = Path(bundle).resolve()
    verify_bundle(root)
    manifest = json_object(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    if nested_string(manifest, "dataset", "semantic_sha256") != dataset_hash:
        raise ValueError("lineage dataset hash does not match the bundle")


def _available_output(path: Path, *, force: bool) -> Path:
    output = path.resolve()
    if output.exists() and not force:
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _decimal_argument(value: str, name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a decimal string") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
