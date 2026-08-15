<!-- i18n-key: DOCS_INDEX; locale: zh-TW; reviewed: 2026-08-15 -->
[English](README.md) · [繁體中文](README.zh-TW.md)

# LLM Arbitrage System 文件

先閱讀 [專案 README](../README.zh-TW.md)。其中說明支援的 Entrypoint、目前成熟度、Evidence boundary、Quick start 與 Non-goals。

## 技術文件

- [Integration status](integration-status.md) — Merged、Open、Planned 與 Blocked capability ledger。
- [Architecture](architecture.md) — Component boundary 與 System structure。
- [State Machines](state-machines.md) — Runtime 與 Experiment transition。
- [Data flow](data-flow.md) — Input、Output、Evidence 與 Ownership。
- [Replay evidence](replay-evidence.md) — Append-only replay 與 Integrity model。
- [Phase 3 experiments](phase3-experiments.md) — Experiment bundle 與 Sweep contract。
- [Phase 4 trust registry](phase4-trust-registry.md) — Trusted OOS registry 與 Lineage。
- [Phase 5 campaigns](phase5-campaigns.md) — Resumable campaign execution。
- [Phase 6 valuation](phase6-valuation.md) — Valuation 與 Decision evidence。
- [Phase 7 selection governance](phase7-selection-governance.md) — Selection diagnostic 與 Authority boundary。
- [Phase 8 separation of duties](phase8-separation-of-duties.md) — Independent review 與 Signer separation。
- [Git delivery](git/README.md) — Stack、Admission、Worker 與 Publication contract。

## 專案與社群文件

- [文件語言政策](I18N.zh-TW.md)
- [Open-source readiness checklist](OPEN_SOURCE_CHECKLIST.zh-TW.md)
- [參與貢獻](../CONTRIBUTING.zh-TW.md)
- [安全政策](../SECURITY.zh-TW.md)
- [支援](../SUPPORT.zh-TW.md)
- [治理](../GOVERNANCE.zh-TW.md)
- [Maintainers](../MAINTAINERS.zh-TW.md)
- [行為準則](../CODE_OF_CONDUCT.zh-TW.md)
- [變更紀錄](../CHANGELOG.zh-TW.md)
- [Release process](../RELEASING.zh-TW.md)

## Source of truth 順序

文件不一致時，依下列順序判定：

```text
已合併 Code 與 Repository policy
> 目前 Machine-readable contracts 與 Tests
> 目前 Implementation/status ledger
> Architecture 與 Runbooks
> README summaries
> Issues、Pull Requests 與 Conversational summaries
```

Open Pull Request、Configured workflow、Example、Fixture、Generated report 或 Signed receipt，都不能單獨提升 `main` 的 Implementation 或 Verification state。
