"""CLI integration."""
import typing as t

import os
import re
import sys

import click
from playhouse.db_url import connect

from . import LOGGER, MIGRATE_TABLE
from .router import Router


CLEAN_RE: t.Pattern = re.compile(r'\s+$', re.M)
VERBOSE: t.List[str] = ['WARNING', 'INFO', 'DEBUG', 'NOTSET']


def get_router(directory: str = None, database: str = None,
               migratetable: str = MIGRATE_TABLE, verbose: int = 0) -> Router:
    """Load and initialize a router."""
    config: t.Dict = {}
    logging_level: str = VERBOSE[verbose]
    ignore = schema = None

    if directory:
        try:
            with open(os.path.join(directory, 'conf.py')) as cfg:
                code = compile(cfg.read(), '<string>', 'exec', dont_inherit=True)
                exec(code, config, config)
                database = config.get('DATABASE', database)
                ignore = config.get('IGNORE', ignore)
                schema = config.get('SCHEMA', schema)
                migratetable = config.get('MIGRATE_TABLE', migratetable)
                logging_level = config.get('LOGGING_LEVEL', logging_level).upper()
        except IOError:
            pass

    if isinstance(database, str):
        database = connect(database)

    LOGGER.setLevel(logging_level)

    if not database:
        LOGGER.error("Database is undefined")
        return sys.exit(1)

    try:
        return Router(database, migrate_table=migratetable, migrate_dir=directory,
                      ignore=ignore, schema=schema)
    except RuntimeError as exc:
        LOGGER.error(exc)
        return sys.exit(1)


@click.group()
def cli():
    """Just a group."""
    pass


@cli.command()
@click.option('--name', default=None, help="Select migration")
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('--fake', is_flag=True, default=False, help="Run migration as fake.")
@click.option('--migratetable', default="migratehistory", help="Migration table.")
@click.option('-v', '--verbose', count=True)
def migrate(name: str = None, database: str = None, directory: str = None,
            migratetable: str = MIGRATE_TABLE, verbose: int = 0, fake: bool = False):
    """Migrate database."""
    router = get_router(directory, database, migratetable, verbose)
    migrations = router.run(name, fake=fake)
    if migrations:
        click.echo('Migrations completed: %s' % ', '.join(migrations))


@cli.command()
@click.argument('name')
@click.option('--auto', default=False, is_flag=True, help=(
    "Scan sources and create db migrations automatically. "
    "Supports autodiscovery."))
@click.option('--auto-source', default=None, help=(
    "Set to python module path for changes autoscan (e.g. 'package.models'). "
    "Current directory will be recursively scanned by default."))
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('--migratetable', default="migratehistory", help="Migration table.")
@click.option('-v', '--verbose', count=True)
def create(name: str = None, database: str = None, directory: str = None,
           migratetable: str = MIGRATE_TABLE, verbose: int = 0,
           auto: bool = False, auto_source: str = None):
    """Create a migration."""
    router: Router = get_router(directory, database, migratetable, verbose)
    router.create(name or 'auto', auto=auto_source if auto and auto_source else auto)


@cli.command()
@click.argument('name', required=False)
@click.option('--count', required=False, default=1, type=int,
              help="Number of last migrations to be rolled back."
                   "Ignored in case of non-empty name")
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('--migratetable', default="migratehistory", help="Migration table.")
@click.option('-v', '--verbose', count=True)
def rollback(name: str = None, database: str = None, directory: str = None,
             migratetable: str = MIGRATE_TABLE, verbose: int = 0, count: int = 1):
    """Rollback a migration with given name or number of last migrations with given --count option as integer number"""  # noqa
    router: Router = get_router(directory, database, migratetable, verbose)
    if not name:
        if len(router.done) < count:
            raise RuntimeError(
                'Unable to rollback %s migrations from %s: %s' %
                (count, len(router.done), router.done))
        for _ in range(count):
            router = get_router(directory, database, migratetable, verbose)
            name = router.done[-1]
            router.rollback(name)
    else:
        router.rollback(name)


@cli.command()
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('--migratetable', default="migratehistory", help="Migration table.")
@click.option('-v', '--verbose', count=True)
def list(database: str = None, directory: str = None,
         migratetable: str = MIGRATE_TABLE, verbose: int = 0):
    """List migrations."""
    router: Router = get_router(directory, database, migratetable, verbose)
    click.echo('Migrations are done:')
    click.echo('\n'.join(router.done))
    click.echo('')
    click.echo('Migrations are undone:')
    click.echo('\n'.join(router.diff))


@cli.command()
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('--migratetable', default="migratehistory", help="Migration table.")
@click.option('-v', '--verbose', count=True)
def merge(database: str = None, directory: str = None,
          migratetable: str = MIGRATE_TABLE, verbose: int = 0):
    """Merge migrations into one."""
    router: Router = get_router(directory, database, migratetable, verbose)
    router.merge()
