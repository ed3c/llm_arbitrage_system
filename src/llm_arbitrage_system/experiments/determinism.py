from __future__ import annotations

from dataclasses import replace

from llm_arbitrage_system.domain.contracts import FeatureSnapshot, MarketEvent, TradePlan
from llm_arbitrage_system.experiments.canonical import (
    canonical_json_bytes,
    feature_payload,
    market_event_payload,
    sha256_hex,
    trade_plan_semantic_payload,
)
from llm_arbitrage_system.simulation.protocols import Planner


class ContentAddressedPlanner:
    """Replace UUID defaults with identifiers derived from replay evidence."""

    def __init__(self, delegate: Planner, *, dataset_semantic_sha256: str) -> None:
        if len(dataset_semantic_sha256) != 64:
            raise ValueError("dataset_semantic_sha256 must be a SHA-256 hex digest")
        self.delegate = delegate
        self.dataset_semantic_sha256 = dataset_semantic_sha256
        self._feature_sequence = 0

    def plan(self, event: MarketEvent, features: FeatureSnapshot) -> TradePlan | None:
        feature_sequence = self._feature_sequence
        self._feature_sequence += 1
        plan = self.delegate.plan(event, features)
        if plan is None:
            return None

        identity_payload = {
            "schema_version": 1,
            "dataset_semantic_sha256": self.dataset_semantic_sha256,
            "feature_sequence": feature_sequence,
            "event": market_event_payload(event),
            "features": feature_payload(features),
            "plan": trade_plan_semantic_payload(plan),
        }
        digest = sha256_hex(canonical_json_bytes(identity_payload))
        deterministic_legs = tuple(
            replace(leg, client_order_id=f"leg-{digest[:24]}-{index}")
            for index, leg in enumerate(plan.legs)
        )
        context = dict(plan.context)
        context["content_address"] = digest
        context["feature_sequence"] = feature_sequence
        return replace(
            plan,
            plan_id=f"plan-{digest[:32]}",
            legs=deterministic_legs,
            context=context,
        )
