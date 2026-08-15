<!-- i18n-key: README; locale: zh-TW; reviewed: 2026-08-15 -->
[English](README.md) · [繁體中文](README.zh-TW.md)

# LLM Arbitrage System

[![CI](https://github.com/ed3c/llm_arbitrage_system/actions/workflows/ci.yml/badge.svg)](https://github.com/ed3c/llm_arbitrage_system/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10–3.13](https://img.shields.io/badge/Python-3.10%E2%80%933.13-blue.svg)](pyproject.toml)

**用於 Strategy replay、Risk-gated execution simulation、Reproducible experiment 與 Evidence-bound evaluation 的確定性 Paper-only research harness。**

> **成熟度：** Research software。本 Repository 不連接 Exchange、Broker、Wallet、Deposit、Withdrawal、Live market WebSocket 或 Order endpoint，也不證明 Profitability、Financial suitability 或 Trading authority。

## 為什麼需要這個專案

市場研究 Prototype 常把 Strategy logic、Risk decision、Simulated fill、Performance report、Model selection 與 Deployment claim 混在一起。這會讓 Failure 難以重現，也可能讓看似成功的結果掩蓋薄弱 Lineage 或不安全 Assumption。

LLM Arbitrage System 將責任拆成 Typed State Machines 與 Durable evidence：

```text
offline market events
→ adaptive analytics
→ paper strategy proposal
→ risk and capacity approval
→ deterministic simulated execution
→ append-only replay evidence
→ reproducible experiment bundle
→ trusted out-of-sample evaluation
→ valuation and selection diagnostics
→ independent human review
```

後續 Phase 只能增加 Evidence，不會取得 Trading、Release 或 Deployment authority。

## 核心能力

| Area | `main` 已實作內容 |
|---|---|
| Domain contracts | Immutable typed event、Plan、Approval、Fill、Report、Timezone-aware timestamp 與 Exact decimal value |
| Analytics | Kaufman efficiency ratio、KAMA、Rolling Z-score、ATR percentage 與 Kalman filtering |
| Strategy routing | Funding carry、Overcrowding reversion 與 RWA lead-lag 的 Offline paper scenarios |
| Risk control | Freshness、Edge、Notional、Exposure、Duplicate、Balance 與 Slippage gate |
| Simulation | Bounded queue orchestration、Deterministic concurrent fill、Failure injection、Compensation 與 Residual-risk handling |
| Evidence | Append-only SQLite lifecycle、Event、Decision、Risk check、Result、Report 與 Integrity check |
| Experiments | Strict JSONL／YAML input、Semantic ID、Content-addressed bundle、Sweep、Walk-forward plan 與 Replay verification |
| Trust and evaluation | Ed25519 attestation、Lineage DAG、Trusted local registry、Out-of-sample evaluation 與 Coverage aggregation |
| Governance | Resumable campaign、Terminal valuation、Selection diagnostic 與 Signed independent-review record |

精確的 Merged、Open、Planned 與 Blocked 狀態維護於 [`docs/integration-status.md`](docs/integration-status.md)。Open Pull Request 在合併前不屬於 `main` 的 Supported capability。

## 架構

```mermaid
flowchart LR
    A[Offline JSONL market events] --> B[Typed dataset validation]
    B --> C[Adaptive analytics]
    C --> D[Paper strategy router]
    D --> E[Risk and capacity approval]
    E -->|rejected| J[(Replay journal)]
    E -->|approved| F[Deterministic paper executor]
    F --> G[Compensation / reconciliation]
    G --> J
    J --> H[Experiment bundle + verification]
    H --> I[Trusted OOS registry]
    I --> K[Valuation + selection diagnostics]
    K --> L[Independent human review]
```

Transition ownership 與 Failure behavior 請閱讀 [`docs/architecture.md`](docs/architecture.md)、[`docs/state-machines.md`](docs/state-machines.md) 與 [`docs/data-flow.md`](docs/data-flow.md)。

## Quick start

### Requirements

- Python 3.10–3.13
- Git
- Deterministic local path 不需要 Exchange、Broker、Wallet 或 Model-provider credential

```bash
git clone https://github.com/ed3c/llm_arbitrage_system.git
cd llm_arbitrage_system

python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

llm-arbitrage --help
make check
```

執行 Phase 3 Deterministic experiment smoke：

```bash
make phase3-smoke
```

其他 Offline gate：

```bash
make phase4-smoke
make phase5-smoke
make phase6-smoke
make phase7-smoke
make phase8-smoke
```

這些命令只證明 Local fixture 所捕捉的行為與 Evidence，不證明 Live market data quality、Independent cohort construction、Causal alpha、Future return、Release readiness 或 Trading safety。

## Evidence model

Repository 明確分離以下 Claim：

```text
code exists
!= command is reachable
!= deterministic test passed
!= hosted CI passed
!= evidence bundle verified
!= trusted OOS evaluation passed
!= independent review approved
!= release authorized
!= live trading authorized
```

相關 Phase 會綁定 Identifier、Source hash、Configuration hash、Code revision、Package version、Signer identity 與 Parent lineage。缺少或衝突的 Evidence 採 Fail closed。

## Repository map

```text
src/llm_arbitrage_system/
├── domain/          immutable contracts
├── analytics/       adaptive market features
├── simulation/      strategy, approval, execution, orchestration
├── storage/         append-only SQLite replay journal
├── reporting/       evidence-bounded performance reports
└── experiments/     bundles, trust, OOS, campaigns, valuation and review

examples/            deterministic inputs and policies
tests/               positive, negative, tamper and recovery coverage
scripts/             offline smoke and delivery helpers
docs/                architecture, state, evidence and integration ledgers
```

## 文件

- [文件索引](docs/README.zh-TW.md)
- [目前整合狀態](docs/integration-status.md)
- [Architecture](docs/architecture.md)
- [State Machines](docs/state-machines.md)
- [Data flow](docs/data-flow.md)
- [Replay evidence](docs/replay-evidence.md)
- [Experiment contract](docs/phase3-experiments.md)
- [Trust and OOS registry](docs/phase4-trust-registry.md)
- [Campaigns、Valuation、Selection 與 Review](docs/phase5-campaigns.md)
- [文件語言政策](docs/I18N.zh-TW.md)
- [Open-source readiness checklist](docs/OPEN_SOURCE_CHECKLIST.zh-TW.md)

## 安全與負責任使用

- 唯一支援的 Execution mode 是 Paper execution。
- 本 Repository 不得加入 Credential、Account、Wallet、Deposit、Withdrawal 或 External order route。
- Generated metric 必須標示 Data、Configuration、Code、Runtime 與 Evidence limitation。
- Backtest 或 OOS evidence 不得描述為 Realized profit 或 Future profit。
- Legal、Financial、Operational、Release、Deployment 與 Trading decision 仍由 Human 負責。

漏洞請透過 [SECURITY.zh-TW.md](SECURITY.zh-TW.md) 私下回報。

## 參與與治理

修改 Code 或 Evidence semantics 前先閱讀 [CONTRIBUTING.zh-TW.md](CONTRIBUTING.zh-TW.md)。Public support boundary 見 [SUPPORT.zh-TW.md](SUPPORT.zh-TW.md)，Decision authority 見 [GOVERNANCE.zh-TW.md](GOVERNANCE.zh-TW.md)，Maintainer 見 [MAINTAINERS.zh-TW.md](MAINTAINERS.zh-TW.md)。

## License

本專案使用 [MIT License](LICENSE)。此 License 不授予 Third-party data、Market feed、Document、Trademark 或 Service 的權利。
