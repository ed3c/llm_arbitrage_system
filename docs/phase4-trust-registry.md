# Phase 4 signed provenance, lineage, and OOS registry

Phase 4 wraps the deterministic Phase 3 experiment runner with a local trust and evaluation control plane. It does not add connectivity, account access, or live execution.

## Trust flow

```text
verified evidence bundle
  -> detached Ed25519 attestation
  -> optional trusted-key match
  -> optional registered dataset lineage
  -> immutable local registry import
```

`keygen` writes a PKCS8 private key with mode `0600` and a public key. Private keys stay outside the repository and evidence bundles. The detached attestation binds the experiment ID, run ID, manifest digest, checksum-file digest, bundle-root digest, signer key ID, embedded public key, and optional lineage ID.

A valid signature proves that the holder of one local provenance key signed those captured bytes. It does not establish market-data truth, legal identity, profitability, or risk-free returns.

## Dataset lineage

A schema-v1 lineage manifest contains the dataset semantic SHA-256, source/derived/slice kind, a named and versioned transformation, canonical parameters, parent lineage IDs, and optional source notes. Its lineage ID is content-addressed. Source nodes cannot have parents; derived and slice nodes require parents. The registry refuses a child until every parent exists.

## Planned test-window execution

```text
Phase 3 matrix
  -> evaluation_id
  -> candidate overrides + config hash
  -> train and test slice hashes
  -> replay test slice only
  -> evaluation.json
  -> checksummed bundle
  -> detached signature
  -> registry registration
```

Registration recomputes the matrix identity and rejects a bundle unless the evaluation ID, candidate configuration hash, test dataset hash, train hash, indexes, experiment manifest, and trusted signature all match. The train slice is planning evidence only; it is not replayed by the Phase 4 test runner.

## Registry schema

| Table | Role |
| --- | --- |
| `trusted_keys` | Ed25519 public-key allowlist |
| `lineage_nodes` | immutable content-addressed lineage manifests |
| `lineage_edges` | parent DAG relationships |
| `experiments` | signed bundle identity, reports, trust, and optional lineage |
| `evaluations` | matrix-bound test-window registrations |

The local SQLite registry enables foreign keys, WAL, and `synchronous=FULL`. `registry-verify` runs SQLite integrity and foreign-key checks.

## Aggregation boundary

`registry-aggregate` reports expected, registered, trusted, and missing windows per candidate. It may average evidence-supported execution metrics. It deliberately emits null selection, realized PnL, Sharpe, and alpha-decay fields. Candidate selection requires a separately reviewed policy and stronger evidence.

Use `make phase4-smoke` for the complete offline path.
