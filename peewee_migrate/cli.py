"""CLI integration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import click
from playhouse.db_url import connect

from .logs import logger
from .models import MIGRATE_TABLE
from .router import Router

if TYPE_CHECKING:
    from collections.abc import Iterable

    import peewee as pw

    from peewee_migrate.types import TParams

VERBOSE: list[str] = ["WARNING", "INFO", "DEBUG", "NOTSET"]


def get_router(
    directory: str | Path | None = None,
    database: str | pw.Database | pw.Proxy | None = None,
    migratetable: str = MIGRATE_TABLE,
    verbose: int = 0,
    ignore: Iterable[str] | None = None,
) -> Router:
    """Load and initialize a router."""
    config: TParams = {}
    logging_level: str = VERBOSE[min(verbose, len(VERBOSE) - 1)]
    ignore = list(ignore) if ignore else None
    schema = None

    if directory:
        directory = Path(directory)
        conf = directory / "conf.py"
        if conf.exists():
            with conf.open() as cfg:
                code = compile(cfg.read(), "<string>", "exec", dont_inherit=True)
                exec(code, config, config)
                database = config.get("DATABASE", database)
                # IGNORE from conf.py adds to --ignore, both name tables to skip.
                ignore = [*(ignore or ()), *(config.get("IGNORE") or ())] or None
                schema = config.get("SCHEMA", schema)
                migratetable = config.get("MIGRATE_TABLE", migratetable)
                logging_level = config.get("LOGGING_LEVEL", logging_level).upper()

    db: pw.Database | pw.Proxy | None = connect(database) if isinstance(database, str) else database

    logger.setLevel(logging_level)

    if not db:
        logger.error("Database is undefined")
        raise SystemExit(1)

    try:
        return Router(
            db,
            migrate_table=migratetable,
            migrate_dir=directory,
            ignore=ignore,
            schema=schema,
        )
    except RuntimeError as exc:
        logger.exception("Failed to initialize router")
        raise SystemExit(1) from exc


@click.group()
def cli() -> None:
    """Migrate database with Peewee ORM."""
    logging.basicConfig(level=logging.INFO)


@cli.command()
@click.option("--name", default=None, help="Select migration")
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--fake", is_flag=True, default=False, help="Run migration as fake.")
@click.option("--migratetable", default=MIGRATE_TABLE, help="Migration table.")
@click.option("-v", "--verbose", count=True)
def migrate(  # noqa: PLR0913
    name: str | None = None,
    database: str | None = None,
    directory: str | None = None,
    migratetable: str = MIGRATE_TABLE,
    verbose: int = 0,
    *,
    fake: bool = False,
) -> None:
    """Migrate database."""
    router = get_router(directory, database, migratetable, verbose)
    click.secho("Migrating %s" % router.database.database, fg="blue")
    for mgr in router.run(name, fake=fake):
        click.echo("- [x] %s" % mgr)

    click.echo("OK")


@cli.command()
@click.argument("name")
@click.option(
    "--auto",
    default=False,
    is_flag=True,
    help="Scan sources and create db migrations automatically. Supports autodiscovery.",
)
@click.option(
    "--auto-source",
    default=None,
    help=(
        "Set to python module path for changes autoscan (e.g. 'package.models'). "
        "Current directory will be recursively scanned by default."
    ),
)
@click.option(
    "--ignore",
    multiple=True,
    help="Model name to ignore during autoscan. Repeat for multiple models.",
)
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--migratetable", default=MIGRATE_TABLE, help="Migration table.")
@click.option("-v", "--verbose", count=True)
def create(  # noqa: PLR0913
    name: str | None = None,
    database: str | None = None,
    directory: str | None = None,
    migratetable: str = MIGRATE_TABLE,
    verbose: int = 0,
    *,
    auto: bool = False,
    auto_source: str | None = None,
    ignore: tuple[str, ...] = (),
) -> None:
    """Create a migration."""
    router: Router = get_router(directory, database, migratetable, verbose, ignore)
    router.create(name or "auto", auto=auto_source if auto and auto_source else auto)


@cli.command()
@click.option(
    "--count",
    required=False,
    default=1,
    type=int,
    help="Number of last migrations to be rolled back.",
)
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--migratetable", default=MIGRATE_TABLE, help="Migration table.")
@click.option("-v", "--verbose", count=True)
def rollback(
    database: str | None = None,
    directory: str | None = None,
    migratetable: str = MIGRATE_TABLE,
    verbose: int = 0,
    count: int = 1,
) -> None:
    """Rollback migrations."""
    router: Router = get_router(directory, database, migratetable, verbose)
    if len(router.done) < count:
        raise RuntimeError(
            "Unable to rollback %s migrations from %s: %s" % (count, len(router.done), router.done)
        )
    for _ in range(count):
        router.rollback()


@cli.command(name="list")
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--migratetable", default=MIGRATE_TABLE, help="Migration table.")
@click.option("-v", "--verbose", count=True)
def list_migrations(
    database: str | None = None,
    directory: str | None = None,
    migratetable: str = MIGRATE_TABLE,
    verbose: int = 0,
) -> None:
    """List migrations."""
    router: Router = get_router(directory, database, migratetable, verbose)
    click.secho("List of migrations:\n", fg="blue")
    for migration in router.done:
        click.echo(f"- [x] {migration}")

    for migration in router.diff:
        click.echo(f"- [ ] {migration}")

    click.secho(f"\nDone: {len(router.done)}, Pending: {len(router.diff)}", fg="blue")


@cli.command()
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--migratetable", default=MIGRATE_TABLE, help="Migration table.")
@click.option("-v", "--verbose", count=True)
def merge(
    database: str | None = None,
    directory: str | None = None,
    migratetable: str = MIGRATE_TABLE,
    verbose: int = 0,
) -> None:
    """Merge migrations into one."""
    router: Router = get_router(directory, database, migratetable, verbose)
    router.merge()
