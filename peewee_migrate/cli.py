""" CLI integration. """
import os
import re
import sys
from importlib import import_module

import click
import peewee as pw
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
        click.echo('Migrations are completed: %s' % ', '.join(migrations))


@cli.command()
@click.argument('name')
@click.option('--auto', default=False, help=(
    "Create migrations automatically. Set to your models module."))
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def create(name, database=None, auto=False, directory=None, verbose=None):
    """ Create migration. """
    from peewee_migrate.auto import diff_many, NEWLINE
    router = get_router(directory, database, verbose)
    migrate_ = rollback_ = ''
    if auto:
        try:
            mod = import_module(auto)
            models = []
            for name_ in dir(mod):
                obj = getattr(mod, name_)
                if isinstance(obj, type) and issubclass(obj, pw.Model):
                    models.append(obj)
            try:
                migrator = router.migrator
            except Exception as exc:  # noqa
                router.logger.error(exc)
                return sys.exit(1)
            for name_ in router.diff:
                router.run_one(name_, migrator)
            migrate_ = diff_many(models, migrator.orm.values())
            if not migrate_:
                return router.logger.warn('No changes has found.')

            migrate_ = NEWLINE + NEWLINE.join('\n\n'.join(migrate_).split('\n'))
            migrate_ = CLEAN_RE.sub('\n', migrate_)
            rollback_ = diff_many(migrator.orm.values(), models)
            rollback_ = NEWLINE + NEWLINE.join('\n\n'.join(rollback_).split('\n'))
            rollback_ = CLEAN_RE.sub('\n', rollback_)
        except ImportError:
            router.logger.error('Invalid module.')

    router.create(name, migrate=migrate_, rollback=rollback_)


@cli.command()
@click.argument('name')
@click.option('--database', default=None, help="Database connection")
@click.option('--directory', default='migrations', help="Directory where migrations are stored")
@click.option('-v', '--verbose', count=True)
def rollback(name, database=None, directory=None, verbose=None):
    router = get_router(directory, database, verbose)
    router.rollback(name)
