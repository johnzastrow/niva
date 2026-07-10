# TEMPLATE — copy to a QGIS plugin repo root as `Makefile`.
# Portable dev & release tasks. Plugin-specific bits live in scripts/build_plugin.sh, so this is
# (nearly) identical across plugins — the ONLY thing to change is UNIT_TEST below.
# Requires: uv, zip, git, gh.   Run `make help`.  See ../publishing-qgis-plugins.md for the full guide.
SHELL := /bin/bash
BANDIT_EXCLUDE := ./test,./tests,./help,./docs,./.git
UNIT_TEST      := test/test_something_unit.py   # <- CHANGE ME: the pure-Python test(s) CI runs ("" to skip)

.DEFAULT_GOAL := help
.PHONY: help check lint bandit secrets security test build strings clean tag

help:            ## list targets
	@grep -hE '^[a-z][a-z-]*:.*##' $(MAKEFILE_LIST) | sed -E 's/:[^#]*##/\t/' | sort | expand -t18

check: lint bandit secrets test  ## run EVERY publish gate (ruff+flake8, bandit, secrets, tests)

lint:            ## ruff (fast) then flake8 (authoritative pre-publish check)
	uv run --no-project --with ruff ruff check .
	uv run --no-project --with flake8 flake8 .

bandit:          ## security scan — fails on HIGH/MEDIUM (blocks plugins.qgis.org)
	uv run --no-project --with bandit bandit -r . -x $(BANDIT_EXCLUDE) -ll

secrets:         ## detect-secrets — fails if any secret is found
	@uv run --no-project --with detect-secrets detect-secrets scan \
	  | uv run --no-project python -c "import sys,json; r=json.load(sys.stdin).get('results',{}); print('secrets:', 'clean' if not r else 'FOUND '+str(list(r))); sys.exit(1 if r else 0)"

security: bandit secrets  ## bandit + secrets only

test:            ## run the pure-Python unit test(s) that CI runs
	uv run --no-project --with pytest python -m pytest $(UNIT_TEST) -q

build:           ## build the upload zip (self-verifying — includes subpackages + LICENSE)
	bash scripts/build_plugin.sh

strings:         ## compile i18n .ts -> .qm (if the plugin has translations)
	@[ -x scripts/compile-strings.sh ] && bash scripts/compile-strings.sh || echo "no scripts/compile-strings.sh — skipping"

clean:           ## remove caches + built artefacts
	rm -rf .ruff_cache **/__pycache__ __pycache__ *.zip resources.py

tag:             ## tag + push a release, e.g. `make tag V=1.2.3` (CI builds the zip + GitHub Release)
	@test -n "$(V)" || { echo "usage: make tag V=x.y.z"; exit 1; }
	@git diff --quiet || { echo "working tree dirty — commit first"; exit 1; }
	git tag -a v$(V) -m "v$(V)" && git push origin v$(V)
