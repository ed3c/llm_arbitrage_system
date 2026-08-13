# Architecture

The supplied PDF defines six stages: market ingestion and storage, Kaufman/noise analytics, three strategy paths, central risk approval, multi-leg paper execution, and an `asyncio.Queue` producer-consumer pipeline.

## Runtime contract

```text
MarketEvent
  -> FeatureSnapshot
  -> TradePlan
  -> ApprovedTradePlan
  -> ExecutionResult
```

Value objects are immutable. Monetary values use `Decimal`. Timestamps are timezone-aware. Strategies cannot call execution adapters directly.

## Failure model

Paper legs execute concurrently. If one simulated leg fails after another fills, the router creates a reverse paper leg for the confirmed quantity. Failed compensation records residual exposure and halts new entries until reconciliation.

## Storage

`TimeSeriesStore` is the stable interface. In-memory storage keeps tests fast, while SQLite provides durable local replay. Analytics and strategies do not depend on the selected backend.
