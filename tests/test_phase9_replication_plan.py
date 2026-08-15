from __future__ import annotations

from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.replication_plan import (
    load_replication_plan,
)

_CANDIDATE_ID = "candidate-a0c8f92d194d01b5ecaf5dbf"
_CANDIDATE_CONFIG_SHA = (
    "a0c8f92d194d01b5ecaf5dbfa089b2ce230fd3366918a3918943ce005e0c4adc"
)


def _write_plan(path: Path, *, reordered: bool = False) -> Path:
    if reordered:
        text = f"""authority:
  trading_authorized: false
  deployment_authorized: false
  release_authorized: false
  automatic_promotion: false
  human_admit_required: true
acceptance:
  require_all_reserved_holdouts_positive: true
  minimum_median_total_pnl_usd: "0.00"
  minimum_worst_case_total_pnl_usd: "0.000"
  maximum_insufficient_replications: 0
  maximum_failed_replications: 1
  minimum_positive_replication_fraction: "0.6700"
  minimum_research_approved_fraction: "0.670"
comparability:
  require_equal_terminal_mark_lag: true
  require_equal_periods_per_year: true
  require_equal_package_version: true
  require_equal_code_revision: true
independence:
  prohibit_phase6_source_report_reuse: true
  require_distinct_quorum_envelope_sha256: true
  require_distinct_dossier_sha256: true
  require_distinct_matrix_sha256: true
  require_distinct_dataset_semantic_sha256: true
  minimum_distinct_quorum_signers: 2
  minimum_replications: 3
candidate:
  candidate_config_sha256: {_CANDIDATE_CONFIG_SHA}
  candidate_id: {_CANDIDATE_ID}
scope: independent_offline_replication
schema_version: 1
"""
    else:
        text = f"""schema_version: 1
scope: independent_offline_replication
candidate:
  candidate_id: {_CANDIDATE_ID}
  candidate_config_sha256: {_CANDIDATE_CONFIG_SHA}
independence:
  minimum_replications: 3
  minimum_distinct_quorum_signers: 2
  require_distinct_dataset_semantic_sha256: true
  require_distinct_matrix_sha256: true
  require_distinct_dossier_sha256: true
  require_distinct_quorum_envelope_sha256: true
  prohibit_phase6_source_report_reuse: true
comparability:
  require_equal_code_revision: true
  require_equal_package_version: true
  require_equal_periods_per_year: true
  require_equal_terminal_mark_lag: true
acceptance:
  minimum_research_approved_fraction: "0.67"
  minimum_positive_replication_fraction: "0.67"
  maximum_failed_replications: 1
  maximum_insufficient_replications: 0
  minimum_worst_case_total_pnl_usd: "0"
  minimum_median_total_pnl_usd: "0"
  require_all_reserved_holdouts_positive: true
authority:
  human_admit_required: true
  automatic_promotion: false
  release_authorized: false
  deployment_authorized: false
  trading_authorized: false
"""
    path.write_text(text, encoding="utf-8")
    return path


def test_replication_plan_identity_is_semantic_and_non_authorizing(
    tmp_path: Path,
) -> None:
    first = load_replication_plan(_write_plan(tmp_path / "first.yaml"))
    second = load_replication_plan(
        _write_plan(tmp_path / "second.yaml", reordered=True)
    )

    assert first.plan_id == second.plan_id
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.plan_id.startswith("replication-plan-")

    payload = first.summary()["plan"]
    assert payload["scope"] == "independent_offline_replication"
    assert payload["candidate"]["candidate_id"] == _CANDIDATE_ID
    assert payload["acceptance"]["minimum_research_approved_fraction"] == "0.67"
    assert payload["authority"] == {
        "human_admit_required": True,
        "automatic_promotion": False,
        "release_authorized": False,
        "deployment_authorized": False,
        "trading_authorized": False,
    }
    assert "winner" not in payload
    assert "selection" not in payload
    assert "rank" not in payload
    assert "score" not in payload


def test_material_threshold_change_changes_replication_plan_identity(
    tmp_path: Path,
) -> None:
    first_path = _write_plan(tmp_path / "first.yaml")
    second_path = _write_plan(tmp_path / "second.yaml")
    second_path.write_text(
        second_path.read_text(encoding="utf-8").replace(
            'minimum_median_total_pnl_usd: "0"',
            'minimum_median_total_pnl_usd: "1"',
        ),
        encoding="utf-8",
    )

    first = load_replication_plan(first_path)
    second = load_replication_plan(second_path)

    assert first.plan_id != second.plan_id
    assert first.canonical_sha256 != second.canonical_sha256


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        (
            'minimum_research_approved_fraction: "0.67"',
            "minimum_research_approved_fraction: 0.67",
        ),
        (
            'minimum_positive_replication_fraction: "0.67"',
            'minimum_positive_replication_fraction: "NaN"',
        ),
        (
            'minimum_positive_replication_fraction: "0.67"',
            'minimum_positive_replication_fraction: "1.1"',
        ),
        (
            "scope: independent_offline_replication",
            "scope: live_replication",
        ),
        (
            f"candidate_id: {_CANDIDATE_ID}",
            "candidate_id: candidate-not-hex",
        ),
        (
            f"candidate_config_sha256: {_CANDIDATE_CONFIG_SHA}",
            "candidate_config_sha256: not-a-digest",
        ),
        ("minimum_replications: 3", "minimum_replications: true"),
        (
            "minimum_distinct_quorum_signers: 2",
            "minimum_distinct_quorum_signers: 4",
        ),
        (
            "require_distinct_matrix_sha256: true",
            "require_distinct_matrix_sha256: false",
        ),
        (
            "require_equal_code_revision: true",
            "require_equal_code_revision: false",
        ),
        (
            "require_all_reserved_holdouts_positive: true",
            "require_all_reserved_holdouts_positive: false",
        ),
        ("human_admit_required: true", "human_admit_required: false"),
        ("automatic_promotion: false", "automatic_promotion: true"),
        ("release_authorized: false", "release_authorized: true"),
        ("deployment_authorized: false", "deployment_authorized: true"),
        ("trading_authorized: false", "trading_authorized: true"),
    ],
)
def test_replication_plan_rejects_unsafe_or_ambiguous_values(
    tmp_path: Path,
    original: str,
    replacement: str,
) -> None:
    path = _write_plan(tmp_path / "plan.yaml")
    path.write_text(
        path.read_text(encoding="utf-8").replace(original, replacement),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_replication_plan(path)


def test_replication_plan_rejects_unknown_missing_and_duplicate_fields(
    tmp_path: Path,
) -> None:
    unknown = _write_plan(tmp_path / "unknown.yaml")
    unknown.write_text(
        unknown.read_text(encoding="utf-8") + "winner: forbidden\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown fields"):
        load_replication_plan(unknown)

    missing = _write_plan(tmp_path / "missing.yaml")
    missing.write_text(
        missing.read_text(encoding="utf-8").replace(
            f"  candidate_config_sha256: {_CANDIDATE_CONFIG_SHA}\n",
            "",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing fields"):
        load_replication_plan(missing)

    duplicate = _write_plan(tmp_path / "duplicate.yaml")
    duplicate.write_text(
        duplicate.read_text(encoding="utf-8")
        + "scope: independent_offline_replication\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid replication-plan YAML"):
        load_replication_plan(duplicate)


def test_replication_plan_requires_a_possible_consistent_outcome(
    tmp_path: Path,
) -> None:
    path = _write_plan(tmp_path / "plan.yaml")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "maximum_failed_replications: 1",
        "maximum_failed_replications: 2",
    )
    text = text.replace(
        "maximum_insufficient_replications: 0",
        "maximum_insufficient_replications: 1",
    )
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match="leave at least one consistent replication"):
        load_replication_plan(path)
