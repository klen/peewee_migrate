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
DEFAULT_MIGRATE_DIR = os.path.join(os.getcwd(), 'migrations')
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
        """Initialize and cache MigrationHistory model."""
        MigrateHistory._meta.database = self.database
        MigrateHistory._meta.db_table = self.migrate_table
        MigrateHistory.create_table(True)
        return MigrateHistory

    @property
    def todo(self):
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

    def create(self, name='auto', auto=False):
        """Create a migration."""
        migrate = rollback = ''
        if auto:
            try:
                models = load_models(auto)
            except ImportError:
                return self.logger.error("Can't import models module: %s", auto)

            for migration in self.diff:
                self.run_one(migration, self.migrator, fake=True)

            migrate = compile_migrations(self.migrator, models)
            if not migrate:
                return self.logger.warn('No changes found.')

            rollback = compile_migrations(self.migrator, models, reverse=True)

        self.logger.info('Creating migration "%s"', name)
        name = self.compile(name, migrate, rollback)
        self.logger.info('Migration has been created as "%s"', name)
        return name

    def merge(self, name='initial'):
        """Merge migrations into one."""
        migrate = compile_migrations(self.migrator, [])
        if not migrate:
            return self.logger.error("Can't merge migrations")

        self.clear()

        self.logger.info('Merge migrations into "%s"', name)
        name = self.compile(name, migrate, '', 0)

        migrator = Migrator(self.database)
        self.run_one(name, migrator, fake=True, force=True)
        self.logger.info('Migrations has been merged into "%s"', name)

    def clear(self):
        """Clear migrations."""
        self.model.delete().execute()

    def compile(self, name, migrate='', rollback='', num=None):
        raise NotImplementedError

    def read(self, name):
        raise NotImplementedError

    def run_one(self, name, migrator, fake=True, downgrade=False, force=False):
        """Run/emulate a migration with given name."""
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

            with self.database.transaction():
                if not downgrade:
                    self.logger.info('Migrate "%s"', name)
                    migrate(migrator, self.database, fake=fake)
                    migrator.run()
                    self.model.create(name=name)
                else:
                    self.logger.info('Rolling back %s', name)
                    rollback(migrator, self.database, fake=fake)
                    migrator.run()
                    self.model.delete().where(self.model.name == name).execute()

                self.logger.info('Done %s', name)

        except Exception as exc:
            self.database.rollback()
            self.logger.exception(exc)
            operation = 'Migration' if not downgrade else 'Rollback'
            self.logger.error('%s failed: %s', operation, name)
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

    def __init__(self, database, migrate_dir=DEFAULT_MIGRATE_DIR, **kwargs):
        super(Router, self).__init__(database, **kwargs)
        self.migrate_dir = migrate_dir

    @property
    def todo(self):
        """Scan migrations in file system."""
        if not os.path.exists(self.migrate_dir):
            self.logger.warn('Migration directory: %s does not exist.', self.migrate_dir)
            os.makedirs(self.migrate_dir)
        return sorted(f[:-3] for f in os.listdir(self.migrate_dir) if self.filemask.match(f))

    def compile(self, name, migrate='', rollback='', num=None):
        """Create a migration."""
        if num is None:
            num = len(self.todo)

        name = '{:03}_'.format(num + 1) + name
        filename = name + '.py'
        path = os.path.join(self.migrate_dir, filename)
        with open(path, 'w') as f:
            f.write(MIGRATE_TEMPLATE.format(migrate=migrate, rollback=rollback, name=filename))

        return name

    def read(self, name):
        """Read migration from file."""
        with open(os.path.join(self.migrate_dir, name + '.py')) as f:
            code = f.read()
            scope = {}
            exec_in(code, scope)
            return scope.get('migrate', VOID), scope.get('rollback', VOID)

    def clear(self):
        """Remove migrations from fs."""
        super(Router, self).clear()
        for name in self.todo:
            os.remove(name + '.py')


class ModuleRouter(BaseRouter):

    def __init__(self, database, migrate_module='migrations', **kwargs):
        super(ModuleRouter, self).__init__(database, **kwargs)

        if isinstance(migrate_module, string_types):
            migrate_module = import_module(migrate_module)

        self.migrate_module = migrate_module

    def read(self, name):
        mod = getattr(self.migrate_module, name)
        return getattr(mod, 'migrate', VOID), getattr(mod, 'rollback', VOID)


def load_models(module):
    """Load models from given module."""
    if isinstance(module, string_types):
        module = import_module(module)

    if isinstance(module, ModuleType):
        return list(filter(
            lambda m: isinstance(m, type) and issubclass(m, pw.Model),
            (getattr(module, model) for model in dir(auto))))  # noqa

    return module


def compile_migrations(migrator, models, reverse=False):
    """Compile migrations for given models."""
    source = migrator.orm.values()
    if reverse:
        source, models = models, source

    migrations = diff_many(source, models, migrator, reverse=reverse)
    if not migrations:
        return False

    migrations = NEWLINE + NEWLINE.join('\n\n'.join(migrations).split('\n'))
    return CLEAN_RE.sub('\n', migrations)
