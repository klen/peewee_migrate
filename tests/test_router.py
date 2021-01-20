"""Tests for `peewee_migrate` module."""
import os

from unittest import mock
import peewee as pw


MIGRATIONS_DIR = os.path.join('tests', 'migrations')


def test_router():
    from peewee_migrate import MigrateHistory
    from peewee_migrate.cli import get_router

    router = get_router(MIGRATIONS_DIR, 'sqlite:///:memory:')

    assert router.database
    assert isinstance(router.database, pw.Database)

    assert router.todo == ['001_test', '002_test', '003_tespy']
    assert router.done == []
    assert router.diff == ['001_test', '002_test', '003_tespy']

    router.create('new')
    assert router.todo == ['001_test', '002_test', '003_tespy', '004_new']
    os.remove(os.path.join(MIGRATIONS_DIR, '004_new.py'))

    MigrateHistory.create(name='001_test')
    assert router.diff == ['002_test', '003_tespy']

    MigrateHistory.delete().execute()

    router.run()
    assert router.diff == []

    with mock.patch('peewee.Database.execute_sql') as execute_sql:
        router.run_one('002_test', router.migrator, fake=True)

    assert not execute_sql.called

    migrations = MigrateHistory.select()
    assert list(migrations)
    assert migrations.count() == 3

    router.rollback('003_tespy')
    assert router.diff == ['003_tespy']
    assert migrations.count() == 2

    with mock.patch('os.remove') as mocked:
        router.merge()
        assert mocked.call_count == 3
        assert mocked.call_args[0][0] == os.path.join(MIGRATIONS_DIR, '003_tespy.py')
        assert MigrateHistory.select().count() == 1

    os.remove(os.path.join(MIGRATIONS_DIR, '001_initial.py'))

    from peewee_migrate.router import load_models

    models = load_models('tests.test_autodiscover')
    assert models

    models = load_models('tests.test_autodiscover')
    assert models


def test_router_compile(tmpdir):
    from peewee_migrate.cli import get_router

    migrations = tmpdir.mkdir('migrations')
    router = get_router(str(migrations), 'sqlite:///:memory:')
    router.compile('test_router_compile')

    with open(str(migrations.join('001_test_router_compile.py'))) as f:
        content = f.read()
        assert 'SQL = pw.SQL' in content

# pylama:ignore=W0621
