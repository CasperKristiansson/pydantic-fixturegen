PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PFG := $(BIN)/pfg
NOW ?= 2025-01-01T00:00:00Z

.PHONY: install
install: $(BIN)/python

$(BIN)/python:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ../../..[all-dev]
	$(BIN)/pip install -e .

.PHONY: datasets
datasets: install
	$(PFG) gen json models/segments.py \
	  --include models.segments.SegmentSnapshot \
	  --out samples/segments.jsonl \
	  --jsonl --n 3 \
	  --seed 4142 --freeze-seeds \
	  --now $(NOW)

.PHONY: strategies
strategies: install
	$(PFG) gen strategies models/segments.py \
	  --include models.segments.SegmentSnapshot \
	  --out samples/segments_strategies.py \
	  --seed 4142 --freeze-seeds \
	  --now $(NOW)
