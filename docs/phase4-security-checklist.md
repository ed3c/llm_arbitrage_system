# Phase 4 security checklist

- [ ] Private provenance key is outside the repository and evidence bundle.
- [ ] Private-key file mode is `0600`.
- [ ] Bundle verifies before signing.
- [ ] Attestation verifies after signing.
- [ ] Registry signer key is trusted or import explicitly records untrusted status.
- [ ] Referenced lineage exists and its dataset hash matches.
- [ ] Evaluation record matches matrix, candidate configuration, and test slice.
- [ ] Registry SQLite integrity and foreign-key checks pass.
- [ ] Aggregation does not select a winner or invent unsupported metrics.
