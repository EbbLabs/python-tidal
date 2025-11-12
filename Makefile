.PHONY: lint test install format all develop shell help
POETRY ?= poetry run

help:
	@echo -e "Task runner for python-tidal.  Run make <option> to do something.\n"
	@echo -e "\t\t\tOptions\n"
	@echo -e "develop:\tset up development virtual environment with required deps"
	@echo -e "shell:\t\tstart a shell inside the development environment"
	@echo -e "install:\tbuild package and install system wide (do not run this from within the virtual environment)"
	@echo -e "format:\t\tformat code"
	@echo -e "lint:\t\tlint code"
	@echo -e "test:\t\trun tests: will fail if development environment not already created"

develop:
	poetry install

shell:
	poetry shell

install:
	rm -rf dist
	poetry build
	pip install dist/*.whl --break-system-packages

format:
	${POETRY} isort tidalapi tests
	${POETRY} black tidalapi tests
	${POETRY} docformatter -i tidalapi tests
	# ${POETRY} ruff . # Don't autofix as ruff can break things

lint:
	${POETRY} isort --check tidalapi tests
	${POETRY} black --check tidalapi tests
	${POETRY} docformatter --check tidalapi tests
	# ${POETRY} ruff .


test:
	${POETRY} pytest tests/
