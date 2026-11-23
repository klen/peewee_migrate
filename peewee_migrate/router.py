"""Migration router."""

from __future__ import annotations

import pkgutil
import re
import sys
import time
import zlib
from contextlib import contextmanager
from functools import cached_property
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Final, cast
from unittest import mock

import peewee as pw
from playhouse.migrate import MySQLDatabase, PostgresqlDatabase

from .auto import NEWLINE, diff_many
from .logs import logger
from .migrator import Migrator
from .models import MIGRATE_TABLE, MigrateHistory
from .template import TEMPLATE

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable
    from logging import Logger

    from peewee_migrate.types import TAuto, TMigration, TModelType


CLEAN_RE: Final = re.compile(r"\s+$", re.MULTILINE)
LOCK_TIMEOUT: Final = 60


def void(m: Migrator, d: pw.Database, fake: bool | None = None) -> None:  # noqa: FBT001
    return None


@contextmanager
def lock_migrations(database: pw.Database | pw.Proxy, table: str) -> Generator[None]:
    """Keep other processes out of the migration run (Postgres and MySQL only).

    Waits up to LOCK_TIMEOUT seconds for another process to finish migrating. Sqlite has
    no advisory lock, and holding one transaction for the whole run would disable the
    `foreign_keys` pragma used by the migrator; the unique history name stays the guard
    there.
    """
    db = database.obj if isinstance(database, pw.Proxy) else database
    if isinstance(db, PostgresqlDatabase):
        key = zlib.crc32(table.encode())
        deadline = time.monotonic() + LOCK_TIMEOUT
        while True:
            locked = db.execute_sql("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone()
            if locked and locked[0]:
                break
            if time.monotonic() >= deadline:
                msg = "Could not acquire the migration lock in %s seconds" % LOCK_TIMEOUT
                raise RuntimeError(msg)
            time.sleep(1)
        try:
            yield
        finally:
            db.execute_sql("SELECT pg_advisory_unlock(%s)", (key,))
    elif isinstance(db, MySQLDatabase):
        # GET_LOCK is server-wide, so the database name has to be part of the lock name.
        lock_name = f"{db.database}:{table}"
        locked = db.execute_sql("SELECT GET_LOCK(%s, %s)", (lock_name, LOCK_TIMEOUT)).fetchone()
        if not locked or locked[0] != 1:
            msg = "Could not acquire the migration lock in %s seconds" % LOCK_TIMEOUT
            raise RuntimeError(msg)
        try:
            yield
        finally:
            db.execute_sql("SELECT RELEASE_LOCK(%s)", (lock_name,))
    else:
        yield


class BaseRouter(object):
    """Abstract base class for router."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        database: pw.Database | pw.Proxy,
        migrate_table: str = MIGRATE_TABLE,
        ignore: Iterable[str] | None = None,
        schema: str | None = None,
        logger: Logger = logger,
        migrator_class: type[Migrator] = Migrator,
    ) -> None:
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
    def model(self) -> type[MigrateHistory]:
        """Initialize and cache a MigrationHistory model for this router's database."""
        # A subclass per router: binding the shared MigrateHistory would send every
        # router's history to whichever database was bound last.
        model: type[MigrateHistory] = type(MigrateHistory.__name__, (MigrateHistory,), {})
        meta = model._meta
        meta.database = self.database
        meta.table_name = self.migrate_table
        meta.schema = self.schema
        model.create_table(safe=True)
        return model

    @property
    def todo(self) -> Iterable[str]:
        """Get migrations to run."""
        raise NotImplementedError

    @property
    def done(self) -> list[str]:
        """Scan migrations in database."""
        return [mm.name for mm in self.model.select().order_by(self.model.id)]

    @property
    def diff(self) -> list[str]:
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

    def create(self, name: str = "auto", *, auto: TAuto = False) -> str | None:
        """Create a migration.

        :param auto: Python module path to scan for models.
        """
        migrate = rollback = ""
        if auto:
            # Local packages have to be importable for autodiscovery to work.
            curdir = f"{Path.cwd()}"
            if curdir not in sys.path:
                sys.path.append(curdir)
            models: list[Any] = auto if isinstance(auto, list) else [auto]
            if not all(_check_model(m) for m in models):
                try:
                    modules = models
                    if isinstance(auto, bool):
                        modules = [
                            m for _, m, ispkg in pkgutil.iter_modules([f"{Path.cwd()}"]) if ispkg
                        ]
                    models = [m for module in modules for m in load_models(module)]

                except ImportError:
                    self.logger.exception("Can't import models module: %s", auto)
                    return None

            if self.ignore:
                models = [m for m in models if m._meta.name not in self.ignore]

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

    def merge(self, name: str = "initial") -> None:
        """Merge migrations into one."""
        with lock_migrations(self.database, self.migrate_table):
            migrator = Migrator(self.database)
            migrate = compile_migrations(migrator, list(self.migrator.orm))
            if not migrate:
                return self.logger.error("Can't merge migrations")

            self.logger.info('Merge migrations into "%s"', name)
            rollback = compile_migrations(self.migrator, [])
            name = self.compile(name, migrate, rollback, 0)

            # Write the merged migration before dropping the old ones.
            self.clear(keep=name)

            migrator = Migrator(self.database)
            self.run_one(name, migrator, fake=True, force=True)
            self.logger.info('Migrations has been merged into "%s"', name)
            return None

    def clear(self, keep: str | None = None) -> None:
        """Clear migrations."""
        delete = self.model.delete()  # type: ignore[not-callable]
        delete.execute()

    def compile(
        self, name: str, migrate: str = "", rollback: str = "", num: int | None = None
    ) -> str:
        """Create a migration."""
        raise NotImplementedError

    def read(self, name: str) -> tuple[TMigration, TMigration]:
        """Read migration from file."""
        raise NotImplementedError

    def run_one(
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
                with (
                    mock.patch("peewee.Model.select"),
                    mock.patch("peewee.Database.execute_sql", return_value=mocked_cursor),
                ):
                    migrate(migrator, self.database, fake=fake)

                if force:
                    self.model.create(name=name)
                    self.logger.info("Done %s", name)

                migrator.reset()
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
                    delete = self.model.delete()  # type: ignore[not-callable]
                    delete.where(self.model.name == name).execute()

                self.logger.info("Done %s", name)
                return name

        except Exception:
            operation = "Migration" if not downgrade else "Rollback"
            self.logger.exception("%s failed: %s", operation, name)
            raise

    def run(self, name: str | None = None, *, fake: bool = False) -> list[str]:
        """Run migrations."""
        self.logger.info("Starting migrations")

        with lock_migrations(self.database, self.migrate_table):
            done: list[str] = []
            diff = self.diff
            if name and name not in diff:
                raise ValueError("Migration %s is not pending" % name)

            if not diff:
                self.logger.info("There is nothing to migrate")
                return done

            migrator = self.migrator
            for mname in diff:
                done.append(self.run_one(mname, migrator, fake=fake, force=fake))
                if name and name == mname:
                    break

            return done

    def rollback(self) -> None:
        """Rollback the latest migration."""
        with lock_migrations(self.database, self.migrate_table):
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

    filemask = re.compile(r"\d+_[^.]+\.py$")

    def __init__(
        self,
        database: pw.Database | pw.Proxy,
        migrate_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the router."""
        super(Router, self).__init__(database, **kwargs)
        if isinstance(migrate_dir, str):
            migrate_dir = Path(migrate_dir)
        self.migrate_dir = migrate_dir or Path.cwd() / "migrations"

    @property
    def todo(self) -> list[str]:
        """Scan migrations in file system."""
        if not self.migrate_dir.exists():
            self.logger.warning("Migration directory: %s does not exist.", self.migrate_dir)
            self.migrate_dir.mkdir(parents=True, exist_ok=True)
        return sorted(
            (f.stem for f in Path.iterdir(self.migrate_dir) if self.filemask.match(f.name)),
            key=lambda name: int(name.split("_", 1)[0]),
        )

    def compile(
        self, name: str, migrate: str = "", rollback: str = "", num: int | None = None
    ) -> str:
        """Create a migration."""
        if num is None:
            num = max((int(name.split("_", 1)[0]) for name in self.todo), default=0)

        name = "{:03}_".format(num + 1) + name
        filename = name + ".py"
        path = self.migrate_dir / filename
        with path.open("w", encoding="utf-8") as f:
            f.write(TEMPLATE.format(migrate=migrate, rollback=rollback, name=filename))

        return name

    def read(self, name: str) -> tuple[TMigration, TMigration]:
        """Read migration from file."""
        path = self.migrate_dir / (name + ".py")
        with path.open("r") as f:
            code = f.read()
            scope = {}
            code = compile(code, "<string>", "exec", dont_inherit=True)
            exec(code, scope, None)
            return scope.get("migrate", void), scope.get("rollback", void)

    def clear(self, keep: str | None = None) -> None:
        """Remove migrations from fs."""
        for name in self.todo:
            if name != keep:
                (self.migrate_dir / (name + ".py")).unlink()
        super(Router, self).clear()


class ModuleRouter(BaseRouter):
    """Module based router."""

    def __init__(
        self,
        database: pw.Database | pw.Proxy,
        migrate_module: str | ModuleType = "migrations",
        **kwargs: Any,
    ) -> None:
        """Initialize the router."""
        super(ModuleRouter, self).__init__(database, **kwargs)

        if isinstance(migrate_module, str):
            migrate_module = import_module(migrate_module)

        self.migrate_module = migrate_module

    def read(self, name: str) -> tuple[TMigration, TMigration]:
        """Read migrations from a module."""
        mod = getattr(self.migrate_module, name)
        return getattr(mod, "migrate", void), getattr(mod, "rollback", void)


def load_models(module: str | ModuleType) -> set[TModelType]:
    """Load models from given module."""

    modules = [module] if isinstance(module, ModuleType) else _import_submodules(module)
    return cast(
        "set[TModelType]",
        {
            m
            for module in modules
            for m in filter(_check_model, (getattr(module, name) for name in dir(module)))
        },
    )


def _import_submodules(
    package: str | ModuleType, passed: set[str] | None = None
) -> list[ModuleType]:
    if passed is None:
        passed = set()

    if isinstance(package, str):
        package = import_module(package)

    if not hasattr(package, "__path__"):
        return [package]

    path_ids = set(map(str, package.__path__))
    if passed & path_ids:
        return []
    passed |= path_ids

    modules: list[ModuleType] = [package]
    prefix = package.__name__ + "."

    for _finder, name, is_pkg in pkgutil.walk_packages(package.__path__, prefix):
        try:
            module = import_module(name)
        except ImportError:
            continue

        modules.append(module)
        if is_pkg:
            modules.extend(_import_submodules(module, passed))

    return modules


def _check_model(obj: object) -> bool:
    """Check object if it's a peewee model and unique."""
    return isinstance(obj, type) and issubclass(obj, pw.Model) and hasattr(obj, "_meta")


def compile_migrations(
    migrator: Migrator, models: list[TModelType], *, reverse: bool = False
) -> str:
    """Compile migrations for given models."""
    source = list(migrator.orm)
    if reverse:
        source, models = models, source

    migrations = diff_many(models, source, migrator, reverse=reverse)
    if not migrations:
        return ""

    code = NEWLINE + NEWLINE.join("\n\n".join(migrations).split("\n"))
    return CLEAN_RE.sub("\n", code)
