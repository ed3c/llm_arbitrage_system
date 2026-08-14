from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from llm_arbitrage_system.experiments.bundle import verify_bundle
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes
from llm_arbitrage_system.experiments.config import load_experiment_config
from llm_arbitrage_system.experiments.dataset import load_jsonl_dataset
from llm_arbitrage_system.experiments.runner import run_experiment
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

    validate_dataset = subparsers.add_parser(
        "validate-dataset",
        help="Validate a strict MarketEvent JSONL dataset.",
    )
    validate_dataset.add_argument("dataset", type=Path)

    validate_config = subparsers.add_parser(
        "validate-config",
        help="Validate and canonicalize an experiment YAML configuration.",
    )
    validate_config.add_argument("config", type=Path)

    run = subparsers.add_parser(
        "run",
        help="Run one content-addressed offline paper experiment.",
    )
    run.add_argument("--dataset", type=Path, required=True)
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--code-revision")
    run.add_argument("--force", action="store_true")

    verify = subparsers.add_parser(
        "verify",
        help="Verify checksums, manifest identity, and SQLite evidence.",
    )
    verify.add_argument("bundle", type=Path)

    matrix = subparsers.add_parser(
        "plan-matrix",
        help="Create a deterministic parameter-grid and walk-forward evaluation plan.",
    )
    matrix.add_argument("--dataset", type=Path, required=True)
    matrix.add_argument("--config", type=Path, required=True)
    matrix.add_argument("--sweep", type=Path, required=True)
    matrix.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        payload = _dispatch(arguments)
    except (OSError, ValueError, RuntimeError) as error:
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
    if command == "verify":
        return verify_bundle(arguments.bundle).as_dict()
    if command == "run":
        result = asyncio.run(
            run_experiment(
                dataset_path=arguments.dataset,
                config_path=arguments.config,
                output_root=arguments.output,
                code_revision=arguments.code_revision,
                force=bool(arguments.force),
            )
        )
        return result.as_dict()
    if command == "plan-matrix":
        dataset = load_jsonl_dataset(arguments.dataset)
        config = load_experiment_config(arguments.config)
        sweep = load_sweep_spec(arguments.sweep)
        payload = matrix_payload(dataset, config.config, sweep)
        output = Path(arguments.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_json_bytes(payload) + b"\n")
        return {
            "output": str(output),
            "candidate_count": payload["candidate_count"],
            "window_count": payload["window_count"],
            "evaluation_count": payload["evaluation_count"],
        }
    raise RuntimeError(f"unsupported command: {command}")


if __name__ == "__main__":
    raise SystemExit(main())
