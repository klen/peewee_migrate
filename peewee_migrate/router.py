"""Migration router."""
from __future__ import annotations

import os
import pkgutil
import re
import sys
from functools import cached_property
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Final, Iterable, List, Optional, Set, Type, Union
from unittest import mock

import peewee as pw

from .auto import NEWLINE, diff_many
from .logs import logger
from .migrator import Migrator
from .models import MIGRATE_TABLE, MigrateHistory
from .template import TEMPLATE

if TYPE_CHECKING:
    from logging import Logger

    from peewee_migrate.types import TModelType


CLEAN_RE: Final = re.compile(r"\s+$", re.M)
CURDIR: Final = Path.cwd()
DEFAULT_MIGRATE_DIR: Final = CURDIR / "migrations"


def void(m, d, fake=None):
    return None


class BaseRouter(object):
    """Abstract base class for router."""

    def __init__(  # noqa: PLR0913
        self,
        database: Union[pw.Database, pw.Proxy],
        migrate_table=MIGRATE_TABLE,
        ignore: Optional[Iterable[str]] = None,
        schema: Optional[str] = None,
        logger: Logger = logger,
        migrator_class: Type[Migrator] = Migrator,
    ):
        """Initialize the router."""
        self.database = database
        self.migrate_table = migrate_table
        self.schema = schema
        self.ignore = ignore
        self.logger = logger
        self.migrator_class = migrator_class
        if not isinstance(self.database, (pw.Database, pw.Proxy)):
            raise TypeError("Invalid database: %s" % database)
        if not issubclass(self.migrator_class, Migrator):
            raise TypeError("Invalid migrator_class: %s" % database)

    @cached_property
    def model(self) -> Type[MigrateHistory]:
        """Initialize and cache MigrationHistory model."""
        meta = MigrateHistory._meta  # type: ignore[]
        meta.database = self.database
        meta.table_name = self.migrate_table
        meta.schema = self.schema
        MigrateHistory.create_table(safe=True)
        return MigrateHistory

    @property
    def todo(self) -> Iterable[str]:
        """Get migrations to run."""
        raise NotImplementedError

    @property
    def done(self) -> List[str]:
        """Scan migrations in database."""
        return [mm.name for mm in self.model.select().order_by(self.model.id)]

    @property
    def diff(self) -> List[str]:
        """Calculate difference between fs and db."""
        done = set(self.done)
        return [name for name in self.todo if name not in done]

    @cached_property
    def migrator(self) -> Migrator:
        """Create migrator and setup it with fake migrations."""
        migrator = self.migrator_class(self.database)
        for name in self.done:
            self.run_one(name, migrator)
        return migrator

    def create(self, name: str = "auto", *, auto: Any = False) -> Optional[str]:
        """Create a migration.

        :param auto: Python module path to scan for models.
        """
        migrate = rollback = ""
        if auto:
            # Need to append the CURDIR to the path for import to work.
            sys.path.append(f"{ CURDIR }")
            models = auto if isinstance(auto, list) else [auto]
            if not all(_check_model(m) for m in models):
                try:
                    modules = models
                    if isinstance(auto, bool):
                        modules = [
                            m for _, m, ispkg in pkgutil.iter_modules([f"{CURDIR}"]) if ispkg
                        ]
                    models = [m for module in modules for m in load_models(module)]

                except ImportError:
                    self.logger.exception("Can't import models module: %s", auto)
                    return None

            if self.ignore:
                models = [m for m in models if m._meta.name not in self.ignore]  # type: ignore[]

            for migration in self.diff:
                self.run_one(migration, self.migrator, fake=True)

            migrate = compile_migrations(self.migrator, models)
            if not migrate:
                self.logger.warning("No changes found.")
                return None

            rollback = compile_migrations(self.migrator, models, reverse=True)

        self.logger.info('Creating migration "%s"', name)
        name = self.compile(name, migrate, rollback)
        self.logger.info('Migration has been created as "%s"', name)
        return name

    def merge(self, name: str = "initial"):
        """Merge migrations into one."""
        migrator = Migrator(self.database)
        migrate = compile_migrations(migrator, list(self.migrator.orm))
        if not migrate:
            return self.logger.error("Can't merge migrations")

        self.clear()

        self.logger.info('Merge migrations into "%s"', name)
        rollback = compile_migrations(self.migrator, [])
        name = self.compile(name, migrate, rollback, 0)

        migrator = Migrator(self.database)
        self.run_one(name, migrator, fake=True, force=True)
        self.logger.info('Migrations has been merged into "%s"', name)
        return None

    def clear(self):
        """Clear migrations."""
        self.model.delete().execute()

    def compile(  # noqa: A003
        self, name: str, migrate: str = "", rollback: str = "", num: Optional[int] = None
    ) -> str:
        """Create a migration."""
        raise NotImplementedError

    def read(self, name: str):
        """Read migration from file."""
        raise NotImplementedError

    def run_one(  # noqa: PLR0913
        self,
        name: str,
        migrator: Migrator,
        *,
        fake: bool = True,
        downgrade: bool = False,
        force: bool = False,
    ) -> str:
        """Run/emulate a migration with given name."""
        try:
            migrate, rollback = self.read(name)
            if fake:
                mocked_cursor = mock.Mock()
                mocked_cursor.fetch_one.return_value = None
                with mock.patch("peewee.Model.select"), mock.patch(
                    "peewee.Database.execute_sql", return_value=mocked_cursor
                ):
                    migrate(migrator, self.database, fake=fake)

                if force:
                    self.model.create(name=name)
                    self.logger.info("Done %s", name)

                migrator.__ops__ = []
                return name

            with self.database.transaction():
                if not downgrade:
                    self.logger.info('Migrate "%s"', name)
                    migrate(migrator, self.database, fake=fake)
                    migrator()
                    self.model.create(name=name)
                else:
                    self.logger.info("Rolling back %s", name)
                    rollback(migrator, self.database, fake=fake)
                    migrator()
                    self.model.delete().where(self.model.name == name).execute()

                self.logger.info("Done %s", name)
                return name

        except Exception:
            self.database.rollback()
            operation = "Migration" if not downgrade else "Rollback"
            self.logger.exception("%s failed: %s", operation, name)
            raise

    def run(self, name: Optional[str] = None, *, fake: bool = False) -> List[str]:
        """Run migrations."""
        self.logger.info("Starting migrations")

        done: List[str] = []
        diff = self.diff
        if not diff:
            self.logger.info("There is nothing to migrate")
            return done

        migrator = self.migrator
        for mname in diff:
            done.append(self.run_one(mname, migrator, fake=fake, force=fake))
            if name and name == mname:
                break

        return done

    def rollback(self):
        """Rollback the latest migration."""
        done = self.done
        if not done:
            msg = "There is nothing to rollback"
            raise RuntimeError(msg)

        name = done[-1]
        migrator = self.migrator
        self.run_one(name, migrator, fake=False, downgrade=True)
        self.logger.warning("Downgraded migration: %s", name)


class Router(BaseRouter):
    """File system router."""

    filemask = re.compile(r"[\d]{3}_[^\.]+\.py$")

    def __init__(
        self,
        database,
        migrate_dir: Optional[Union[str, Path]] = None,
        **kwargs,
    ):
        """Initialize the router."""
        super(Router, self).__init__(database, **kwargs)
        if migrate_dir is None:
            migrate_dir = DEFAULT_MIGRATE_DIR
        elif isinstance(migrate_dir, str):
            migrate_dir = Path(migrate_dir)
        self.migrate_dir = migrate_dir

    @property
    def todo(self):
        """Scan migrations in file system."""
        if not self.migrate_dir.exists():
            self.logger.warning("Migration directory: %s does not exist.", self.migrate_dir)
            self.migrate_dir.mkdir(parents=True)
        return sorted(f[:-3] for f in os.listdir(self.migrate_dir) if self.filemask.match(f))

    def compile(self, name, migrate="", rollback="", num=None) -> str:  # noqa: A003
        """Create a migration."""
        if num is None:
            num = len(self.todo)

        name = "{:03}_".format(num + 1) + name
        filename = name + ".py"
        path = self.migrate_dir / filename
        with path.open("w") as f:
            f.write(TEMPLATE.format(migrate=migrate, rollback=rollback, name=filename))

        return name

    def read(self, name):
        """Read migration from file."""
        path = self.migrate_dir / (name + ".py")
        with path.open("r") as f:
            code = f.read()
            scope = {}
            code = compile(code, "<string>", "exec", dont_inherit=True)
            exec(code, scope, None)
            return scope.get("migrate", void), scope.get("rollback", void)

    def clear(self):
        """Remove migrations from fs."""
        super(Router, self).clear()
        for name in self.todo:
            path = self.migrate_dir / (name + ".py")
            path.unlink()


class ModuleRouter(BaseRouter):
    """Module based router."""

    def __init__(self, database, migrate_module="migrations", **kwargs):
        """Initialize the router."""
        super(ModuleRouter, self).__init__(database, **kwargs)

        if isinstance(migrate_module, str):
            migrate_module = import_module(migrate_module)

        self.migrate_module = migrate_module

    def read(self, name):
        """Read migrations from a module."""
        mod = getattr(self.migrate_module, name)
        return getattr(mod, "migrate", void), getattr(mod, "rollback", void)


def load_models(module: Union[str, ModuleType]) -> Set[Type[pw.Model]]:
    """Load models from given module."""

    modules = [module] if isinstance(module, ModuleType) else _import_submodules(module)
    return {
        m
        for module in modules
        for m in filter(_check_model, (getattr(module, name) for name in dir(module)))
    }


def _import_submodules(package, passed=...):
    if passed is ...:
        passed = set()

    if isinstance(package, str):
        package = import_module(package)

    # https://github.com/klen/peewee_migrate/issues/125
    if not hasattr(package, "__path__"):
        return {package}

    modules = []
    if set(package.__path__) & passed:
        return modules

    passed |= set(package.__path__)

    for loader, name, is_pkg in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        spec = loader.find_spec(name, None)
        if spec is None or spec.loader is None:
            continue
        module = spec.loader.load_module(name)
        modules.append(module)
        if is_pkg:
            modules += _import_submodules(module)
    return modules


def _check_model(obj):
    """Check object if it's a peewee model and unique."""
    return isinstance(obj, type) and issubclass(obj, pw.Model) and hasattr(obj, "_meta")


def compile_migrations(migrator: Migrator, models: List[TModelType], *, reverse=False) -> str:
    """Compile migrations for given models."""
    source = list(migrator.orm)
    if reverse:
        source, models = models, source

    migrations = diff_many(models, source, migrator, reverse=reverse)
    if not migrations:
        return ""

    code = NEWLINE + NEWLINE.join("\n\n".join(migrations).split("\n"))
    return CLEAN_RE.sub("\n", code)
