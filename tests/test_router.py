"""Tests for `peewee_migrate` module."""

from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from types import ModuleType
from unittest import mock

import peewee as pw
import pytest
from playhouse.db_url import connect
from playhouse.migrate import MySQLDatabase

from peewee_migrate.cli import get_router
from peewee_migrate.router import ModuleRouter, Router, load_models, lock_migrations, void

from .test_autodiscover.models1 import one_models

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def test_router():
    class Dummy(pw.Model):
        id = pw.AutoField()

    router = get_router(MIGRATIONS_DIR, "sqlite:///:memory:")

    assert router.database
    assert isinstance(router.database, pw.Database)

    assert router.todo == ["001_test", "002_test", "003_tespy"]
    assert router.done == []
    assert router.diff == ["001_test", "002_test", "003_tespy"]

    router.create("new")
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new"]
    (MIGRATIONS_DIR / "004_new.py").unlink()

    router.create("new1", auto=Dummy)
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new1"]
    (MIGRATIONS_DIR / "004_new1.py").unlink()

    router.create("new2", auto=[Dummy])
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new2"]
    (MIGRATIONS_DIR / "004_new2.py").unlink()

    router.create("new3", auto="tests.models")
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new3"]
    (MIGRATIONS_DIR / "004_new3.py").unlink()

    router.create("new4", auto=["tests.models"])
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new4"]
    (MIGRATIONS_DIR / "004_new4.py").unlink()

    history = router.model
    history.create(name="001_test")
    assert router.diff == ["002_test", "003_tespy"]

    history.delete().execute()

    router.run()
    assert router.diff == []

    with mock.patch("peewee.Database.execute_sql") as execute_sql:
        router.run_one("002_test", router.migrator, fake=True)

    assert not execute_sql.called

    migrations = history.select()
    assert list(migrations)
    assert migrations.count() == 3

    router.rollback()
    assert router.diff == ["003_tespy"]
    assert migrations.count() == 2

    with mock.patch("pathlib.Path.unlink") as mocked:
        router.merge()
        assert mocked.call_count == 3
        assert history.select().count() == 1

    (MIGRATIONS_DIR / "001_initial.py").unlink()

    models = load_models("tests.test_autodiscover")
    assert models

    models = load_models("tests.test_autodiscover")
    assert models

    models = load_models(one_models)
    assert models

    models = load_models(one_models)
    assert models


def test_router_compile(tmpdir):
    migrations = tmpdir.mkdir("migrations")
    router = get_router(str(migrations), "sqlite:///:memory:")
    router.compile("test_router_compile")

    with migrations.join("001_test_router_compile.py").open() as f:
        content = f.read()
        assert content


def test_migrations_numbered_above_999(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "999_last.py").write_text(
        "def migrate(migrator, database, **kwargs):\n    pass\n"
    )
    router = get_router(str(migrate_dir), "sqlite:///:memory:")

    assert router.create("next") == "1000_next"
    assert router.todo == ["999_last", "1000_next"]
    assert router.run() == ["999_last", "1000_next"]


def test_migration_number_uses_highest_not_count(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    for name in ("001_a", "003_c"):
        (migrate_dir / f"{name}.py").write_text(
            "def migrate(migrator, database, **kwargs):\n    pass\n"
        )
    router = get_router(str(migrate_dir), "sqlite:///:memory:")

    # Counting files would reuse 003 and produce two migrations with the same number.
    assert router.create("new") == "004_new"


def test_todo_creates_missing_directory(tmp_path, monkeypatch):
    migrate_dir = tmp_path / "migrations"
    router = get_router(str(migrate_dir), "sqlite:///:memory:")
    migrate_dir.mkdir()

    # Another worker creates the directory between our exists() check and mkdir().
    real_exists = Path.exists
    monkeypatch.setattr(
        Path, "exists", lambda self: False if self == migrate_dir else real_exists(self)
    )

    assert router.todo == []


def test_history_names_are_unique(router):
    router.model.create(name="001_a")

    with pytest.raises(pw.IntegrityError):
        router.model.create(name="001_a")


def test_create_then_alter_across_migrations(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "001_create.py").write_text(
        "import peewee as pw\n"
        "def migrate(migrator, database, **kwargs):\n"
        "    class T(pw.Model):\n"
        "        name = pw.CharField()\n"
        "    migrator.create_model(T)\n"
    )
    (migrate_dir / "002_alter.py").write_text(
        "import peewee as pw\n"
        "def migrate(migrator, database, **kwargs):\n"
        "    migrator.add_fields('t', extra=pw.CharField(null=True))\n"
    )
    database = pw.SqliteDatabase(":memory:")

    assert get_router(str(migrate_dir), database).run() == ["001_create", "002_alter"]
    assert "extra" in [column.name for column in database.get_columns("t")]


def test_merge_keeps_state_when_unlink_fails(tmp_path, monkeypatch):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "001_create.py").write_text(
        "import peewee as pw\n"
        "def migrate(migrator, database, **kwargs):\n"
        "    class T(pw.Model):\n"
        "        name = pw.CharField()\n"
        "    migrator.create_model(T)\n"
    )
    router = get_router(str(migrate_dir), pw.SqliteDatabase(":memory:"))
    router.run()

    def deny(self):
        raise PermissionError(self)

    monkeypatch.setattr(Path, "unlink", deny)

    with pytest.raises(PermissionError):
        router.merge()

    # The old history and files must survive a failed merge.
    assert router.done == ["001_create"]
    assert (migrate_dir / "001_create.py").exists()
    assert (migrate_dir / "001_initial.py").exists()


def test_conf_error_propagates(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "conf.py").write_text(
        'MIGRATE_TABLE = "custom_history"\nopen("/nonexistent/app-secrets").read()\n'
    )

    with pytest.raises(OSError, match="app-secrets"):
        get_router(str(migrate_dir), "sqlite:///:memory:")


def test_conf_is_applied(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "conf.py").write_text('MIGRATE_TABLE = "custom_history"\n')

    router = get_router(str(migrate_dir), "sqlite:///:memory:")

    assert router.migrate_table == "custom_history"


@pytest.mark.parametrize("dburl", ["postgres:///fake"])
def test_lock_migrations_postgres(dburl, monkeypatch):
    database = connect(dburl)
    monkeypatch.setattr(database.cursor(), "fetchone", lambda *args: (True,))

    with lock_migrations(database, "migratehistory"):
        pass

    queries = database.cursor().queries
    assert "SELECT pg_try_advisory_lock(%s)" in queries
    assert "SELECT pg_advisory_unlock(%s)" in queries


@pytest.mark.parametrize("dburl", ["postgres:///fake"])
def test_lock_timeout_raises(dburl, monkeypatch):
    monkeypatch.setattr("peewee_migrate.router.LOCK_TIMEOUT", 0)
    database = connect(dburl)

    with (
        pytest.raises(RuntimeError, match="Could not acquire the migration lock"),
        lock_migrations(database, "migratehistory"),
    ):
        pass


def test_run_takes_the_lock(tmp_path, monkeypatch):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "001_a.py").write_text("def migrate(migrator, database, **kwargs):\n    pass\n")
    taken = []

    @contextmanager
    def fake_lock(database, table):
        taken.append(table)
        yield

    monkeypatch.setattr("peewee_migrate.router.lock_migrations", fake_lock)

    get_router(str(migrate_dir), "sqlite:///:memory:").run()

    assert taken == ["migratehistory"]


def test_routers_use_their_own_database(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "001_a.py").write_text("def migrate(migrator, database, **kwargs):\n    pass\n")

    router1 = get_router(str(migrate_dir), pw.SqliteDatabase(":memory:"))
    router2 = get_router(str(migrate_dir), pw.SqliteDatabase(":memory:"))

    assert router1.run() == ["001_a"]
    assert router2.done == []
    assert router1.done == ["001_a"]
    assert router1.model is not router2.model


def test_run_named_migration(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    for name in ("001_a", "002_b", "003_c"):
        (migrate_dir / f"{name}.py").write_text(
            "def migrate(migrator, database, **kwargs):\n    pass\n"
        )
    router = get_router(str(migrate_dir), "sqlite:///:memory:")

    with pytest.raises(ValueError, match="002_typo is not pending"):
        router.run("002_typo")

    assert router.done == []
    assert router.run("002_b") == ["001_a", "002_b"]
    assert router.run() == ["003_c"]


def test_run_one_error_propagates(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "001_boom.py").write_text(
        "def migrate(migrator, database, **kwargs):\n"
        "    raise RuntimeError('boom')\n"
        "\n"
        "def rollback(migrator, database, **kwargs):\n"
        "    pass\n"
    )
    router = get_router(str(migrate_dir), "sqlite:///:memory:")

    with pytest.raises(RuntimeError, match="boom"):
        router.run()


def test_router_rejects_invalid_arguments():
    with pytest.raises(TypeError, match="Invalid database"):
        Router("not a database")

    with pytest.raises(TypeError, match="Invalid migrator_class"):
        Router(pw.SqliteDatabase(":memory:"), migrator_class=object)


def test_create_auto_import_error(tmp_path):
    router = get_router(str(tmp_path / "migrations"), "sqlite:///:memory:")

    assert router.create("broken", auto="does.not.exist") is None
    assert router.todo == []


def test_create_auto_respects_ignore(tmp_path):
    migrate_dir = tmp_path / "migrations"
    router = Router(pw.SqliteDatabase(":memory:"), migrate_dir=migrate_dir, ignore=["color"])

    name = router.create("auto", auto="tests.models")
    content = (migrate_dir / f"{name}.py").read_text()

    assert "class Person(pw.Model)" in content
    assert "class Color" not in content


def test_merge_without_models(tmp_path):
    migrate_dir = tmp_path / "migrations"
    router = get_router(str(migrate_dir), pw.SqliteDatabase(":memory:"))

    router.merge()

    assert router.todo == []


def test_rollback_without_migrations(router):
    with pytest.raises(RuntimeError, match="nothing to rollback"):
        router.rollback()


def test_lock_migrations_mysql(monkeypatch):
    database = MySQLDatabase("app")
    queries = []

    class Cursor:
        def fetchone(self):
            return (1,)

    def execute_sql(sql, params=None):
        queries.append((sql, params))
        return Cursor()

    monkeypatch.setattr(database, "execute_sql", execute_sql)

    with lock_migrations(database, "migratehistory"):
        pass

    assert queries == [
        ("SELECT GET_LOCK(%s, %s)", ("app:migratehistory", 60)),
        ("SELECT RELEASE_LOCK(%s)", ("app:migratehistory",)),
    ]


def test_lock_migrations_mysql_is_busy(monkeypatch):
    database = MySQLDatabase("app")

    class Cursor:
        def fetchone(self):
            return (0,)

    monkeypatch.setattr(database, "execute_sql", lambda sql, params=None: Cursor())

    with (
        pytest.raises(RuntimeError, match="Could not acquire the migration lock"),
        lock_migrations(database, "migratehistory"),
    ):
        pass


def test_module_router_reads_migrations():
    module = ModuleType("migrations")
    migration = ModuleType("001_create")
    migration.migrate = lambda migrator, database, **kwargs: None
    module.__dict__["001_create"] = migration

    router = ModuleRouter(pw.SqliteDatabase(":memory:"), migrate_module=module)

    assert router.read("001_create") == (migration.migrate, void)


@pytest.mark.parametrize("dburl", ["postgres:///fake"])
def test_lock_migrations_postgres_waits(dburl, monkeypatch):
    database = connect(dburl)
    answers = iter([(False,), (True,)])
    monkeypatch.setattr(database.cursor(), "fetchone", lambda *args: next(answers))
    monkeypatch.setattr("peewee_migrate.router.time.sleep", lambda seconds: None)

    with lock_migrations(database, "migratehistory"):
        pass

    queries = database.cursor().queries
    assert sum("pg_try_advisory_lock" in query for query in queries) == 2


def test_create_auto_without_changes(tmp_path, monkeypatch):
    migrate_dir = tmp_path / "migrations"
    router = Router(pw.SqliteDatabase(":memory:"), migrate_dir=migrate_dir)
    monkeypatch.chdir(tmp_path)

    assert router.create("auto", auto=True) is None
    assert router.todo == []


def test_run_without_pending_migrations(tmp_path):
    migrate_dir = tmp_path / "migrations"
    router = get_router(str(migrate_dir), "sqlite:///:memory:")

    assert router.run() == []


def test_router_accepts_a_string_directory(tmp_path):
    router = Router(pw.SqliteDatabase(":memory:"), migrate_dir=str(tmp_path / "migrations"))

    assert isinstance(router.migrate_dir, Path)


def test_module_router_imports_a_module_path():
    router = ModuleRouter(pw.SqliteDatabase(":memory:"), migrate_module="tests.models")

    assert router.migrate_module.__name__ == "tests.models"


def test_load_models_skips_broken_modules(monkeypatch):
    real_import = import_module
    broken = "tests.test_autodiscover.models1.one_models"

    def fake_import(name, *args):
        if name == broken:
            raise ImportError(name)
        return real_import(name, *args)

    monkeypatch.setattr("peewee_migrate.router.import_module", fake_import)

    models = load_models("tests.test_autodiscover")

    assert models
    assert all(model.__module__ != broken for model in models)
