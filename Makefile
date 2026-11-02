PYTHON ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: api preview help
api:
	$(PYTHON) -B main_api.py

preview:
	$(PYTHON) -B main_ingest.py

help:
	$(PYTHON) -B -m agent_learning
