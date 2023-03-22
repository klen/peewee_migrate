"""Tests for `peewee_migrate` module."""
from __future__ import annotations

import os
from unittest import mock

import peewee as pw

MIGRATIONS_DIR = os.path.join("tests", "migrations")


def test_router():
    from peewee_migrate.cli import get_router
    from peewee_migrate.models import MigrateHistory

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
    os.remove(os.path.join(MIGRATIONS_DIR, "004_new.py"))

    router.create("new1", auto=Dummy)
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new1"]
    os.remove(os.path.join(MIGRATIONS_DIR, "004_new1.py"))

    router.create("new2", auto=[Dummy])
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new2"]
    os.remove(os.path.join(MIGRATIONS_DIR, "004_new2.py"))

    router.create("new3", auto="tests.models")
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new3"]
    os.remove(os.path.join(MIGRATIONS_DIR, "004_new3.py"))

    router.create("new4", auto=["tests.models"])
    assert router.todo == ["001_test", "002_test", "003_tespy", "004_new4"]
    os.remove(os.path.join(MIGRATIONS_DIR, "004_new4.py"))

    MigrateHistory.create(name="001_test")
    assert router.diff == ["002_test", "003_tespy"]

    MigrateHistory.delete().execute()

    router.run()
    assert router.diff == []

    with mock.patch("peewee.Database.execute_sql") as execute_sql:
        router.run_one("002_test", router.migrator, fake=True)

    assert not execute_sql.called

    migrations = MigrateHistory.select()
    assert list(migrations)
    assert migrations.count() == 3

    router.rollback()
    assert router.diff == ["003_tespy"]
    assert migrations.count() == 2

    with mock.patch("pathlib.Path.unlink") as mocked:
        router.merge()
        assert mocked.call_count == 3
        # assert mocked.call_args[0][0] == os.path.join(MIGRATIONS_DIR, "003_tespy.py")
        assert MigrateHistory.select().count() == 1

    os.remove(os.path.join(MIGRATIONS_DIR, "001_initial.py"))

    from peewee_migrate.router import load_models

    models = load_models("tests.test_autodiscover")
    assert models

    models = load_models("tests.test_autodiscover")
    assert models

    from .test_autodiscover.some_folder_one import one_models

    models = load_models(one_models)
    assert models

    models = load_models(one_models)
    assert models


def test_router_compile(tmpdir):
    from peewee_migrate.cli import get_router

    migrations = tmpdir.mkdir("migrations")
    router = get_router(str(migrations), "sqlite:///:memory:")
    router.compile("test_router_compile")

    with open(str(migrations.join("001_test_router_compile.py"))) as f:
        content = f.read()
        assert "SQL = pw.SQL" in content
