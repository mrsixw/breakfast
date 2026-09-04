.ONESHELL:
SHELL = /bin/bash

SHELL_SOURCES := install.sh $(wildcard utils/*.sh) \
	tests/bats/helpers/common.bash tests/bats/helpers/fake_gh

PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin
DESTDIR ?=

.PHONY: activate build version-bump release breakfast smoketest test e2e e2e-ci bats lint docs-lint shellcheck format man completions install uninstall

.venv:
	uv venv .venv
	uv sync --extra dev

activate: .venv
	. .venv/bin/activate

build: .venv

	uv sync --extra build
	uv run shiv -c breakfast -o breakfast --python '/usr/bin/env python3' --preamble utils/preamble.py .

install: build
	install -d "$(DESTDIR)$(BINDIR)"
	install -m 755 breakfast "$(DESTDIR)$(BINDIR)/breakfast"

uninstall:
	rm -f "$(DESTDIR)$(BINDIR)/breakfast"

version-bump:
	git mkver patch

release: build

breakfast: build

smoketest: breakfast .venv
	. .venv/bin/activate && ./breakfast --version

demo: breakfast .venv
	PATH="$(shell pwd):$$PATH" vhs utils/vhs/demo.tape

test: .venv
	uv sync --extra test
	uv run pytest -v

# End-to-end: drives the built zipapp as a subprocess. Builds first so the
# binary under test is always current. Live scenarios need GH_TOKEN.
e2e: build
	uv sync --extra test
	BREAKFAST_E2E_REQUIRE=1 uv run pytest -v -m e2e tests/e2e

# CI variant: deliberately does NOT depend on build, so it runs against the
# artifact downloaded from the build job — the same bits the release ships.
# Both REQUIRE flags turn "no binary" and "no token" into failures, not skips,
# so the suite cannot silently rot to green.
e2e-ci: .venv
	uv sync --extra test
	BREAKFAST_E2E_REQUIRE=1 BREAKFAST_E2E_REQUIRE_LIVE=1 \
		uv run pytest -v -m e2e tests/e2e

lint: .venv docs-lint shellcheck
	uv sync --extra lint
	uv run ruff check .
	uv run black --check .

docs-lint:
	npx --yes markdownlint-cli2 "docs/**/*.md" "README.md" "CONTRIBUTING.md"

# Static analysis for every shell script we ship, plus the test helpers, which
# are shell too and just as capable of being wrong.
shellcheck:
	npx --yes shellcheck $(SHELL_SOURCES)

# The shell test suite. bats and shellcheck both arrive via npx, exactly as
# markdownlint-cli2 does above — nothing to install by hand.
bats:
	npx --yes bats tests/bats

format: .venv
	uv sync --extra lint
	uv run ruff check --fix .
	uv run black .

man: .venv
	uv sync --extra build
	mkdir -p man1
	uv run python utils/generate_man_page.py man1
	gzip -f man1/breakfast.1

completions: .venv
	uv sync
	mkdir -p completions
	_BREAKFAST_COMPLETE=bash_source uv run breakfast > completions/breakfast.bash
	sed -i.bak 's/_BREAKFAST_COMPLETE=bash_complete $$1)/_BREAKFAST_COMPLETE=bash_complete "$$1")/' completions/breakfast.bash
	sed -i.bak 's/COMPREPLY+=($$value)/COMPREPLY+=("$$value")/' completions/breakfast.bash
	rm -f completions/breakfast.bash.bak
	_BREAKFAST_COMPLETE=zsh_source uv run breakfast > completions/_breakfast
	_BREAKFAST_COMPLETE=fish_source uv run breakfast > completions/breakfast.fish

