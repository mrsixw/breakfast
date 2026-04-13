.ONESHELL:
SHELL = /bin/bash

.PHONY: activate build version-bump release breakfast smoketest test lint docs-lint format man completions

.venv:
	uv venv .venv
	uv sync --extra dev

activate: .venv
	. .venv/bin/activate

build: .venv

	uv sync --extra build
	uv run shiv -c breakfast -o breakfast --python '/usr/bin/env python3' .

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

lint: .venv docs-lint
	uv sync --extra lint
	uv run ruff check .
	uv run black --check .

docs-lint:
	npx --yes markdownlint-cli2 "docs/**/*.md" "README.md" "CONTRIBUTING.md"

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
	_BREAKFAST_COMPLETE=zsh_source uv run breakfast > completions/_breakfast
	_BREAKFAST_COMPLETE=fish_source uv run breakfast > completions/breakfast.fish
