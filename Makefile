.ONESHELL:
SHELL = /bin/bash

.PHONY: activate build version-bump release breakfast smoketest test lint format

.venv:
	uv venv .venv
	uv sync --extra dev

activate: .venv
	. .venv/bin/activate

build: .venv

	uv sync --extra build
	uv run shiv -c breakfast -o breakfast .

version-bump:
	git mkver patch

release: build

breakfast: build

smoketest: breakfast .venv
	. .venv/bin/activate && ./breakfast --version

demo: breakfast .venv
	export SHIV_INTERPRETER=$$(pwd)/.venv/bin/python3; \
	vhs < utils/vhs/demo.tape

test: .venv
	uv sync --extra test
	uv run pytest -v

lint: .venv
	uv sync --extra lint
	uv run ruff check .
	uv run black --check .

format: .venv
	uv sync --extra lint
	uv run ruff check --fix .
	uv run black .
