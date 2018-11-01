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
        'create', '--directory=%s' % tmpdir, '--database=sqlite:///:memory:', '-vvv', 'test'])
    assert result.exit_code == 0

    result = runner.invoke(cli, [
        'migrate', '--directory=%s' % tmpdir, '--database=sqlite:///:memory:', '-v', '--fake'])
    assert result.exit_code == 0
    assert 'Migrations completed: 001_test' in result.output
    assert 'add_column' not in result.output

    result = runner.invoke(cli, [
        'migrate', '--directory=%s' % tmpdir, '--database=sqlite:///:memory:'])
    assert result.exit_code == 0
    assert 'Migrations completed: 001_test' in result.output

    result = runner.invoke(cli, [
        'rollback', '--directory=%s' % tmpdir, '--database=sqlite:///:memory:', '001_test'])
    assert result.exception
    assert result.exception.args[0] == 'No migrations are found.'

    result = runner.invoke(cli, [
        'list', '--directory=%s' % tmpdir, '--database=sqlite:///:memory:'])
    assert 'Migrations are undone:\n001_test' in result.output
