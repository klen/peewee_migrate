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


def test_verbose_overflow(dir_option, db_option):
    result = runner.invoke(cli, ["list", dir_option, db_option, "-vvvv"])

    assert result.exit_code == 0


def test_fake(dir_option, db_option, migrations, router):
    result = runner.invoke(cli, ["migrate", dir_option, db_option, "-v", "--fake"])
    assert result.exit_code == 0
    for mgr in migrations:
        assert mgr in result.output

    # TODO: Find a way of testing fake. This is unclear why the following fails.


def test_get_router_without_database():
    with pytest.raises(SystemExit):
        get_router()


def test_list_shows_applied(dir_option, db_option, migrations):
    runner.invoke(cli, ["migrate", dir_option, db_option, "--name=%s" % migrations[0]])

    result = runner.invoke(cli, ["list", dir_option, db_option])

    assert result.exit_code == 0
    assert "- [x] %s" % migrations[0] in result.output


def test_merge(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "001_create.py").write_text(
        "import peewee as pw\n"
        "def migrate(migrator, database, **kwargs):\n"
        "    @migrator.create_model\n"
        "    class Thing(pw.Model):\n"
        "        name = pw.CharField()\n"
    )
    db_url = "sqlite:///%s" % (tmp_path / "app.db")
    migrate = runner.invoke(cli, ["migrate", f"--directory={migrate_dir}", f"--database={db_url}"])
    assert migrate.exit_code == 0

    result = runner.invoke(cli, ["merge", f"--directory={migrate_dir}", f"--database={db_url}"])

    assert result.exit_code == 0
    assert [path.name for path in migrate_dir.iterdir()] == ["001_initial.py"]


@pytest.mark.parametrize("ignored", [(), ("color",), ("color", "pet")])
def test_create_auto_ignore(tmp_path, ignored):
    migrate_dir = tmp_path / "migrations"
    db_url = "sqlite:///%s" % (tmp_path / "app.db")
    args = [
        "create",
        f"--directory={migrate_dir}",
        f"--database={db_url}",
        "--auto",
        "--auto-source=tests.models",
        *[f"--ignore={name}" for name in ignored],
        "auto",
    ]

    result = runner.invoke(cli, args)

    assert result.exit_code == 0, result.output
    [written] = migrate_dir.iterdir()
    content = written.read_text()
    assert "class Person(pw.Model)" in content
    assert ("class Color" in content) is not ("color" in ignored)
    assert ("class Pet" in content) is not ("pet" in ignored)


def test_create_auto_ignore_adds_to_conf(tmp_path):
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    (migrate_dir / "conf.py").write_text('IGNORE = ["color"]\n')
    db_url = "sqlite:///%s" % (tmp_path / "app.db")

    result = runner.invoke(
        cli,
        [
            "create",
            f"--directory={migrate_dir}",
            f"--database={db_url}",
            "--auto",
            "--auto-source=tests.models",
            "--ignore=pet",
            "auto",
        ],
    )

    assert result.exit_code == 0, result.output
    content = (migrate_dir / "001_auto.py").read_text()
    assert "class Person(pw.Model)" in content
    assert "class Color" not in content
    assert "class Pet" not in content


def test_get_router_passes_ignore():
    database = pw.SqliteDatabase(":memory:")
    router = get_router(None, database, ignore=["color", "pet"])

    assert router.ignore == ["color", "pet"]
