from __future__ import annotations

from pathlib import Path

from llm_arbitrage_system.experiments.cli import main


def test_phase4_cli_signs_and_registers_trusted_bundle(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    dataset = root / "examples/phase3/market_events.jsonl"
    config = root / "examples/phase3/experiment.yaml"
    lineage = root / "examples/phase4/lineage.yaml"
    private_key = tmp_path / "keys/private.pem"
    public_key = tmp_path / "keys/public.pem"
    runs = tmp_path / "runs"
    registry = tmp_path / "registry.sqlite3"
    attestation = tmp_path / "bundle.attestation.json"

    assert (
        main(
            [
                "keygen",
                "--private-key",
                str(private_key),
                "--public-key",
                str(public_key),
            ]
        )
        == 0
    )
    assert main(["validate-lineage", str(lineage)]) == 0
    assert (
        main(
            [
                "run",
                "--dataset",
                str(dataset),
                "--config",
                str(config),
                "--output",
                str(runs),
                "--code-revision",
                "phase4-cli-test",
            ]
        )
        == 0
    )
    bundle = next(path for path in runs.iterdir() if path.name.startswith("exp-"))
    assert (
        main(
            [
                "sign-bundle",
                "--bundle",
                str(bundle),
                "--private-key",
                str(private_key),
                "--lineage",
                str(lineage),
                "--output",
                str(attestation),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify-attestation",
                "--bundle",
                str(bundle),
                "--attestation",
                str(attestation),
                "--trusted-public-key",
                str(public_key),
                "--lineage",
                str(lineage),
            ]
        )
        == 0
    )
    assert main(["registry-init", str(registry)]) == 0
    assert (
        main(
            [
                "registry-trust-key",
                str(registry),
                str(public_key),
                "--label",
                "test",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "registry-import-lineage",
                str(registry),
                str(lineage),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "registry-import-bundle",
                str(registry),
                str(bundle),
                str(attestation),
            ]
        )
        == 0
    )
    assert main(["registry-verify", str(registry)]) == 0
