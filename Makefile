VIRTUAL_ENV	?= .venv
PACKAGE = peewee_migrate

all: $(VIRTUAL_ENV)

# =============
#  Development
# =============

$(VIRTUAL_ENV): pyproject.toml .pre-commit-config.yaml
	@poetry install --with dev
	@poetry run pre-commit install
	@touch $(VIRTUAL_ENV)

.PHONY: t test
# target: test - Runs tests
t test: $(VIRTUAL_ENV)
	@poetry run pytest -xsv --mypy tests

lint: $(VIRTUAL_ENV)
	@poetry run mypy
	@poetry run ruff $(PACKAGE)

v:
	@poetry version -s

# ==============
#  Bump version
# ==============

.PHONY: release
VERSION?=minor
# target: release - Bump version
release: $(VIRTUAL_ENV)
	@poetry version $(VERSION)
	@git commit -am "build(release): `poetry version -s`"
	@git tag `poetry version -s`
	@git checkout master
	@git merge develop
	@git checkout develop
	@git push origin develop master
	@git push --tags

.PHONY: minor
minor: release

.PHONY: patch
patch:
	make release VERSION=patch

.PHONY: major
major:
	make release VERSION=major
