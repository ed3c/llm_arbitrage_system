from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.lineage import load_lineage_manifest
from llm_arbitrage_system.experiments.registry import ExperimentRegistry
from llm_arbitrage_system.experiments.runner import run_experiment
from llm_arbitrage_system.experiments.signing import (
    generate_signing_keypair,
    sign_bundle,
    verify_attestation,
)


@pytest.mark.asyncio
async def test_detached_attestation_binds_bundle_and_trusted_key(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    result = await run_experiment(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase4-signing-test",
    )
    lineage = load_lineage_manifest(root / "examples/phase4/lineage.yaml")
    private_key = tmp_path / "keys/private.pem"
    public_key = tmp_path / "keys/public.pem"
    identity = generate_signing_keypair(private_key, public_key)
    assert private_key.stat().st_mode & 0o777 == 0o600
    attestation = tmp_path / "bundle.attestation.json"
    document = sign_bundle(
        result.bundle.bundle_path,
        private_key,
        attestation,
        lineage_id=lineage.manifest.lineage_id,
    )
    verification = verify_attestation(
        result.bundle.bundle_path,
        attestation,
        trusted_public_key_path=public_key,
        expected_lineage_id=lineage.manifest.lineage_id,
    )
    assert document["payload"]["key_id"] == identity.key_id
    assert verification.experiment_id == result.manifest.experiment_id
    assert verification.lineage_id == lineage.manifest.lineage_id
    assert verification.trusted_key_matched


@pytest.mark.asyncio
async def test_attestation_detects_signature_and_bundle_tampering(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    result = await run_experiment(
        dataset_path=root / "examples/phase3/market_events.jsonl",
        config_path=root / "examples/phase3/experiment.yaml",
        output_root=tmp_path / "runs",
        code_revision="phase4-tamper-test",
    )
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    generate_signing_keypair(private_key, public_key)
    attestation = tmp_path / "attestation.json"
    sign_bundle(result.bundle.bundle_path, private_key, attestation)
    payload = json.loads(attestation.read_text(encoding="utf-8"))
    original = str(payload["signature_base64"])
    replacement = "A" if original[0] != "A" else "B"
    payload["signature_base64"] = replacement + original[1:]
    attestation.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="signature"):
        verify_attestation(result.bundle.bundle_path, attestation)

    sign_bundle(result.bundle.bundle_path, private_key, attestation, force=True)
    report = result.bundle.bundle_path / "report.md"
    report.write_text(
        report.read_text(encoding="utf-8") + "tampered\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        verify_attestation(result.bundle.bundle_path, attestation)


def test_lineage_is_content_addressed_and_registry_requires_parents(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    source_path = root / "examples/phase4/lineage.yaml"
    source = load_lineage_manifest(source_path)
    derived_path = tmp_path / "derived.yaml"
    derived_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                (
                    "dataset_semantic_sha256: "
                    + source.manifest.dataset_semantic_sha256
                ),
                "kind: derived",
                "operation:",
                "  name: normalize",
                '  version: "1"',
                "  parameters: {}",
                "parents:",
                f"  - {source.manifest.lineage_id}",
                "source_uri: null",
                "notes: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    with ExperimentRegistry(tmp_path / "registry.sqlite3") as registry:
        with pytest.raises(ValueError, match="parent is not registered"):
            registry.import_lineage(derived_path)
        registry.import_lineage(source_path)
        registry.import_lineage(derived_path)
        summary = registry.verify()
    assert summary.lineage_nodes == 2
    assert summary.lineage_edges == 1


def test_lineage_content_tampering_changes_the_expected_identity(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    source = load_lineage_manifest(root / "examples/phase4/lineage.yaml")
    altered = tmp_path / "altered.yaml"
    text = (root / "examples/phase4/lineage.yaml").read_text(encoding="utf-8")
    altered.write_text(
        text.replace("synthetic_fixture_capture", "synthetic_fixture_capture_v2"),
        encoding="utf-8",
    )
    altered_snapshot = load_lineage_manifest(altered)
    assert altered_snapshot.manifest.lineage_id != source.manifest.lineage_id
