"""CLI integration."""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Pattern, Union

import click
from playhouse.db_url import connect

from .logs import logger
from .models import MIGRATE_TABLE
from .router import Router

if TYPE_CHECKING:
    from peewee_migrate.types import TParams

CLEAN_RE: Pattern = re.compile(r"\s+$", re.M)
VERBOSE: List[str] = ["WARNING", "INFO", "DEBUG", "NOTSET"]


def get_router(
    directory: Optional[Union[str, Path]] = None,
    database: Optional[str] = None,
    migratetable: str = MIGRATE_TABLE,
    verbose: int = 0,
) -> Router:
    """Load and initialize a router."""
    config: TParams = {}
    logging_level: str = VERBOSE[verbose]
    ignore = schema = None

    if directory:
        directory = Path(directory)
        try:
            with directory.joinpath("conf.py").open() as cfg:
                code = compile(cfg.read(), "<string>", "exec", dont_inherit=True)
                exec(code, config, config)
                database = config.get("DATABASE", database)
                ignore = config.get("IGNORE", ignore)
                schema = config.get("SCHEMA", schema)
                migratetable = config.get("MIGRATE_TABLE", migratetable)
                logging_level = config.get("LOGGING_LEVEL", logging_level).upper()

        except IOError:
            pass

    if isinstance(database, str):
        database = connect(database)

    logger.setLevel(logging_level)

    if not database:
        logger.error("Database is undefined")
        return sys.exit(1)

    try:
        return Router(
            database,
            migrate_table=migratetable,
            migrate_dir=directory,
            ignore=ignore,
            schema=schema,
        )
    except RuntimeError:
        logger.exception("Failed to initialize router")
        return sys.exit(1)


@click.group()
def cli():
    """Migrate database with Peewee ORM."""
    logging.basicConfig(level=logging.INFO)


@cli.command()
@click.option("--name", default=None, help="Select migration")
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--fake", is_flag=True, default=False, help="Run migration as fake.")
@click.option("--migratetable", default="migratehistory", help="Migration table.")
@click.option("-v", "--verbose", count=True)
def migrate(  # noqa: PLR0913
    name: Optional[str] = None,
    database: Optional[str] = None,
    directory: Optional[str] = None,
    migratetable: str = MIGRATE_TABLE,
    verbose: int = 0,
    *,
    fake: bool = False,
):
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
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--migratetable", default="migratehistory", help="Migration table.")
@click.option("-v", "--verbose", count=True)
def create(  # noqa: PLR0913
    name: Optional[str] = None,
    database: Optional[str] = None,
    directory: Optional[str] = None,
    migratetable: Optional[str] = None,
    verbose: int = 0,
    *,
    auto: bool = False,
    auto_source: Optional[str] = None,
):
    """Create a migration."""
    router: Router = get_router(directory, database, migratetable or MIGRATE_TABLE, verbose)
    router.create(name or "auto", auto=auto_source if auto and auto_source else auto)


@cli.command()
@click.option(
    "--count",
    required=False,
    default=1,
    type=int,
    help="Number of last migrations to be rolled back.Ignored in case of non-empty name",
)
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--migratetable", default="migratehistory", help="Migration table.")
@click.option("-v", "--verbose", count=True)
def rollback(
    database: Optional[str] = None,
    directory: Optional[str] = None,
    migratetable: Optional[str] = None,
    verbose: int = 0,
    count: int = 1,
):
    """Rollback a migration with the given steps --count of last migrations as integer number"""
    router: Router = get_router(directory, database, migratetable or MIGRATE_TABLE, verbose)
    if len(router.done) < count:
        raise RuntimeError(
            "Unable to rollback %s migrations from %s: %s" % (count, len(router.done), router.done)
        )
    for _ in range(count):
        router.rollback()


@cli.command()
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--migratetable", default="migratehistory", help="Migration table.")
@click.option("-v", "--verbose", count=True)
def list(  # noqa: A001
    database: Optional[str] = None,
    directory: Optional[str] = None,
    migratetable: Optional[str] = None,
    verbose: int = 0,
):
    """List migrations."""
    router: Router = get_router(directory, database, migratetable or MIGRATE_TABLE, verbose)
    click.secho("List of migrations:\n", fg="blue")
    for migration in router.done:
        click.echo(f"- [x] {migration}")

    for migration in router.diff:
        click.echo(f"- [ ] {migration}")

    click.secho(f"\nDone: {len(router.done)}, Pending: {len(router.diff)}", fg="blue")


@cli.command()
@click.option("--database", default=None, help="Database connection")
@click.option("--directory", default="migrations", help="Directory where migrations are stored")
@click.option("--migratetable", default="migratehistory", help="Migration table.")
@click.option("-v", "--verbose", count=True)
def merge(
    database: Optional[str] = None,
    directory: Optional[str] = None,
    migratetable: Optional[str] = None,
    verbose: int = 0,
):
    """Merge migrations into one."""
    router: Router = get_router(directory, database, migratetable or MIGRATE_TABLE, verbose)
    router.merge()
