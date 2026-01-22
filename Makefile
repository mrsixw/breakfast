.ONESHELL:
SHELL = /bin/bash

.venv:
	uv venv .venv
	uv sync --extra dev

activate: .venv
	. .venv/bin/activate

build: activate
	git mkver patch
	shiv -c breakfast -o breakfast .

breakfast: build

smoketest: breakfast
	./breakfast --version
