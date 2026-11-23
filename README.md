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

## Command line

A migration is a plain Python file with a `migrate()` function. The router keeps
track of applied migrations in a database table and runs each file in its own
transaction. The command line is the usual way to drive it.

Installation puts `pw_migrate` on the path, with `pw-migrate` as an alias.
`python -m peewee_migrate` runs the same commands.

```console
$ pw_migrate --help
Usage: pw_migrate [OPTIONS] COMMAND [ARGS]...

  Migrate database with Peewee ORM.

Options:
  --help  Show this message and exit.

Commands:
  create    Create a migration.
  list      List migrations.
  merge     Merge migrations into one.
  migrate   Migrate database.
  rollback  Rollback migrations.
```

Every command takes the same connection options:

| Option | Default | Meaning |
| --- | --- | --- |
| `--database URL` | none | Database to migrate, e.g. `postgresql://user:pass@host/db`, `sqlite:///app.db`, `mysql://user:pass@host/db`. Required unless `conf.py` provides `DATABASE`. |
| `--directory PATH` | `migrations` | Where migration files live and are looked up. |
| `--migratetable NAME` | `migratehistory` | Table that records applied migrations. |
| `-v` | warnings only | Increase log verbosity: `-v` info, `-vv` debug, `-vvv` everything. |

A `conf.py` inside the migrations directory can set `DATABASE`, `SCHEMA`,
`MIGRATE_TABLE`, `IGNORE` and `LOGGING_LEVEL`; those values win over the flags.
See [The migrations directory](#the-migrations-directory).

Run `pw_migrate COMMAND --help` for the exact options of one command.

### Creating a migration

```console
$ pw_migrate create --database=sqlite:///app.db add_user
$ ls migrations
001_add_user.py
```

The new file has an empty `migrate()` and `rollback()` for you to fill in. Add
`--auto` to generate the operations from your models instead:

```console
$ pw_migrate create --database=sqlite:///app.db --auto add_user
$ pw_migrate create --database=sqlite:///app.db --auto --auto-source=myapp.models add_user
```

`--auto` replays the migrations applied so far, diffs that schema against the
models it can import, and writes the resulting operations. With no
`--auto-source`, the current directory is scanned recursively for packages;
`--auto-source` points at one module path. Tables listed in `IGNORE` are skipped.
When there is nothing to change, no file is written and the command says
`No changes found.`

### Applying migrations

```console
$ pw_migrate migrate --database=postgresql://user:pass@localhost/app
Migrating app
- [x] 001_add_user
- [x] 002_add_email
OK
```

`--name NAME` stops after that migration, which has to be pending:

```console
$ pw_migrate migrate --database=postgresql://user:pass@localhost/app --name=001_add_user
```

`--fake` writes the history rows without executing the migration SQL. Use it for
a schema that already exists, so the files are not applied twice.

### Rolling back

```console
$ pw_migrate rollback --database=postgresql://user:pass@localhost/app
$ pw_migrate rollback --database=postgresql://user:pass@localhost/app --count=3
```

The first undoes the last migration, the second the last three.

Only `rollback()` from the migration file is executed, so a file without one is
undone by dropping its history row alone. Asking for more migrations than are
applied is an error, not a partial rollback.

### Listing migrations

```console
$ pw_migrate list --database=postgresql://user:pass@localhost/app
List of migrations:

- [x] 001_add_user
- [ ] 002_add_email

Done: 1, Pending: 1
```

`[x]` is recorded in the history table, `[ ]` is still waiting on disk.

### Merging migrations

```console
$ pw_migrate merge --database=postgresql://user:pass@localhost/app
```

Squashes the whole history into one `001_initial.py` built from the current
schema and drops the old files. The history table has to match the files, so run
`migrate` first.

Do you want Flask integration? Look at [Flask-PW](https://github.com/klen/flask-pw).

## From Python

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
kept in a Python module instead of a directory. Anything the CLI does is these
calls, so scripts and tests can drive the same flow without a shell.

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
