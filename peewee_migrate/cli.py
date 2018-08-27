""" CLI integration. """
import os
import re
import sys

import click
from playhouse.db_url import connect

from peewee_migrate.compat import string_types


VERBOSE = ['WARNING', 'INFO', 'DEBUG', 'NOTSET']
CLEAN_RE = re.compile(r'\s+$', re.M)


def get_router(directory, database, verbose=0):
    from peewee_migrate import LOGGER
    from peewee_migrate.compat import exec_in
    from peewee_migrate.router import Router

    logging_level = VERBOSE[verbose]
    config = {}
    migrate_table = 'migratehistory'
    ignore = schema = None
    try:
        with open(os.path.join(directory, 'conf.py')) as cfg:
            exec_in(cfg.read(), config, config)
            database = config.get('DATABASE', database)
            ignore = config.get('IGNORE', ignore)
            schema = config.get('SCHEMA', schema)
            migrate_table = config.get('MIGRATE_TABLE', migrate_table)
            logging_level = config.get('LOGGING_LEVEL', logging_level).upper()
    except IOError:
        pass

    if isinstance(database, string_types):
        database = connect(database)

    LOGGER.setLevel(logging_level)

    try:
        return Router(database, migrate_table=migrate_table, migrate_dir=directory,
                      ignore=ignore, schema=schema)
    except RuntimeError as exc:
        LOGGER.error(exc)
        return sys.exit(1)


@click.group()
def cli():
    pass


@cli.command()
@click.option('--name', default=None, help="Select migration")
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('--fake', is_flag=True, default=False, help="Run migration as fake.")
@click.option('-v', '--verbose', count=True)
def migrate(name=None, database=None, directory=None, verbose=None, fake=False):
    """Migrate database."""
    router = get_router(directory, database, verbose)
    migrations = router.run(name, fake=fake)
    if migrations:
        click.echo('Migrations completed: %s' % ', '.join(migrations))


@cli.command()
@click.argument('name')
@click.option('--auto', default=False, is_flag=True, help=(
    "Scan sources and create db migrations automatically. "
    "Supports autodiscovery."))
@click.option('--auto-source', default=False, help=(
    "Set to python module path for changes autoscan (e.g. 'package.models'). "
    "Current directory will be recursively scanned by default."))
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def create(name, database=None, auto=False, auto_source=False, directory=None, verbose=None):
    """Create a migration."""
    router = get_router(directory, database, verbose)
    if auto and auto_source:
        auto = auto_source
    router.create(name, auto=auto)


@cli.command()
@click.argument('name')
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def rollback(name, database=None, directory=None, verbose=None):
    """Rollback a migration with given name."""
    router = get_router(directory, database, verbose)
    router.rollback(name)


@cli.command()
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def list(database=None, directory=None, verbose=None):
    """List migrations."""
    router = get_router(directory, database, verbose)
    click.echo('Migrations are done:')
    click.echo('\n'.join(router.done))
    click.echo('')
    click.echo('Migrations are undone:')
    click.echo('\n'.join(router.diff))


@cli.command()
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def merge(database=None, directory=None, verbose=None):
    """Merge migrations into one."""
    router = get_router(directory, database, verbose)
    router.merge()
