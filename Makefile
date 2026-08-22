.PHONY: color-names test

color-names:
	python3 scripts/generate-names.py

test:
	bats test/
