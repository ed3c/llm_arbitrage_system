# Security policy

## Supported scope

The repository is an offline paper-research, replay, and evidence harness. It contains no exchange credentials, wallet signer, withdrawal path, external order endpoint, or live-mode branch.

## Secrets

Never commit `.env`, exchange API secrets, wallet keys, seed phrases, account identifiers, exported sessions, or provenance private keys. Fixtures use synthetic values only.

Phase 4 provenance keys are local signing keys, not trading credentials. They still authenticate evidence and must be protected:

- generate private keys outside the repository and evidence bundles
- retain file mode `0600`
- never print private-key bytes or embed them in attestations, SQLite, logs, issues, or CI artifacts
- rotate a compromised key by trusting a new public key; immutable historical rows are not rewritten

## Operational controls

- Treat order acknowledgements as non-terminal until a simulated fill or rejection is recorded.
- A failed compensation leaves residual exposure and halts new entries.
- Bundle, attestation, lineage, matrix, or registry mismatches fail closed.
- Registry imports require a trusted key unless an explicit untrusted override is supplied.

## Evidence limits

Checksums prove byte consistency. Ed25519 signatures prove possession of one provenance private key. Neither proves market-data truth, legal identity, realized profitability, or future performance.

## Reporting

Report security defects privately to the repository owner with the affected commit and a minimal synthetic reproduction. Do not include real credentials or private keys.
