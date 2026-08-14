# Architecture

The supplied PDF defines market ingestion and storage, Kaufman/noise analytics, three strategy paths, central risk approval, multi-leg execution, and an `asyncio.Queue` producer-consumer pipeline. This repository keeps that data plane offline and adds a separate Phase 3 evidence plane for repeatable experiments.

## Runtime contract

```text
MarketEvent
  -> FeatureSnapshot
  -> TradePlan
  -> ApprovedTradePlan
  -> ExecutionResult
```

Value objects are immutable. Monetary values use `Decimal`. Timestamps are timezone-aware. Strategies cannot call execution adapters directly.

## Phase 3 experiment contract

```text
source JSONL + source YAML + code revision
  -> strict parsing
  -> canonical dataset + canonical configuration
  -> semantic SHA-256 identity
  -> content-addressed plan identifiers
  -> PaperReplayPipeline
  -> SQLite journal + replay/performance reports
  -> manifest + checksums
  -> atomic bundle publication
  -> independent verification
```

The experiment identity includes the semantic dataset hash, canonical configuration hash, code revision, package version, and bundle schema version. Raw source hashes are retained for provenance, while whitespace and YAML/JSON key ordering do not alter semantic identity. Operational timestamps inside SQLite are evidence metadata and are intentionally excluded from the identity.

## Data and control flow

```text
JSONL MarketEvent dataset
  -> Dataset validator
  -> AnalyticsEngine
  -> ContentAddressedPlanner(PaperStrategyRouter)
  -> StatefulPaperApprover
  -> DeterministicPaperExecutor
  -> SQLiteReplayJournal
  -> ResearchPerformanceReport
  -> Evidence bundle verifier
```

The data plane remains bounded by `asyncio.Queue`. The control plane validates inputs before the pipeline starts, refuses silent overwrites, and publishes a bundle only after the journal reaches `completed` and SQLite reports `integrity_check = ok`.

## Failure model

Paper legs execute concurrently. If one simulated leg fails after another fills, the executor creates a reverse paper fill for the confirmed quantity. Failed reconciliation records residual exposure and halts new entries. Any pipeline-stage exception cancels sibling tasks and moves the replay run to `aborted`. A staging directory is removed rather than published as a completed bundle.

## Storage and verification

SQLite stores run lifecycle, market events, decisions, risk evaluations, and execution results. The final bundle contains the source and canonical inputs, SQLite database, machine-readable reports, a Markdown report, manifest, and SHA-256 file list. Verification rejects missing or extra files, unsafe checksum paths, symlinks, digest mismatches, source/canonical divergence, manifest identity drift, multiple replay rows, mismatched run IDs, non-completed runs, and failed SQLite integrity.

## Walk-forward planning

Phase 3 produces deterministic rolling or anchored train/purge/test windows and bounded Cartesian parameter grids. Every evaluation records candidate configuration, train slice hash, test slice hash, and a content-derived evaluation ID. Matrix creation is a research plan; it does not perform model selection or assert alpha decay.
