PYTHON ?= python

.PHONY: install lint typecheck test phase3-smoke phase4-smoke phase5-smoke phase6-smoke phase7-smoke phase8-smoke phase9-smoke check

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest --cov=llm_arbitrage_system --cov-report=term-missing --cov-fail-under=70

phase3-smoke:
	rm -rf .phase3-runs
	llm-arbitrage validate-dataset examples/phase3/market_events.jsonl
	llm-arbitrage validate-config examples/phase3/experiment.yaml
	llm-arbitrage run --dataset examples/phase3/market_events.jsonl --config examples/phase3/experiment.yaml --output .phase3-runs --code-revision phase3-smoke
	bundle=$$(find .phase3-runs -mindepth 1 -maxdepth 1 -type d -name 'exp-*' -print -quit); test -n "$$bundle"; llm-arbitrage verify "$$bundle"
	llm-arbitrage plan-matrix --dataset examples/phase3/market_events.jsonl --config examples/phase3/experiment.yaml --sweep examples/phase3/sweep.yaml --output .phase3-runs/matrix.json

phase4-smoke:
	bash scripts/phase4_smoke.sh

phase5-smoke:
	bash scripts/phase5_smoke.sh

phase6-smoke:
	bash scripts/phase6_smoke.sh

phase7-smoke:
	bash scripts/phase7_smoke.sh

phase8-smoke:
	bash scripts/phase8_smoke.sh

phase9-smoke:
	bash scripts/phase9_smoke.sh

check: lint typecheck test
