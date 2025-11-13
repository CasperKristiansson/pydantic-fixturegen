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

.PHONY: list
list: install
	$(PFG) list app/models/__init__.py --tree

.PHONY: snapshots
snapshots: install
	$(PFG) gen json app/models/order.py \
	  --include app.models.order.OrderEnvelope \
	  --out snapshots/orders.json \
	  --seed 7337 --freeze-seeds \
	  --now $(NOW) \
	  --n 3 --indent 2
	$(PFG) gen fixtures app/models/order.py \
	  --include app.models.order.OrderEnvelope \
	  --out tests/fixtures/test_orders.py \
	  --style factory --scope session \
	  --cases 3 \
	  --seed 7337 --freeze-seeds \
	  --now $(NOW)

.PHONY: snapshot-verify
snapshot-verify: install
	$(PFG) snapshot verify app/models/order.py \
	  --include app.models.order.OrderEnvelope \
	  --json-out snapshots/orders.json \
	  --seed 7337 --freeze-seeds \
	  --now $(NOW) \
	  || ( $(PFG) snapshot write app/models/order.py \
	        --include app.models.order.OrderEnvelope \
	        --json-out snapshots/orders.json \
	        --seed 7337 --freeze-seeds \
	        --now $(NOW) \
	        && $(PFG) snapshot verify app/models/order.py \
	             --include app.models.order.OrderEnvelope \
	             --json-out snapshots/orders.json \
	             --seed 7337 --freeze-seeds \
	             --now $(NOW) )
	$(PFG) snapshot verify app/models/order.py \
	  --include app.models.order.OrderEnvelope \
	  --fixtures-out tests/fixtures/test_orders.py \
	  --seed 7337 --freeze-seeds \
	  --now $(NOW) \
	  || ( $(PFG) snapshot write app/models/order.py \
	        --include app.models.order.OrderEnvelope \
	        --fixtures-out tests/fixtures/test_orders.py \
	        --seed 7337 --freeze-seeds \
	        --now $(NOW) \
	        && $(PFG) snapshot verify app/models/order.py \
	             --include app.models.order.OrderEnvelope \
	             --fixtures-out tests/fixtures/test_orders.py \
	             --seed 7337 --freeze-seeds \
	             --now $(NOW) )

.PHONY: run-api
run-api: install
	$(BIN)/uvicorn app:build_app --reload

.PHONY: clean
clean:
	rm -rf $(VENV)
