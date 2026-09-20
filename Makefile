PYTHON ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: test preview help
test:
	$(PYTHON) -B -m unittest discover -s tests -v

preview:
	$(PYTHON) -B main_ingest.py

help:
	$(PYTHON) -B -m agent_learning
