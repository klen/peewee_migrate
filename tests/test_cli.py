from click.testing import CliRunner

runner = CliRunner()


def test_cli(tmpdir):
    from peewee_migrate.cli import cli

    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'migrate' in result.output
    assert 'create' in result.output
    assert 'rollback' in result.output

    result = runner.invoke(cli, [
        'create', '--directory=%s' % tmpdir, '--database=sqlite:///:memory:', 'test'])
    assert result.exit_code == 0
    assert 'Migration is created' in result.output

    result = runner.invoke(cli, [
        'migrate', '--directory=%s' % tmpdir, '--database=sqlite:///:memory:'])
    assert result.exit_code == 0
    assert 'Migrations are completed: 001_test' in result.output

    result = runner.invoke(cli, [
        'rollback', '--directory=%s' % tmpdir, '--database=sqlite:///:memory:', '001_test'])
    assert result.exit_code == -1

    result = runner.invoke(cli, ['rollback', 'test'])
    assert type(result.exception) == RuntimeError
