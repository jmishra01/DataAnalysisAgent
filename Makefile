UV ?= uv
PYTHON ?= python
CSV ?= data/retail.csv
QUESTION ?= Maximum units sold by product category
SESSION ?= retail-review

.DEFAULT_GOAL := help

.PHONY: help install run run-code test evaluate check compose-config docker-build docker-run

help:
	@printf '%s\n' \
		'CSV Data Analysis Agent' \
		'' \
		'Local commands:' \
		'  make install          Install project dependencies' \
		'  make run              Run one analysis question' \
		'  make run-code         Run and include generated code' \
		'  make test             Run the unit test suite' \
		'  make evaluate         Run representative evaluations' \
		'  make check            Run tests, evaluation, and Compose validation' \
		'' \
		'Docker commands:' \
		'  make compose-config   Validate compose.yaml' \
		'  make docker-build     Build the application image' \
		'  make docker-run       Run one question inside Docker' \
		'' \
		'Optional variables:' \
		"  CSV='data/retail.csv'" \
		"  QUESTION='Compare revenue by city'" \
		"  SESSION='retail-review'"

install:
	$(UV) sync --frozen

run:
	$(UV) run $(PYTHON) cli.py --csv "$(CSV)" --question "$(QUESTION)" --session "$(SESSION)"

run-code:
	$(UV) run $(PYTHON) cli.py --csv "$(CSV)" --question "$(QUESTION)" --session "$(SESSION)" --show-code

test:
	$(UV) run $(PYTHON) -m unittest discover -s tests -v

evaluate:
	$(UV) run $(PYTHON) -m scripts.evaluate

compose-config:
	docker compose -f compose.yaml config --quiet

check: test evaluate compose-config

docker-build:
	docker compose -f compose.yaml build csv-agent

docker-run:
	ANALYSIS_QUESTION="$(QUESTION)" AGENT_SESSION_ID="$(SESSION)" docker compose -f compose.yaml run --rm csv-agent
