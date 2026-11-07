import peewee as pw
import pytest
from click.testing import CliRunner

from peewee_migrate.cli import cli, get_router

runner = CliRunner()


@pytest.fixture
def dir_option(tmpdir):
    return "--directory=%s" % tmpdir


@pytest.fixture
def db_url(tmpdir):
    db_path = tmpdir / "test_sqlite.db"
    db_path.open("a").close()
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
    for _i in range(migrations_number):
        router().create(name)
    return ["00%s_test" % i for i in range(1, migrations_number + 1)]


@pytest.fixture
def migrations_str(migrations):
    return ", ".join(migrations)


def test_get_router_with_database_object():
    database = pw.SqliteDatabase(":memory:")
    router = get_router(None, database)

    assert router.database is database


def test_help():
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "create" in result.output
    assert "rollback" in result.output


def test_create(dir_option, db_option):
    for _i in range(2):
        result = runner.invoke(cli, ["create", dir_option, db_option, "-vvv", "test"])
        assert result.exit_code == 0


def test_migrate(dir_option, db_option, migrations):
    result = runner.invoke(cli, ["migrate", dir_option, db_option])
    assert result.exit_code == 0
    for mgr in migrations:
        assert mgr in result.output


def test_list(dir_option, db_option, migrations):
    result = runner.invoke(cli, ["list", dir_option, db_option])
    assert "List of migrations" in result.output
    for mgr in migrations:
        assert mgr in result.output


def test_rollback(dir_option, db_option, router, migrations):
    router().run()

    count_overflow = len(migrations) + 1
    result = runner.invoke(cli, ["rollback", dir_option, db_option, "--count=%s" % count_overflow])
    assert result.exception
    assert "Unable to rollback %s migrations" % count_overflow in result.exception.args[0]
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


def test_fake(dir_option, db_option, migrations, router):
    result = runner.invoke(cli, ["migrate", dir_option, db_option, "-v", "--fake"])
    assert result.exit_code == 0
    for mgr in migrations:
        assert mgr in result.output

    # TODO: Find a way of testing fake. This is unclear why the following fails.


@pytest.mark.parametrize("ignored", [(), ("ignoredone",), ("ignoredone", "ignoredtwo")])
@pytest.mark.parametrize("from_config", [False, True])
def test_create_auto_ignore_issue_165(tmp_path, monkeypatch, db_url, ignored, from_config):
    dir_option = f"--directory={tmp_path}"
    db_option = f"--database={db_url}"
    models = tmp_path / "ignored_cli_models.py"
    models.write_text(
        "from peewee import Model, TextField\n"
        "class Kept(Model):\n    value = TextField()\n"
        "class IgnoredOne(Model):\n    value = TextField()\n"
        "class IgnoredTwo(Model):\n    value = TextField()\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    if from_config:
        (tmp_path / "conf.py").write_text(f"IGNORE = {ignored!r}\n")
    options = [] if from_config else [item for name in ignored for item in ("--ignore", name)]
    result = runner.invoke(
        cli,
        [
            "create",
            "initial",
            dir_option,
            db_option,
            "--auto",
            "--auto-source",
            "ignored_cli_models",
            *options,
        ],
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli, ["migrate", dir_option, db_option])
    assert result.exit_code == 0, result.output
    tables = set(get_router(tmp_path, db_url).database.get_tables())
    assert tables == {"kept", "ignoredone", "ignoredtwo", "migratehistory"} - set(ignored)
