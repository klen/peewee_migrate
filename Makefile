VIRTUAL_ENV	?= .venv
PACKAGE = peewee_migrate

all: $(VIRTUAL_ENV)

# =============
#  Development
# =============
#
.PHONY: clean
# target: clean - Display callable targets
clean:
	rm -rf build/ dist/ docs/_build *.egg-info
	find $(CURDIR) -name "*.py[co]" -delete
	find $(CURDIR) -name "*.orig" -delete
	find $(CURDIR)/$(MODULE) -name "__pycache__" | xargs rm -rf

$(VIRTUAL_ENV): pyproject.toml .pre-commit-config.yaml
	@uv sync
	@uv run pre-commit install
	@touch $(VIRTUAL_ENV)

.PHONY: t test
# target: test - Runs tests
t test: $(VIRTUAL_ENV)
	@uv run pytest -xsv tests

.PHONY: types
# target: types - Check typing
types: $(VIRTUAL_ENV)
	@echo 'Checking typing...'
	@uv run pyrefly check

.PHONY: lint
# target: lint - Check code
lint: $(VIRTUAL_ENV)
	@make types
	@uv run ruff check

outdated:
	@echo "Checking for outdated dependencies..."
	@uv tree --depth 1 --outdated | grep 'latest' || echo "All dependencies are up to date."

# ==============
#  Bump version
# ==============

VERSION	?= minor
MAIN_BRANCH = master
STAGE_BRANCH = develop

.PHONY: release
VPART?=minor
# target: release - Bump version
release:
	git checkout $(MAIN_BRANCH)
	git pull
	git checkout $(STAGE_BRANCH)
	git pull
	uvx bump-my-version bump $(VPART)
	uv lock
	@VERSION="$$(uv version --short)"; \
		{ \
			printf 'build(release): %s\n\n' "$$VERSION"; \
			printf 'Changes:\n\n'; \
			git log --oneline --pretty=format:'%s [%an]' $(MAIN_BRANCH)..$(STAGE_BRANCH) | grep -Evi 'github|^Merge' || true; \
		} | git commit -a -F -; \
		git tag -a "$$VERSION" -m "$$VERSION";
	git checkout $(MAIN_BRANCH)
	git merge $(STAGE_BRANCH)
	git checkout $(STAGE_BRANCH)
	git merge $(MAIN_BRANCH)
	@git -c push.followTags=false push origin $(STAGE_BRANCH) $(MAIN_BRANCH)
	@git push --tags origin
	@echo "Release process complete for `uv version --short`"

.PHONY: minor
minor: release

.PHONY: patch
patch:
	make release VPART=patch

.PHONY: major
major:
	make release VPART=major

version v:
	uv version --short
