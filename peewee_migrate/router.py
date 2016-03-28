import os
import re
from importlib import import_module
from types import StringTypes

import mock
import peewee as pw
from cached_property import cached_property

from peewee_migrate import LOGGER, MigrateHistory
from peewee_migrate.migrator import Migrator
from peewee_migrate.utils import exec_in  # noqa


MIGRATE_DIR = os.path.join(os.getcwd(), 'migrations')
VOID = lambda m, d: None # noqa
with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template.txt')) as t:
    MIGRATE_TEMPLATE = t.read()


class BaseRouter(object):

    """Abstract base class for router."""

    def __init__(self, database, logger=LOGGER):
        self.database = database
        self.logger = logger
        if not isinstance(self.database, (pw.Database, pw.Proxy)):
            raise RuntimeError('Invalid database: %s' % database)

    @cached_property
    def model(self):
        """Ensure that migrations has prepared to run."""
        # Initialize MigrationHistory model
        MigrateHistory._meta.database = self.database
        try:
            MigrateHistory.create_table()
        except pw.DatabaseError:
            self.database.rollback()
        return MigrateHistory

    @property
    def todo(self):
        raise NotImplementedError

    def create(self, name='auto'):
        """Create a migration."""
        raise NotImplementedError

    def read(self, name):
        raise NotImplementedError

    @property
    def done(self):
        """Scan migrations in database."""
        return [mm.name for mm in self.model.select()]

    @property
    def diff(self):
        """Calculate difference between fs and db."""
        done = set(self.done)
        return [name for name in self.todo if name not in done]

    @property
    def migrator(self):
        migrator = Migrator(self.database)
        for name in self.done:
            self.run_one(name, migrator)
        return migrator

    def run_one(self, name, migrator, fake=True, downgrade=False, force=False):
        """Run a migration."""

        try:
            migrate, rollback = self.read(name)
            if fake:
                with mock.patch('peewee.Model.select'):
                    with mock.patch('peewee.InsertQuery.execute'):
                        migrate(migrator, self.database)

                if force:
                    self.model.create(name=name)
                    self.logger.info('Done %s', name)

                migrator.clean()
                return migrator

            self.logger.info('Run "%s"', name)
            with self.database.transaction():
                if not downgrade:
                    migrate(migrator, self.database)
                    migrator.run()
                    self.model.create(name=name)
                    self.logger.info('Done %s', name)
                else:
                    self.logger.info('Rollback %s', name)
                    rollback(migrator, self.database)
                    migrator.run()
                    self.model.delete().where(self.model.name == name).execute()
                    self.logger.info('Rolled back %s', name)

        except Exception as exc:
            self.database.rollback()
            self.logger.exception(exc)
            self.logger.error('Migration failed: %s', name)
            raise

    def run(self, name=None, fake=False):
        """Run migrations."""
        self.logger.info('Start migrations')

        done = []
        diff = self.diff
        if not diff:
            self.logger.info('There is nothing to migrate')
            return done

        migrator = self.migrator
        for mname in diff:
            self.run_one(mname, migrator, fake=fake, force=fake)
            done.append(mname)
            if name and name == mname:
                break

        return done

    def rollback(self, name):
        name = name.strip()
        done = self.done
        if not done:
            raise RuntimeError('No migrations are found.')
        if name != done[-1]:
            raise RuntimeError('Only last migration can be canceled.')

        migrator = self.migrator
        self.run_one(name, migrator, False, True)
        self.logger.warn('Downgraded migration: %s', name)


class Router(BaseRouter):

    filemask = re.compile(r"[\d]{3}_[^\.]+\.py$")

    def __init__(self, database, migrate_dir=MIGRATE_DIR, **kwargs):
        super(Router, self).__init__(database, **kwargs)
        self.migrate_dir = migrate_dir

    @property
    def todo(self):
        """Scan migrations in file system."""
        if not os.path.exists(self.migrate_dir):
            self.logger.warn('Migration directory: %s does not exists.', self.migrate_dir)
            os.makedirs(self.migrate_dir)
        return sorted(
            ''.join(f[:-3]) for f in os.listdir(self.migrate_dir) if self.filemask.match(f))

    def create(self, name='auto', migrate='', rollback=''):
        """Create a migration."""
        self.logger.info('Create a migration "%s"', name)
        num = len(self.todo)
        prefix = '{:03}_'.format(num + 1)
        name = prefix + name + '.py'
        path = os.path.join(self.migrate_dir, name)
        with open(path, 'w') as f:
            f.write(MIGRATE_TEMPLATE.format(migrate=migrate, rollback=rollback))

        self.logger.info('Migration has created %s', path)
        return path

    def read(self, name):
        """Read migration from file."""
        with open(os.path.join(self.migrate_dir, name + '.py')) as f:
            code = f.read()
            scope = {}
            exec_in(code, scope)
            return scope.get('migrate', VOID), scope.get('rollback', VOID)


class ModuleRouter(BaseRouter):

    def __init__(self, database, migrate_module='migrations', **kwargs):
        super(ModuleRouter, self).__init__(database, **kwargs)

        if isinstance(migrate_module, StringTypes):
            migrate_module = import_module(migrate_module)

        self.migrate_module = migrate_module

    def read(self, name):
        mod = getattr(self.migrate_module, name)
        return getattr(mod, 'migrate', VOID), getattr(mod, 'rollback', VOID)
