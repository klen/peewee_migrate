import pytest
from click.testing import CliRunner

from peewee_migrate.cli import cli, get_router

runner = CliRunner()


@pytest.fixture
def dir_option(tmpdir):
    return "--directory=%s" % tmpdir


@pytest.fixture
def db_url(tmpdir):
    db_path = "%s/test_sqlite.db" % tmpdir
    open(db_path, "a").close()
    return "sqlite:///%s" % db_path


@pytest.fixture
def db_option(db_url):
    return "--database=%s" % db_url


@pytest.fixture
def router(tmpdir, db_url):
    return lambda: get_router(str(tmpdir), db_url)


@pytest.fixture
def migrations(router):
    migrations_number = 5
    name = "test"
    for i in range(migrations_number):
        router().create(name)
    return ["00%s_test" % i for i in range(1, migrations_number + 1)]


@pytest.fixture
def migrations_str(migrations):
    return ", ".join(migrations)


def test_help():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "create" in result.output
    assert "rollback" in result.output


def test_create(dir_option, db_option):
    for i in range(2):
        result = runner.invoke(cli, ["create", dir_option, db_option, "-vvv", "test"])
        assert result.exit_code == 0


def test_migrate(dir_option, db_option, migrations_str):
    result = runner.invoke(cli, ["migrate", dir_option, db_option])
    assert result.exit_code == 0
    assert "Migrations completed: %s" % migrations_str in result.output


def test_list(dir_option, db_option, migrations):
    result = runner.invoke(cli, ["list", dir_option, db_option])
    assert "Migrations are done:\n" in result.output
    assert "Migrations are undone:\n%s" % "\n".join(migrations) in result.output


def test_rollback(dir_option, db_option, router, migrations):
    router().run()

    count_overflow = len(migrations) + 1
    result = runner.invoke(
        cli, ["rollback", dir_option, db_option, "--count=%s" % count_overflow]
    )
    assert result.exception
    assert (
        "Unable to rollback %s migrations" % count_overflow in result.exception.args[0]
    )
    assert router().done == migrations

    result = runner.invoke(cli, ["rollback", dir_option, db_option])
    assert not result.exception
    assert router().done == migrations[:-1]

    result = runner.invoke(cli, ["rollback", dir_option, db_option])
    assert not result.exception
    assert router().done == migrations[:-2]

    result = runner.invoke(cli, ["rollback", dir_option, db_option, "--count=2"])
    assert not result.exception
    assert router().done == migrations[:-4]


def test_fake(dir_option, db_option, migrations_str, router):
    result = runner.invoke(cli, ["migrate", dir_option, db_option, "-v", "--fake"])
    assert result.exit_code == 0
    assert "Migrations completed: %s" % migrations_str in result.output

    # TODO: Find a way of testing fake. This is unclear why the following fails.
    # assert not router().done
