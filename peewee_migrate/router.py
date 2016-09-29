import os
import re
from importlib import import_module
from types import ModuleType

import mock
import peewee as pw
from cached_property import cached_property

from peewee_migrate import LOGGER, MigrateHistory
from peewee_migrate.auto import diff_many, NEWLINE
from peewee_migrate.compat import string_types, exec_in
from peewee_migrate.migrator import Migrator


CLEAN_RE = re.compile(r'\s+$', re.M)
MIGRATE_DIR = os.path.join(os.getcwd(), 'migrations')
VOID = lambda m, d: None # noqa
with open(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'template.txt')) as t:
    MIGRATE_TEMPLATE = t.read()


class BaseRouter(object):

    """Abstract base class for router."""

    def __init__(self, database, migrate_table='migratehistory', logger=LOGGER):
        self.database = database
        self.migrate_table = migrate_table
        self.logger = logger
        if not isinstance(self.database, (pw.Database, pw.Proxy)):
            raise RuntimeError('Invalid database: %s' % database)

    @cached_property
    def model(self):
        """Ensure that migrations has prepared to run."""
        # Initialize MigrationHistory model
        MigrateHistory._meta.database = self.database
        MigrateHistory._meta.db_table = self.migrate_table
        MigrateHistory.create_table(True)
        return MigrateHistory

    @property
    def todo(self):
        raise NotImplementedError

    def create(self, name='auto', auto=False):
        """Create a migration."""
        migrate = rollback = ''
        if auto:
            if isinstance(auto, string_types):
                try:
                    auto = import_module(auto)
                except ImportError:
                    return self.logger.error("Can't import models module: %s", auto)

            if isinstance(auto, ModuleType):
                auto = list(filter(
                    lambda m: isinstance(m, type) and issubclass(m, pw.Model),
                    (getattr(auto, model) for model in dir(auto))))  # noqa

            for migration in self.diff:
                self.run_one(migration, self.migrator)

            models1 = auto
            models2 = list(self.migrator.orm.values())

            migrate = diff_many(models1, models2, migrator=self.migrator)
            if not migrate:
                return self.logger.warn('No changes found.')

            migrate = NEWLINE + NEWLINE.join('\n\n'.join(migrate).split('\n'))
            migrate = CLEAN_RE.sub('\n', migrate)

            rollback = diff_many(models2, models1, migrator=self.migrator, reverse=True)
            rollback = NEWLINE + NEWLINE.join('\n\n'.join(rollback).split('\n'))
            rollback = CLEAN_RE.sub('\n', rollback)

        self.logger.info('Creating migration "%s"', name)
        path = self._create(name, migrate, rollback)
        self.logger.info('Migration created %s', path)
        return path

    def _create(self, name, migrate='', rollback=''):
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

    @cached_property
    def migrator(self):
        """Create migrator and setup it with fake migrations."""
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
                    with mock.patch('peewee.Query._execute'):
                        migrate(migrator, self.database, fake=fake)

                if force:
                    self.model.create(name=name)
                    self.logger.info('Done %s', name)

                migrator.clean()
                return migrator

            self.logger.info('Running "%s"', name)
            with self.database.transaction():
                if not downgrade:
                    migrate(migrator, self.database, fake=fake)
                    migrator.run()
                    self.model.create(name=name)
                    self.logger.info('Done %s', name)
                else:
                    self.logger.info('Rolling back %s', name)
                    rollback(migrator, self.database, fake=fake)
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
        self.logger.info('Starting migrations')

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
            self.logger.warn('Migration directory: %s does not exist.', self.migrate_dir)
            os.makedirs(self.migrate_dir)
        return sorted(
            ''.join(f[:-3]) for f in os.listdir(self.migrate_dir) if self.filemask.match(f))

    def _create(self, name, migrate='', rollback=''):
        """Create a migration."""
        num = len(self.todo)
        prefix = '{:03}_'.format(num + 1)
        name = prefix + name + '.py'
        path = os.path.join(self.migrate_dir, name)
        with open(path, 'w') as f:
            f.write(MIGRATE_TEMPLATE.format(migrate=migrate, rollback=rollback))

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

        if isinstance(migrate_module, string_types):
            migrate_module = import_module(migrate_module)

        self.migrate_module = migrate_module

    def read(self, name):
        mod = getattr(self.migrate_module, name)
        return getattr(mod, 'migrate', VOID), getattr(mod, 'rollback', VOID)
