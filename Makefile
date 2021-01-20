VIRTUAL_ENV	?= env

all: $(VIRTUAL_ENV)

.PHONY: help
# target: help - Display callable targets
help:
	@egrep "^# target:" [Mm]akefile

.PHONY: clean
# target: clean - Clean the repository
clean:
	rm -rf build/ dist/ docs/_build *.egg-info
	find $(CURDIR) -name "*.py[co]" -delete
	find $(CURDIR) -name "*.orig" -delete
	find $(CURDIR)/$(MODULE) -name "__pycache__" -delete

# ==============
#  Bump version
# ==============

.PHONY: release
VERSION?=minor
# target: release - Bump version
release: $(VIRTUAL_ENV)
	@bump2version $(VERSION)
	@git checkout master
	@git merge develop
	@git checkout develop
	@git push --all
	@git push --tags

.PHONY: minor
minor: release

.PHONY: patch
patch:
	make release VERSION=patch

.PHONY: major
major:
	make release VERSION=major

# ===============
#  Build package
# ===============

.PHONY: register
# target: register - Register module on PyPi
register:
	@python setup.py register

.PHONY: upload
# target: upload - Upload module on PyPi
upload: clean $(VIRTUAL_ENV)
	@$(VIRTUAL_ENV)/bin/python setup.py sdist bdist_wheel
	@$(VIRTUAL_ENV)/bin/twine upload dist/*.tar.gz || true
	@$(VIRTUAL_ENV)/bin/twine upload dist/*.whl || true
	@$(VIRTUAL_ENV)/bin/pip install -e $(CURDIR)

# =============
#  Development
# =============

$(VIRTUAL_ENV): setup.cfg
	@[ -d $(VIRTUAL_ENV) ] || python -m venv $(VIRTUAL_ENV)
	@$(VIRTUAL_ENV)/bin/pip install -e .[tests,build]
	@touch $(VIRTUAL_ENV)

.PHONY: t test
# target: test - Runs tests
t test: $(VIRTUAL_ENV)
	@$(VIRTUAL_ENV)/bin/pytest tests
