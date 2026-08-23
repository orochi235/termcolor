.PHONY: color-names test

# Prefer the repo's virtualenv when it exists; CI installs pytest for python3.
PYTHON := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

color-names:
	python3 scripts/generate-names.py

test:
	bats test/
	$(PYTHON) -m pytest
