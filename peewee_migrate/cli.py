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
    try:
        with open(os.path.join(directory, 'conf.py')) as cfg:
            exec_in(cfg.read(), config, config)
            database = config.get('DATABASE', database)
            logging_level = config.get('LOGGING_LEVEL', logging_level).upper()
    except IOError:
        pass

    if isinstance(database, string_types):
        database = connect(database)

    LOGGER.setLevel(logging_level)

    try:
        return Router(database, migrate_dir=directory)
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
@click.option('--fake', default=False, help=("Run migration as fake."))
@click.option('-v', '--verbose', count=True)
def migrate(name=None, database=None, directory=None, verbose=None, fake=False):
    """ Run migrations. """
    router = get_router(directory, database, verbose)
    migrations = router.run(name, fake=fake)
    if migrations:
        click.echo('Migrations completed: %s' % ', '.join(migrations))


@cli.command()
@click.argument('name')
@click.option('--auto', default=False, help=(
    "Create migrations automatically. Set path to your models module."))
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def create(name, database=None, auto=False, directory=None, verbose=None):
    """ Create migration. """
    router = get_router(directory, database, verbose)
    router.create(name, auto=auto)


@cli.command()
@click.argument('name')
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def rollback(name, database=None, directory=None, verbose=None):
    """ Rollback migration."""
    router = get_router(directory, database, verbose)
    router.rollback(name)
