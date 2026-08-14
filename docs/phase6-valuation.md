# Phase 6 — Evidence-grade terminal valuation and OOS statistics

Phase 6 adds an explicit valuation plane to the offline paper research system. It does not infer profit from execution settlement cash. A verified evaluation bundle becomes valuatable only when the caller supplies strict terminal marks for every non-zero open position.

## Source and extension boundary

The supplied design includes backtest reporting for Sharpe ratio, maximum drawdown, and alpha decay after the market-data → analytics → strategy → risk → execution flow. Earlier phases correctly left those fields unset because fills and settlement cash do not supply an equity curve or terminal market value. Phase 6 adds the missing evidence contracts; it does not add live market access.

## Directory ownership

```text
src/llm_arbitrage_system/experiments/
├── valuation.py            strict marks and one verified-bundle terminal valuation
├── oos_statistics.py       chronological trusted window aggregation
├── statistics_inputs.py    strict operational candidate/evaluation input manifest
└── statistics_signing.py   detached Ed25519 statistics-report attestation

examples/phase6/
└── terminal_marks.json     strict mark-snapshot example

scripts/
└── phase6_smoke.sh         deterministic end-to-end verification path
```

## Valuation state machine

```text
verified evidence bundle + strict terminal marks
  -> bundle exact-file/checksum/SQLite verification
  -> marks duplicate-key/schema/time/Decimal validation
  -> terminal as_of >= dataset last event
  -> deterministic fill accounting
       fills + compensated_fills
       buy  = negative settlement cash + positive quantity
       sell = positive settlement cash + negative quantity
       fees = separate evidence and settlement deduction
  -> exact mark coverage for all and only non-zero positions
  -> terminal market value
  -> mark-to-market PnL = settlement cash + terminal market value
  -> content-addressed valuation report
```

The valuation ID binds:

```text
experiment ID
run ID
bundle-root SHA-256
terminal-marks semantic SHA-256
valuation policy
code revision
package version
```

The policy explicitly excludes funding accrual, borrow and margin costs, liquidation mechanics, corporate actions, and intraperiod valuation. Those exclusions stay visible in the report.

## OOS statistics state machine

```text
Phase 3 matrix
  + trusted Phase 4 registry rows
  + one valuation input per planned evaluation
  + positive initial equity
  + explicit periods per year
  -> exact matrix/candidate/config/train/test/window binding
  -> exact experiment and bundle-root binding
  -> complete candidate evidence requirement
  -> non-overlapping chronological test windows
  -> one comparable terminal-mark lag
  -> independent candidate equity path
  -> maximum drawdown
  -> annualized terminal-window Sharpe when dispersion exists
  -> OLS terminal-PnL slope when at least three windows exist
  -> non-negative alpha-decay magnitude only for a negative slope
  -> content-addressed OOS report
```

The declared alpha-decay method is:

```text
ols_terminal_pnl_bps_per_window
```

It is a descriptive slope over comparable terminal paper PnL observations. It is not causal proof that an alpha exists or will persist.

## Statistics input manifest

`campaign-statistics` accepts one strict JSON input manifest:

```json
{
  "schema_version": 1,
  "candidate_ids": ["candidate-..."],
  "valuations": [
    {
      "evaluation_id": "evaluation-...",
      "bundle": "evaluations/evaluation-.../exp-...",
      "marks": "marks/evaluation-....json"
    }
  ]
}
```

Relative paths resolve from the manifest directory. Candidate and evaluation IDs must be non-empty and unique. Bundle directories and mark files must exist before statistical evaluation begins.

## Operator commands

```bash
llm-arbitrage validate-marks examples/phase6/terminal_marks.json

llm-arbitrage value-bundle \
  --bundle experiment-runs/evaluations/exp-... \
  --marks marks/evaluation-....json \
  --output valuations/evaluation-....json \
  --code-revision "$(git rev-parse HEAD)"

llm-arbitrage validate-statistics-inputs statistics-inputs.json

llm-arbitrage campaign-statistics \
  --registry state/experiments.registry.sqlite3 \
  --matrix experiment-runs/matrix.json \
  --inputs statistics-inputs.json \
  --initial-equity "100000" \
  --periods-per-year 252 \
  --output oos-statistics.json \
  --code-revision "$(git rev-parse HEAD)"

llm-arbitrage sign-statistics \
  --report oos-statistics.json \
  --private-key /secure/provenance.pem \
  --output oos-statistics.attestation.json

llm-arbitrage verify-statistics \
  --report oos-statistics.json \
  --attestation oos-statistics.attestation.json \
  --trusted-public-key /secure/provenance.pub.pem
```

Outputs are overwrite-protected unless an explicit `--force` is supplied.

## Signed statistics report

The detached Ed25519 attestation binds the canonical report SHA-256, report ID, matrix SHA-256, code revision, package version, periods per year, candidate count, signer key ID, and embedded public key. Verification re-parses the report, requires canonical JSON, checks the signature, and optionally requires one exact trusted public key.

A valid signature proves possession of one provenance private key over captured report bytes. It does not establish the legal identity of the signer, market-data truth, mark-source truth, causal alpha, realized live profit, future returns, or production safety.

## Statistical availability rules

```text
maximum drawdown
  requires: explicit initial equity + complete chronological terminal PnL series

annualized Sharpe
  requires: at least two comparable returns + non-zero dispersion

alpha decay
  requires: at least three comparable windows + declared OLS method

winner selection
  remains: null / absent
```

Mixed mark lags, overlapping windows, missing evaluations, untrusted registry evidence, wrong bundles, wrong candidate hashes, wrong test hashes, and wrong window indexes fail closed.

## Verification

```bash
make check
make phase3-smoke
make phase4-smoke
make phase5-smoke
make phase6-smoke
```

The Phase 6 smoke path generates synthetic data, executes three non-overlapping matrix-bound test windows, signs and registers each paper bundle, supplies comparable terminal marks, computes valuation and OOS statistics, signs the canonical report, verifies it against the trusted public key, checks that no winner is selected, and removes generated evidence.
