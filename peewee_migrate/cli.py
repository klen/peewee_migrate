""" CLI integration. """
import os
from types import StringTypes

import click
from playhouse.db_url import connect


VERBOSE = ['WARNING', 'INFO', 'DEBUG']


def get_router(directory, database, verbose=0):
    from peewee_migrate import LOGGER
    from peewee_migrate.utils import exec_in # noqa
    from peewee_migrate.router import Router

    logging_level = VERBOSE[verbose]
    config = {}
    try:
        with open(os.path.join(directory, 'conf.py')) as cfg:
            exec_in(cfg.read(), config, config)
            database = config.get('DATABASE', database)
            logging_level = config.get('LOGGING_LEVEL', logging_level)
    except IOError:
        pass

    if isinstance(database, StringTypes):
        database = connect(database)

    LOGGER.setLevel(logging_level)

    return Router(database, migrate_dir=directory)


@click.group()
def cli():
    pass


@cli.command()
@click.option('--name', default=None, help="Select migration")
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def migrate(name=None, database=None, directory=None, verbose=None):
    """ Run migrations. """
    router = get_router(directory, database, verbose)
    migrations = router.run(name)
    click.echo('Migrations are completed: %s' % ', '.join(migrations))


@cli.command()
@click.argument('name')
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def create(name, database=None, directory=None, verbose=None):
    """ Create migration. """
    router = get_router(directory, database, verbose)
    path = router.create(name)
    click.echo('Migration is created: %s' % path)


@cli.command()
@click.argument('name')
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def rollback(name, database=None, directory=None, verbose=None):
    router = get_router(directory, database, verbose)
    name = router.rollback(name)
    click.echo('Migration has been canceled: %s' % name)
