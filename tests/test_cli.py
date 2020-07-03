from click.testing import CliRunner

runner = CliRunner()


def test_cli(tmpdir):
    tmpdir = str(tmpdir)
    from peewee_migrate.cli import cli
    from peewee_migrate.cli import get_router

    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'migrate' in result.output
    assert 'create' in result.output
    assert 'rollback' in result.output

    db_path = '%s/test_sqlite.db' % tmpdir
    db_url = 'sqlite:///%s' % db_path
    dir_option = '--directory=%s' % tmpdir
    db_option = '--database=%s' % db_url

    open(db_path, 'a').close()

    migrations_number = 5

    for i in range(migrations_number):
        result = runner.invoke(cli, ['create', dir_option, db_option, '-vvv', 'test'])
        assert result.exit_code == 0

    migrations_names = ['00%s_test' % i for i in range(1, migrations_number + 1)]
    migrations_names_str = ', '.join(migrations_names)

    # The fake seems having an issue or at least issue during testing, as
    # it affects freshly loaded router.done and breaks the tests after it
    # result = runner.invoke(cli, ['migrate', dir_option, db_option, '-v', '--fake'])
    # assert result.exit_code == 0
    # assert 'Migrations completed: %s' % migrations_names_str in result.output
    # assert 'add_column' not in result.output

    result = runner.invoke(cli, ['migrate', dir_option, db_option])
    assert result.exit_code == 0
    assert 'Migrations completed: %s' % migrations_names_str in result.output

    result = runner.invoke(cli, ['list', dir_option, db_option])
    assert 'Migrations are done:\n001_test' in result.output

    result = runner.invoke(cli, ['rollback', dir_option, db_option, '005_test'])
    assert not result.exception
    assert get_router(tmpdir, db_url).done == migrations_names[:-1]

    result = runner.invoke(cli, ['rollback', dir_option, db_option, '2'])
    assert not result.exception
    assert get_router(tmpdir, db_url).done == migrations_names[:-3]

    result = runner.invoke(cli, ['rollback', dir_option, db_option, '005_test'])
    assert result.exception
    assert result.exception.args[0] == 'Only last migration can be canceled.'
