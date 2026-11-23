# Peewee Migrate

A simple migration engine for [Peewee](http://docs.peewee-orm.com/en/latest) ORM.

[![Tests](https://github.com/klen/peewee_migrate/workflows/tests/badge.svg)](https://github.com/klen/peewee_migrate/actions/workflows/tests.yml)
[![Release](https://github.com/klen/peewee_migrate/workflows/release/badge.svg)](https://github.com/klen/peewee_migrate/actions/workflows/release.yml)
[![PyPI version](https://img.shields.io/pypi/v/peewee-migrate)](https://pypi.org/project/peewee-migrate/)
[![Python versions](https://img.shields.io/pypi/pyversions/peewee-migrate)](https://pypi.org/project/peewee-migrate/)

## Requirements

Peewee 4.4 or newer, Python 3.11 or newer.

### Dependency note

- For `Peewee<3.0` use `Peewee-Migrate==0.14.0`
- For `Python 3.0-3.6` use `Peewee-Migrate==1.1.6`
- For `Python 3.7` use `Peewee-Migrate==1.6.6`
- For `Python 3.8, 3.9` use `Peewee-Migrate>=1.13.0`
- For `Python 3.11+` use `Peewee-Migrate>=1.14+`

## Installation

```console
pip install peewee-migrate
```

## Usage

A migration is a plain Python file with a `migrate()` function. The router keeps
track of applied migrations in a database table and runs each file in its own
transaction.

### From the shell

The package installs `pw_migrate` (and the `pw-migrate` alias):

- `create NAME` writes a new empty migration file. Add `--auto` to generate it
  from your models instead.
- `migrate` applies everything pending. `--name NAME` stops after that
  migration, `--fake` records migrations as applied without running any SQL.
- `rollback` undoes the last migration; `--count N` undoes the last N.
- `list` shows applied and pending migrations.
- `merge` squashes the whole history into a single `001_initial.py`.

All commands accept `--database` (a URL such as `postgresql://user:pass@host/db`),
`--directory` and `--migratetable`. Run `pw_migrate COMMAND --help` for the exact
option list.

Do you want Flask integration? Look at [Flask-PW](https://github.com/klen/flask-pw).

### From Python

```python
from peewee import SqliteDatabase

from peewee_migrate import Router

router = Router(SqliteDatabase("test.db"))

router.create("add_user")               # empty 001_add_user.py
router.create(auto="myapp.models")      # generated from your model classes
router.run()                            # apply everything pending
router.run("002_add_user")              # apply up to the given migration
router.rollback()                       # undo the last one
router.merge()                          # squash into 001_initial.py

router.todo      # names found on disk
router.done      # names recorded in the database
router.diff      # names still pending
```

`Router` also takes `migrate_dir`, `migrate_table`, `ignore` (table names to skip
when diffing models) and `schema`. `ModuleRouter` does the same for migrations
kept in a Python module instead of a directory.

## The migrations directory

The directory defaults to `migrations` in the current working directory and is
created on first use. Point the CLI at another one with `--directory`, or pass
`migrate_dir` to the router.

Each file is named `NNN_name.py`. Only the number matters: files are applied in
numeric order, and the numbers do not have to be contiguous, so you can leave a
gap and slot a migration between two existing ones later.

A `conf.py` in that directory configures the router:

```python
DATABASE = "postgresql://user:pass@localhost/app"
SCHEMA = "public"
MIGRATE_TABLE = "migratehistory"
IGNORE = ["cache_entry"]
LOGGING_LEVEL = "INFO"
```

Values from `conf.py` win over the command line flags. Errors raised inside it
are not swallowed.

## How it works

Applied migrations are recorded in the `migratehistory` table (rename it with
`--migratetable`). The name is unique there. Each migration runs inside a
transaction and its history row is written in the same transaction, so a
migration that fails leaves neither schema changes nor a history row behind. On
MySQL the DDL part is not covered, see Limitations.

Several processes may start migrating at once. On Postgres the router takes a
`pg_advisory_lock`, on MySQL a `GET_LOCK`, both keyed by the history table, and
the second process waits up to 60 seconds for the first one to finish before it
gives up with an error.

## Migration files

Each file must define `migrate()` and may define `rollback()`:

```python
def migrate(migrator, database, fake=False, **kwargs):
    """Write your migrations here."""
    ...


def rollback(migrator, database, fake=False, **kwargs):
    """Write your rollback migrations here."""
    ...
```

The `migrator` argument carries the operations: `create_model`, `remove_model`,
`add_fields`, `change_fields`, `remove_fields`, `rename_field`, `rename_table`,
`add_index`, `drop_index`, `add_not_null`, `drop_not_null`, `add_default`,
`add_constraint`, `drop_constraints`, plus `sql()` for raw SQL and `run()` for
arbitrary Python. A generated file lists them in its docstring.

`migrator.orm["table_name"]` returns the model as it exists at that point in the
history, which is what data migrations usually need.

A migration without `rollback()` counts as an empty rollback: the command
removes its history row and leaves the schema alone. If you want a real
undoing, write the inverse operations.

A model created with `migrator.create_model()` can only be changed in a later
migration. Create it in one file and alter it in the next one; the same file
would try to add a column that the new table already has.

## Automatic migrations

`create --auto` replays the migrations applied so far, diffs that against the
models it can import, and writes the resulting operations. With no
`--auto-source` the current directory is scanned recursively for packages;
`--auto-source myapp.models` points it at a module instead. Table names listed
in `IGNORE` are skipped.

## Limitations

- Sqlite has no advisory lock, so concurrent processes are not serialised
  there. The unique history name turns a double apply into an error instead of a
  silent duplicate. The constraint is part of newly created history tables; an
  existing `migratehistory` table keeps its old definition.
- MySQL commits DDL implicitly, so a migration that fails halfway can leave
  partial schema changes behind.
- Applied migrations are not checksummed. Editing a file that already ran
  changes nothing in the database and is not reported.
- On Sqlite, changing a column rebuilds the table, which is slow on large
  tables.
- One router serves one database. Two databases in one process means two
  routers, which is supported; sharing a single router between them is not.

## Bug tracker

If you have any suggestions, bug reports or annoyances, please report them at
https://github.com/klen/peewee_migrate/issues.

## Contributing

Development happens at GitHub: https://github.com/klen/peewee_migrate
