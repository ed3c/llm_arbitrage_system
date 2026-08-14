# Phase 4 data flow

```text
bundle -> sign -> verify -> trust allowlist -> registry import
source lineage -> parent DAG validation -> registry lineage node
matrix evaluation -> test-slice replay -> evaluation.json -> signed bundle -> registry registration
registry evaluations -> coverage aggregation -> no automatic winner
```

Failures in signature, lineage, trust, matrix binding, SQLite integrity, or immutable identity stop registration.
