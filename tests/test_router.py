"""Tests for `peewee_migrate` module."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import peewee as pw
import pytest
from playhouse.db_url import connect

from peewee_migrate.cli import get_router
from peewee_migrate.router import load_models, lock_migrations

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
