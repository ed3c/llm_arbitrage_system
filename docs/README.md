<!-- i18n-key: DOCS_INDEX; locale: en; reviewed: 2026-08-15 -->
[English](README.md) · [繁體中文](README.zh-TW.md)

# LLM Arbitrage System documentation

Start with the [project README](../README.md). It explains the supported entrypoints, current maturity, evidence boundaries, quick start, and non-goals.

## Technical documentation

- [Integration status](integration-status.md) — Merged, open, planned, and blocked capability ledger.
- [Architecture](architecture.md) — Component boundaries and system structure.
- [State Machines](state-machines.md) — Runtime and experiment transitions.
- [Data flow](data-flow.md) — Inputs, outputs, evidence, and ownership.
- [Replay evidence](replay-evidence.md) — Append-only replay and integrity model.
- [Phase 3 experiments](phase3-experiments.md) — Experiment bundle and sweep contract.
- [Phase 4 trust registry](phase4-trust-registry.md) — Trusted OOS registry and lineage.
- [Phase 5 campaigns](phase5-campaigns.md) — Resumable campaign execution.
- [Phase 6 valuation](phase6-valuation.md) — Valuation and decision evidence.
- [Phase 7 selection governance](phase7-selection-governance.md) — Selection diagnostics and authority boundaries.
- [Phase 8 separation of duties](phase8-separation-of-duties.md) — Independent review and signer separation.
- [Git delivery](git/README.md) — Stack, admission, worker, and publication contracts.

## Project and community documentation

- [Documentation language policy](I18N.md)
- [Open-source readiness checklist](OPEN_SOURCE_CHECKLIST.md)
- [Contributing](../CONTRIBUTING.md)
- [Security](../SECURITY.md)
- [Support](../SUPPORT.md)
- [Governance](../GOVERNANCE.md)
- [Maintainers](../MAINTAINERS.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)
- [Changelog](../CHANGELOG.md)
- [Release process](../RELEASING.md)

## Source-of-truth order

When documents disagree, use this order:

```text
merged code and repository policy
> current machine-readable contracts and tests
> current implementation/status ledger
> architecture and runbooks
> README summaries
> Issues, Pull Requests, and conversational summaries
```

An open Pull Request, configured workflow, example, fixture, generated report, or signed receipt cannot upgrade the implementation or verification state of `main` by itself.
