from __future__ import annotations

from pathlib import Path

import pytest

from llm_arbitrage_system.experiments.selection_policy import (
    load_selection_policy,
)

_MATRIX_SHA = "b82cadbc214144710becc3f9cf3d3791d504687124308ed964704b2b07e40232"


def _write_policy(path: Path, *, reordered: bool = False) -> Path:
    if reordered:
        text = f"""decision_mode: human_review_only
schema_version: 1
matrix_sha256: {_MATRIX_SHA}
multiple_testing:
  require_adjusted_pairwise_evidence: false
  minimum_non_tied_pairwise_windows: 3
  family_alpha: "0.050"
  method: holm_sign_test
admission:
  maximum_alpha_decay_bps_per_window: "100.0"
  minimum_positive_window_fraction: "0.500"
  maximum_drawdown_pct: "25.0"
  require_equal_mark_lag: true
  require_equal_test_intervals: true
  require_equal_window_indexes: true
  require_complete_coverage: true
  minimum_windows_per_candidate: 3
  minimum_candidates: 2
objective:
  tie_breakers:
    - maximum_drawdown_pct
    - alpha_decay_bps_per_window
  direction: maximize
  metric: total_mark_to_market_pnl_usd
"""
    else:
        text = f"""schema_version: 1
matrix_sha256: {_MATRIX_SHA}
decision_mode: human_review_only
objective:
  metric: total_mark_to_market_pnl_usd
  direction: maximize
  tie_breakers:
    - maximum_drawdown_pct
    - alpha_decay_bps_per_window
admission:
  minimum_candidates: 2
  minimum_windows_per_candidate: 3
  require_complete_coverage: true
  require_equal_window_indexes: true
  require_equal_test_intervals: true
  require_equal_mark_lag: true
  maximum_drawdown_pct: "25"
  minimum_positive_window_fraction: "0.5"
  maximum_alpha_decay_bps_per_window: "100"
multiple_testing:
  method: holm_sign_test
  family_alpha: "0.05"
  minimum_non_tied_pairwise_windows: 3
  require_adjusted_pairwise_evidence: false
"""
    path.write_text(text, encoding="utf-8")
    return path


def test_selection_policy_identity_is_semantic_and_human_review_only(
    tmp_path: Path,
) -> None:
    first = load_selection_policy(_write_policy(tmp_path / "first.yaml"))
    second = load_selection_policy(
        _write_policy(tmp_path / "second.yaml", reordered=True)
    )

    assert first.policy_id == second.policy_id
    assert first.canonical_sha256 == second.canonical_sha256
    assert first.policy.decision_mode == "human_review_only"
    assert first.policy.objective.metric == "total_mark_to_market_pnl_usd"
    assert first.summary()["policy"]["admission"]["maximum_drawdown_pct"] == "25"
    assert "winner" not in first.summary()["policy"]
    assert "candidate_ids" not in first.summary()["policy"]


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        (
            'maximum_drawdown_pct: "25"',
            "maximum_drawdown_pct: 25.0",
        ),
        (
            "decision_mode: human_review_only",
            "decision_mode: automatic",
        ),
        (
            "  tie_breakers:\n    - maximum_drawdown_pct\n"
            "    - alpha_decay_bps_per_window",
            "  tie_breakers:\n    - maximum_drawdown_pct\n"
            "    - maximum_drawdown_pct",
        ),
        (
            f"matrix_sha256: {_MATRIX_SHA}",
            "matrix_sha256: not-a-digest",
        ),
    ],
)
def test_selection_policy_rejects_unsafe_or_ambiguous_values(
    tmp_path: Path,
    replacement: str,
    match: str,
) -> None:
    path = _write_policy(tmp_path / "policy.yaml")
    path.write_text(
        path.read_text(encoding="utf-8").replace(replacement, match),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_selection_policy(path)


def test_selection_policy_rejects_unknown_fields_and_duplicate_yaml_keys(
    tmp_path: Path,
) -> None:
    unknown = _write_policy(tmp_path / "unknown.yaml")
    unknown.write_text(
        unknown.read_text(encoding="utf-8") + "winner: candidate-forbidden\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown fields"):
        load_selection_policy(unknown)

    duplicate = _write_policy(tmp_path / "duplicate.yaml")
    duplicate.write_text(
        duplicate.read_text(encoding="utf-8") + "decision_mode: human_review_only\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid selection-policy YAML"):
        load_selection_policy(duplicate)


def test_selection_policy_rejects_invalid_threshold_ranges(tmp_path: Path) -> None:
    path = _write_policy(tmp_path / "policy.yaml")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'minimum_positive_window_fraction: "0.5"',
            'minimum_positive_window_fraction: "1.1"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="minimum_positive_window_fraction"):
        load_selection_policy(path)
