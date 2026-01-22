.ONESHELL:
SHELL = /bin/bash

.venv:
	uv venv .venv
	uv sync --extra dev

activate: .venv
	. .venv/bin/activate

build: activate
	uv run shiv -c breakfast -o breakfast .

version-bump:
	git mkver patch

release: build

breakfast: build

smoketest: breakfast
	./breakfast --version

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
