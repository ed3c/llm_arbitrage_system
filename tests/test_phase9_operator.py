from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.bundle_io import write_json
from llm_arbitrage_system.experiments.canonical import canonical_json_bytes, sha256_hex
from llm_arbitrage_system.experiments.replication import (
    ReplicationCohortEvidence,
    ReplicationReport,
)
from llm_arbitrage_system.experiments.replication_cli import build_parser
from llm_arbitrage_system.experiments.replication_cli import (
    main as replication_main,
)
from llm_arbitrage_system.experiments.replication_signing import (
    load_replication_report,
    sign_replication_report,
    verify_replication_attestation,
)
from llm_arbitrage_system.experiments.signing import generate_signing_keypair

_CANDIDATE_ID = "candidate-a0c8f92d194d01b5ecaf5dbf"
_CANDIDATE_CONFIG_SHA = (
    "a0c8f92d194d01b5ecaf5dbfa089b2ce230fd3366918a3918943ce005e0c4adc"
)
_PLAN_ID = "replication-plan-" + "1" * 40
_PLAN_SHA = "2" * 64


def _digest(value: int) -> str:
    return f"{value:064x}"


def _keypair(tmp_path: Path, name: str) -> tuple[Path, Path, str]:
    private_key = tmp_path / name / "private.pem"
    public_key = tmp_path / name / "public.pem"
    identity = generate_signing_keypair(private_key, public_key)
    return private_key, public_key, identity.key_id


def _cohort(
    index: int,
    *,
    statistics_key_id: str,
    dossier_key_id: str,
    quorum_key_id: str,
    pnl: Decimal,
) -> ReplicationCohortEvidence:
    return ReplicationCohortEvidence(
        cohort_id=f"cohort-{index:024x}",
        statistics_report_id=f"oos-report-{index:040x}",
        statistics_report_sha256=_digest(100 + index),
        statistics_signer_key_id=statistics_key_id,
        dossier_id=f"selection-dossier-{index:040x}",
        dossier_sha256=_digest(200 + index),
        dossier_signer_key_id=dossier_key_id,
        quorum_envelope_id=f"review-quorum-{index:040x}",
        quorum_envelope_sha256=_digest(300 + index),
        quorum_signer_key_id=quorum_key_id,
        quorum_status="approved_for_research_only",
        matrix_sha256=_digest(400 + index),
        code_revision="phase9-operator-test",
        package_version="0.1.0",
        periods_per_year=252,
        mark_lag_microseconds=60_000_000,
        window_count=3,
        test_semantic_sha256=tuple(
            _digest(index * 10 + window) for window in range(3)
        ),
        total_mark_to_market_pnl_usd=pnl,
        state="replication_consistent",
        reasons=(),
    )


def _report_path(
    tmp_path: Path,
) -> tuple[
    Path,
    dict[str, tuple[Path, Path, str]],
]:
    keys = {
        "statistics-a": _keypair(tmp_path, "statistics-a"),
        "statistics-b": _keypair(tmp_path, "statistics-b"),
        "dossier-a": _keypair(tmp_path, "dossier-a"),
        "dossier-b": _keypair(tmp_path, "dossier-b"),
        "quorum-a": _keypair(tmp_path, "quorum-a"),
        "quorum-b": _keypair(tmp_path, "quorum-b"),
        "report": _keypair(tmp_path, "report"),
        "wrong": _keypair(tmp_path, "wrong"),
    }
    cohorts = (
        _cohort(
            1,
            statistics_key_id=keys["statistics-a"][2],
            dossier_key_id=keys["dossier-a"][2],
            quorum_key_id=keys["quorum-a"][2],
            pnl=Decimal("10"),
        ),
        _cohort(
            2,
            statistics_key_id=keys["statistics-b"][2],
            dossier_key_id=keys["dossier-b"][2],
            quorum_key_id=keys["quorum-b"][2],
            pnl=Decimal("20"),
        ),
        _cohort(
            3,
            statistics_key_id=keys["statistics-a"][2],
            dossier_key_id=keys["dossier-a"][2],
            quorum_key_id=keys["quorum-a"][2],
            pnl=Decimal("30"),
        ),
    )
    independence_checks = tuple(
        sorted(
            {
                "minimum_replications": True,
                "minimum_distinct_quorum_signers": True,
                "minimum_distinct_dossier_signers": True,
                "minimum_distinct_statistics_signers": True,
                "disjoint_test_semantic_sha256": True,
                "distinct_matrix_sha256": True,
                "distinct_dossier_sha256": True,
                "distinct_quorum_envelope_sha256": True,
                "statistics_report_reuse_prohibited": True,
            }.items()
        )
    )
    comparability_checks = tuple(
        sorted(
            {
                "equal_code_revision": True,
                "equal_package_version": True,
                "equal_periods_per_year": True,
                "equal_terminal_mark_lag": True,
            }.items()
        )
    )
    acceptance_checks = tuple(
        sorted(
            {
                "minimum_research_approved_fraction": True,
                "minimum_positive_replication_fraction": True,
                "maximum_failed_replications": True,
                "maximum_insufficient_replications": True,
                "minimum_worst_case_total_pnl_usd": True,
                "minimum_median_total_pnl_usd": True,
            }.items()
        )
    )
    identity = {
        "schema_version": 1,
        "plan_id": _PLAN_ID,
        "plan_sha256": _PLAN_SHA,
        "candidate_id": _CANDIDATE_ID,
        "candidate_config_sha256": _CANDIDATE_CONFIG_SHA,
        "status": "replication_consistent",
        "cohort_count": 3,
        "research_approved_count": 3,
        "positive_replication_count": 3,
        "failed_replication_count": 0,
        "insufficient_replication_count": 0,
        "research_approved_fraction": "1",
        "positive_replication_fraction": "1",
        "worst_case_total_pnl_usd": "10",
        "median_total_pnl_usd": "20",
        "independence_checks": dict(independence_checks),
        "comparability_checks": dict(comparability_checks),
        "acceptance_checks": dict(acceptance_checks),
        "cohorts": [cohort.identity_payload() for cohort in cohorts],
    }
    report = ReplicationReport(
        report_id="replication-report-"
        + sha256_hex(canonical_json_bytes(identity))[:40],
        plan_id=_PLAN_ID,
        plan_sha256=_PLAN_SHA,
        candidate_id=_CANDIDATE_ID,
        candidate_config_sha256=_CANDIDATE_CONFIG_SHA,
        status="replication_consistent",
        cohort_count=3,
        research_approved_count=3,
        positive_replication_count=3,
        failed_replication_count=0,
        insufficient_replication_count=0,
        research_approved_fraction=Decimal("1"),
        positive_replication_fraction=Decimal("1"),
        worst_case_total_pnl_usd=Decimal("10"),
        median_total_pnl_usd=Decimal("20"),
        independence_checks=independence_checks,
        comparability_checks=comparability_checks,
        acceptance_checks=acceptance_checks,
        cohorts=cohorts,
    )
    path = tmp_path / "replication-report.json"
    write_json(path, report.as_dict())
    return path, keys


def test_replication_report_loader_recomputes_identity_and_aggregates(
    tmp_path: Path,
) -> None:
    path, _ = _report_path(tmp_path)

    snapshot = load_replication_report(path)

    assert snapshot.report_id.startswith("replication-report-")
    assert snapshot.plan_id == _PLAN_ID
    assert snapshot.status == "replication_consistent"
    assert len(snapshot.participant_key_ids) == 6
    assert snapshot.summary()["trading_authorized"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cohort_count", 4),
        ("research_approved_fraction", "0.5"),
        ("median_total_pnl_usd", "999"),
        ("status", "replication_failed"),
        ("deployment_authorized", True),
        ("trading_authorized", True),
        ("release_authorized", True),
        ("automatic_promotion", True),
    ],
)
def test_replication_report_loader_rejects_tamper(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    path, _ = _report_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    write_json(path, payload)

    with pytest.raises(ValueError):
        load_replication_report(path)


def test_replication_report_loader_rejects_noncanonical_and_duplicate_json(
    tmp_path: Path,
) -> None:
    path, _ = _report_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="canonical JSON"):
        load_replication_report(path)

    path.write_text(
        '{"schema_version":1,"schema_version":1}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate replication report JSON key"):
        load_replication_report(path)


def test_replication_signing_requires_independent_key_and_trusted_verification(
    tmp_path: Path,
) -> None:
    report, keys = _report_path(tmp_path)
    attestation = tmp_path / "replication.attestation.json"

    sign_replication_report(
        report,
        keys["report"][0],
        attestation,
    )
    verified = verify_replication_attestation(
        report,
        attestation,
        trusted_public_key_path=keys["report"][1],
    )

    assert verified.status == "replication_consistent"
    assert verified.cohort_count == 3
    assert verified.trusted_key_matched is True
    assert verified.as_dict()["deployment_authorized"] is False

    with pytest.raises(ValueError, match="must differ from every statistics"):
        sign_replication_report(
            report,
            keys["statistics-a"][0],
            tmp_path / "participant.attestation.json",
        )
    with pytest.raises(ValueError, match="trusted public key"):
        verify_replication_attestation(
            report,
            attestation,
            trusted_public_key_path=keys["wrong"][1],
        )
    with pytest.raises(FileExistsError):
        sign_replication_report(
            report,
            keys["report"][0],
            attestation,
        )


def test_replication_signature_rejects_report_tamper(
    tmp_path: Path,
) -> None:
    report, keys = _report_path(tmp_path)
    attestation = tmp_path / "replication.attestation.json"
    sign_replication_report(report, keys["report"][0], attestation)

    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["evidence_boundary"] = "tampered"
    write_json(report, payload)

    with pytest.raises(ValueError):
        verify_replication_attestation(
            report,
            attestation,
            trusted_public_key_path=keys["report"][1],
        )


def test_phase9_cli_validates_signs_and_verifies_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report, keys = _report_path(tmp_path)
    attestation = tmp_path / "replication.attestation.json"

    assert replication_main(["validate-replication-report", str(report)]) == 0
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_payload["status"] == "replication_consistent"

    assert (
        replication_main(
            [
                "sign-replication-report",
                "--report",
                str(report),
                "--private-key",
                str(keys["report"][0]),
                "--output",
                str(attestation),
            ]
        )
        == 0
    )
    sign_payload = json.loads(capsys.readouterr().out)
    assert sign_payload["release_authorized"] is False

    assert (
        replication_main(
            [
                "verify-replication-report",
                "--report",
                str(report),
                "--attestation",
                str(attestation),
                "--trusted-public-key",
                str(keys["report"][1]),
            ]
        )
        == 0
    )
    verify_payload = json.loads(capsys.readouterr().out)
    assert verify_payload["trusted_key_matched"] is True
    assert verify_payload["trading_authorized"] is False


def test_phase9_parser_has_no_live_release_or_deployment_commands() -> None:
    parser = build_parser()
    for command in (
        "deploy",
        "release",
        "trade",
        "withdraw",
        "connect-venue",
        "select-winner",
        "promote-candidate",
    ):
        with pytest.raises(SystemExit):
            parser.parse_args([command])
