from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.bundle import verify_bundle, write_checksums
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.runner import run_experiment


@pytest.mark.asyncio
async def test_runner_writes_and_verifies_content_addressed_bundle(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    result = await run_experiment(
        dataset_path=root / "examples" / "phase3" / "market_events.jsonl",
        config_path=root / "examples" / "phase3" / "experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase3-test",
    )

    bundle = result.bundle.bundle_path
    assert bundle.name == result.manifest.experiment_id
    assert result.replay_report["events_received"] == 12
    assert result.replay_report["plans_approved"] == 1
    assert result.replay_report["filled"] == 1
    assert (bundle / "evidence.sqlite3").is_file()
    assert (bundle / "checksums.sha256").is_file()
    verification = verify_bundle(bundle)
    assert verification.run_status == "completed"
    assert verification.experiment_id == result.manifest.experiment_id


@pytest.mark.asyncio
async def test_runner_refuses_to_overwrite_existing_evidence(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    arguments = {
        "dataset_path": root / "examples" / "phase3" / "market_events.jsonl",
        "config_path": root / "examples" / "phase3" / "experiment.yaml",
        "output_root": tmp_path / "runs",
        "code_revision": "phase3-test",
    }
    await run_experiment(**arguments)
    with pytest.raises(FileExistsError):
        await run_experiment(**arguments)


@pytest.mark.asyncio
async def test_bundle_verifier_detects_tampering(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    result = await run_experiment(
        dataset_path=root / "examples" / "phase3" / "market_events.jsonl",
        config_path=root / "examples" / "phase3" / "experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase3-tamper-test",
    )
    report = result.bundle.bundle_path / "replay_report.json"
    report.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_bundle(result.bundle.bundle_path)


@pytest.mark.asyncio
async def test_bundle_verifier_relinks_raw_and_canonical_inputs(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    result = await run_experiment(
        dataset_path=root / "examples" / "phase3" / "market_events.jsonl",
        config_path=root / "examples" / "phase3" / "experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase3-source-link-test",
    )
    bundle = result.bundle.bundle_path
    source_path = bundle / "inputs" / "dataset.source.jsonl"
    source_text = source_path.read_text(encoding="utf-8")
    source_path.write_text(source_text.replace('"price":"100.0"', '"price":"101.0"', 1), encoding="utf-8")

    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset"]["source_sha256"] = sha256_hex(source_path.read_bytes())
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    write_checksums(bundle)

    with pytest.raises(ValueError, match="canonical input does not match its source"):
        verify_bundle(bundle)
