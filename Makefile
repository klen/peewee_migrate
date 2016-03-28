VIRTUALENV=$(shell echo "$${VIRTUALENV:-'.env'}")

all: $(VIRTUALENV)

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
release:
	@pip install bumpversion
	@bumpversion $(VERSION)
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
upload: clean
	@pip install twine wheel
	@python setup.py sdist upload
	@python setup.py bdist_wheel upload

# =============
#  Development
# =============

$(VIRTUALENV): requirements.txt
	@[ -d $(VIRTUALENV) ] || virtualenv --no-site-packages $(VIRTUALENV)
	@$(VIRTUALENV)/bin/pip install -r requirements.txt
	@touch $(VIRTUALENV)

.PHONY: test
# target: test - Runs tests
test: clean $(VIRTUALENV)/bin/py.test
	@py.test -xs tests

$(VIRTUALENV)/bin/py.test: $(VIRTUALENV) requirements-tests.txt
	@$(VIRTUALENV)/bin/pip install -r $(CURDIR)/requirements-tests.txt
	@touch $(VIRTUALENV)/bin/py.test

.PHONY: t
t: test
