.ONESHELL:
SHELL = /bin/bash

.venv:
	python3 -m venv .venv
	. .venv/bin/activate
	pip install -r requirements.txt

activate: .venv
	. .venv/bin/activate

build: activate
	shiv -c breakfast -o breakfast .

breakfast: build

smoketest: breakfast
	./breakfast --version
