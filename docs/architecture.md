# Architecture

The supplied PDF defines market ingestion/storage, Kaufman and noise analytics, three strategy paths, central risk approval, multi-leg execution, and an `asyncio.Queue` pipeline. This repository keeps that data plane offline. Phases 3 and 4 add evidence and trust control planes around it.

## Runtime contract

```text
MarketEvent -> FeatureSnapshot -> TradePlan -> ApprovedTradePlan -> ExecutionResult
```

Value objects are immutable. Monetary values use `Decimal`. Timestamps are timezone-aware. Strategies cannot call execution adapters directly.

## Evidence and trust contract

```text
source JSONL + source YAML + code revision
  -> strict parsing and canonical identity
  -> deterministic paper replay
  -> SQLite journal + reports
  -> checksummed bundle
  -> detached Ed25519 attestation
  -> optional content-addressed lineage DAG
  -> trusted immutable registry import
  -> matrix-bound test evaluation
  -> coverage aggregation
```

The experiment identity includes semantic dataset and configuration hashes, code revision, package version, and schema version. Operational timestamps are excluded. The detached attestation binds the current manifest and checksum tree without creating a recursive signature/checksum dependency.

## Signature boundary

The canonical attestation payload contains the signer key ID and public key, experiment/run IDs, manifest SHA-256, checksum-file SHA-256, a derived bundle-root SHA-256, and optional lineage ID. Verification validates the bundle before the signature and all binding fields. A caller may require an exact trusted public key.

Private provenance keys are local secrets, not trading credentials. They stay outside the repository, bundles, SQLite evidence, and registry. Key generation writes the private file with mode `0600`.

## Lineage DAG

Lineage manifests describe the semantic dataset hash, source/derived/slice kind, named transformation, canonical parameters, parent lineage IDs, and optional source URI. The lineage ID is derived from canonical manifest content. The registry enforces parent-before-child import and foreign-key integrity.

## OOS evaluation flow

A Phase 3 matrix identifies candidate configurations and train/purge/test windows. Phase 4 locates one `evaluation_id`, verifies the source dataset and base config, reconstructs the candidate config, and replays only the test slice. The bundle receives a checksummed `evaluation.json`. Registry registration independently checks the matrix hash, candidate hash, train/test hashes, indexes, manifest, and trusted signature.

## Registry and aggregation

The local registry stores trusted keys, lineage nodes/edges, signed experiments, and registered evaluations. Rows are immutable. SQLite foreign keys, WAL, `synchronous=FULL`, integrity, and foreign-key checks are enabled.

Aggregation compares registered evaluations with matrix expectations. It reports complete, partial, and missing coverage plus execution-evidence averages. It does not perform candidate selection or populate realized PnL, Sharpe, or alpha decay.

## Failure model

Paper legs execute concurrently and partial outcomes are reversed. Pipeline exceptions abort the run and prevent bundle publication. Signature, lineage, trust, matrix, or registry mismatch fails closed before registration.
