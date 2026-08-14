# LLM Arbitrage System

This branch contains **Phase 1** of the paper-first architecture derived from the supplied *Trading Systems and Methods 資源* PDF.

Phase 1 establishes the safe, testable foundation:

- immutable domain contracts for market events, features, plans, approvals, fills, and results
- typed runtime configuration with conservative defaults
- Kaufman Efficiency Ratio and KAMA analytics
- rolling Z-score, ATR percentage, and one-dimensional Kalman filtering
- in-memory event storage and execution-journal interfaces
- deterministic synthetic/replay input and paper fill simulation
- Python packaging, CI, contributor guidance, and security boundaries

Real venue credentials, wallet signing, live order endpoints, and withdrawal functions are deliberately excluded.

## Install and test

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
make check
```

## Planned follow-up

Phase 2 wires the three PDF-derived research paths—funding carry, overcrowding reversion, and RWA lead-lag—through central risk approval, compensated multi-leg paper execution, backtest replay, and the asyncio orchestrator.

The complete locally validated paper-MVP implementation is maintained as the implementation artifact for this workstream while this draft branch is reviewed.
