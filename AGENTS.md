# Agent instructions

## Current phase

This branch is the paper-first contracts and analytics foundation. Preserve the typed pipeline boundary and keep every module credential-free.

## Commands

```bash
python -m pip install -e ".[dev]"
make check
```

## Required invariants

- Use timezone-aware timestamps and `Decimal` for prices, amounts, and limits.
- Do not add private keys, API secrets, seed phrases, withdrawal functions, or live order endpoints.
- Keep domain contracts immutable.
- Add deterministic tests for every analytics or state transition change.
- Treat the future strategy, approval, and execution layers as separate modules rather than bypassing their boundaries.
