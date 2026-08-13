# Contributing

Keep Phase 1 changes inside the typed foundation: domain contracts, configuration, analytics, storage interfaces, and deterministic paper simulation.

Before opening a pull request:

```bash
python -m pip install -e ".[dev]"
make check
```

Do not commit secrets or introduce live venue connectivity in this phase. New analytics require deterministic unit tests and documented warm-up behavior. Changes to event or result contracts must remain immutable and backward-compatible unless an ADR records the migration.
