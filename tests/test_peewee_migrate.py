""" Tests for `peewee_migrate` module. """
from peewee_migrate.core import Router as R, MigrateHistory as MH


def test_router():

    rr = R('tests/migrations', DATABASE='sqlite:///remove_me')
    rr = R('tests/migrations', DATABASE='sqlite:///remove_me')

    assert rr.db
    assert rr.db.database != 'remove_me'
    assert rr.fs_migrations == ['001_test', '002_test', '003_tespy']
    assert rr.db_migrations == []
    assert rr.diff == ['001_test', '002_test', '003_tespy']

    MH.create(name='001_test')
    assert rr.diff == ['002_test', '003_tespy']

    MH.delete().execute()

    rr.run()
    assert rr.diff == []
    migrations = MH.select()
    assert list(migrations)


# pylama:ignore=W0621
