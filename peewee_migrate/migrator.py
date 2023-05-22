"""Run migrations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Union, cast, overload

import peewee as pw
from playhouse.migrate import (
    SQL,
    Context,
    MySQLDatabase,
    Operation,
    PostgresqlDatabase,
    SqliteDatabase,
    make_index_name,
    operation,
)
from playhouse.migrate import MySQLMigrator as MqM
from playhouse.migrate import PostgresqlMigrator as PgM
from playhouse.migrate import SchemaMigrator as ScM
from playhouse.migrate import SqliteMigrator as SqM

from .logs import logger

if TYPE_CHECKING:
    from .types import TModelType, TVModelType


class SchemaMigrator(ScM):
    """Implement migrations."""

    @classmethod
    def from_database(cls, database: Union[pw.Database, pw.Proxy]) -> SchemaMigrator:
        """Initialize migrator by db."""
        if isinstance(database, PostgresqlDatabase):
            return PostgresqlMigrator(database)

        if isinstance(database, SqliteDatabase):
            return SqliteMigrator(database)

        if isinstance(database, MySQLDatabase):
            return MySQLMigrator(database)

        raise ValueError("Unsupported database: %s" % database)

    def drop_table(self, model: TModelType, *, cascade: bool = True) -> Callable[[], Any]:
        """Drop table."""
        return lambda: model.drop_table(cascade=cascade)

    @operation
    def sql(self, sql: str, *params) -> SQL:
        """Execute raw SQL."""
        return SQL(sql, *params)

    @operation
    def change_column(
        self, table: str, column_name: str, field: pw.Field
    ) -> List[Union[Context, Operation]]:
        """Change column."""
        operations: List[Union[Context, Operation]] = self.alter_change_column(
            table, column_name, field
        )
        if not field.null:
            operations.append(self.add_not_null(table, column_name))
        return operations

    @operation
    def add_default(self, table: str, column: str, field: pw.Field):
        default = field.default
        if callable(default):
            default = default()
        alter_column: pw.Context = self._alter_column(self.make_context(), table, column)
        ctx: pw.Context = alter_column.literal(" SET DEFAULT ")
        return ctx.sql(field.db_value(default))

    def alter_change_column(
        self, table: str, column: str, field: pw.Field
    ) -> List[Union[Context, Operation]]:
        """Support change columns."""
        ctx = self.make_context()
        field_null, field.null = field.null, True
        ctx = self._alter_table(ctx, table).literal(" ALTER COLUMN ").sql(field.ddl(ctx))
        field.null = field_null
        return [ctx]

    def alter_add_column(
        self, table: str, column_name: str, field: pw.Field, **kwargs
    ) -> Operation:
        """Fix fieldname for ForeignKeys."""
        name = field.name
        op = super(SchemaMigrator, self).alter_add_column(table, column_name, field, **kwargs)
        if isinstance(field, pw.ForeignKeyField):
            field.name = name
        return op


class MySQLMigrator(SchemaMigrator, MqM):
    """Support MySQL."""

    def alter_change_column(
        self, table: str, column: str, field: pw.Field
    ) -> List[Union[Context, Operation]]:
        """Support change columns."""
        ctx = self.make_context()
        field_null, field.null = field.null, True
        ctx = self._alter_table(ctx, table).literal(" MODIFY COLUMN ").sql(field.ddl(ctx))
        field.null = field_null
        return [ctx]


class PostgresqlMigrator(SchemaMigrator, PgM):
    """Support the migrations in postgresql."""

    def alter_change_column(
        self, table: str, column: str, field: pw.Field
    ) -> List[Union[Context, Operation]]:
        """Support change columns."""
        ctx = self.make_context()
        fn, field.null = field.null, True
        fc, field.constraints = field.constraints, []
        ddl = field.ddl(ctx)
        ddl.nodes.insert(1, pw.SQL("TYPE"))
        ctx = self._alter_table(ctx, table).literal(" ALTER COLUMN ").sql(ddl)
        field.null, field.constraints = fn, fc
        res = [ctx]
        if field.default is not None:
            res.append(self.add_default(table, column, field))
        return res


class SqliteMigrator(SchemaMigrator, SqM):
    """Support the migrations in sqlite."""

    def drop_table(self, model: pw.Model, *, cascade: bool = True) -> Callable:
        """Sqlite doesnt support cascade syntax by default."""
        return lambda: model.drop_table(cascade=False)

    def alter_change_column(
        self, table: str, column: str, field: pw.Field
    ) -> List[Union[Operation, Context]]:
        """Support change columns."""

        def fn(c_name, c_def):
            ctx = self.make_context()
            ctx.sql(field.ddl(ctx))
            return ctx.query()[0]

        return [self._update_column(table, column, fn)]  # type: ignore[]


class ORM:
    __slots__ = ("__tables__", "__models__")

    def __init__(self):
        self.__tables__: Dict[str, TModelType] = {}
        self.__models__: Dict[str, TModelType] = {}

    def add(self, model: TModelType):
        self.__models__[model.__name__] = model
        self.__tables__[model._meta.table_name] = model  # type: ignore[]

    def remove(self, model: TModelType):
        del self.__models__[model.__name__]
        del self.__tables__[model._meta.table_name]  # type: ignore[]

    def __getattr__(self, name: str) -> TModelType:
        return self.__models__[name]

    def __getitem__(self, name: str) -> TModelType:
        return self.__tables__[name]

    def __iter__(self):
        return iter(self.__models__.values())


class Migrator:
    """Provide migrations."""

    def __init__(self, database: Union[pw.Database, pw.Proxy]):
        """Initialize the migrator."""
        self.orm: ORM = ORM()

        if isinstance(database, pw.Proxy):
            database = database.obj

        self.__database__ = database
        self.__ops__: List[Union[Operation, Callable]] = []
        self.__migrator__ = SchemaMigrator.from_database(database)

    def __call__(self):
        """Run operations."""
        for op in self.__ops__:
            if isinstance(op, Operation):
                logger.info("%s %s", op.method, op.args)
                op.run()
            else:
                logger.info("Run %s", op.__name__)
                op()
        self.__ops__ = []

    def __iter__(self):
        """Iterate over models."""
        return iter(self.orm)

    @overload
    def __get_model__(self, model: TVModelType) -> TVModelType:
        ...

    @overload
    def __get_model__(self, model: str) -> TModelType:
        ...

    def __get_model__(self, model: Union[TVModelType, str]) -> Union[TVModelType, TModelType]:
        """Get model by name."""
        if isinstance(model, str):
            if model in self.orm.__models__:
                return self.orm.__models__[model]
            if model in self.orm.__tables__:
                return self.orm[model]

            raise ValueError("Model %s not found" % model)

        return model

    def sql(self, sql: str, *params):
        """Execute raw SQL."""
        op = cast(Operation, self.__migrator__.sql(sql, *params))
        self.__ops__.append(op)

    def python(self, func: Callable, *args, **kwargs):
        """Run a python function."""
        self.__ops__.append(lambda: func(*args, **kwargs))

    def create_table(self, model: TVModelType) -> TVModelType:
        """Create model and table in database.

        >> migrator.create_table(model)
        """
        meta = model._meta  # type: ignore[]
        self.orm.add(model)

        meta.database = self.__database__
        self.__ops__.append(model.create_table)
        return model

    create_model = create_table

    def drop_table(self, model: Union[str, TModelType], *, cascade: bool = True):
        """Drop model and table from database.

        >> migrator.drop_table(model, cascade=True)
        """
        model = self.__get_model__(model)
        self.orm.remove(model)
        self.__ops__.append(self.__migrator__.drop_table(model, cascade=cascade))

    remove_model = drop_table

    def add_columns(self, model: Union[str, TModelType], **fields: pw.Field) -> TModelType:
        """Create new fields."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        for name, field in fields.items():
            meta.add_field(name, field)
            self.__ops__.append(
                self.__migrator__.add_column(  # type: ignore[]
                    meta.table_name, field.column_name, field
                )
            )
            if field.unique:
                self.__ops__.append(
                    self.__migrator__.add_index(meta.table_name, (field.column_name,), unique=True)
                )
        return model

    add_fields = add_columns

    def change_columns(self, model: Union[str, TModelType], **fields: pw.Field) -> TModelType:
        """Change fields."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        for name, field in fields.items():
            old_field = meta.fields.get(name, field)
            old_column_name = old_field and old_field.column_name

            meta.add_field(name, field)

            if isinstance(old_field, pw.ForeignKeyField):
                self.__ops__.append(
                    self.__migrator__.drop_foreign_key_constraint(meta.table_name, old_column_name)
                )

            if old_column_name != field.column_name:
                self.__ops__.append(
                    self.__migrator__.rename_column(
                        meta.table_name, old_column_name, field.column_name
                    )
                )

            if isinstance(field, pw.ForeignKeyField):
                on_delete = field.on_delete if field.on_delete else "RESTRICT"
                on_update = field.on_update if field.on_update else "RESTRICT"
                self.__ops__.append(
                    self.__migrator__.add_foreign_key_constraint(
                        meta.table_name,
                        field.column_name,
                        field.rel_model._meta.table_name,
                        field.rel_field.name,
                        on_delete,
                        on_update,
                    )
                )
                continue

            self.__ops__.append(
                self.__migrator__.change_column(  # type: ignore[]
                    meta.table_name, field.column_name, field
                )
            )

            if field.unique == old_field.unique:
                continue

            if field.unique:
                index = (field.column_name,), field.unique
                self.__ops__.append(self.__migrator__.add_index(meta.table_name, *index))
                meta.indexes.append(index)
            else:
                index = field.column_name
                self.__ops__.append(self.__migrator__.drop_index(meta.table_name, index))
                meta.indexes.remove(((field.column_name,), old_field.unique))

        return model

    change_fields = change_columns

    def drop_columns(
        self, model: Union[str, TModelType], *names: str, cascade: bool = True
    ) -> TModelType:
        """Remove fields from model."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        fields = [field for field in meta.fields.values() if field.name in names]
        for field in fields:
            self.__del_field__(model, field)
            if field.unique:
                index_name = make_index_name(meta.table_name, [field.column_name])
                self.__ops__.append(self.__migrator__.drop_index(meta.table_name, index_name))
            self.__ops__.append(
                self.__migrator__.drop_column(  # type: ignore[]
                    meta.table_name, field.column_name, cascade=cascade
                )
            )
        return model

    remove_fields = drop_columns

    def __del_field__(self, model: TModelType, field: pw.Field):
        """Delete field from model."""
        meta = model._meta  # type: ignore[]
        meta.remove_field(field.name)
        delattr(model, field.name)
        if isinstance(field, pw.ForeignKeyField):
            obj_id_name = field.column_name
            if field.column_name == field.name:
                obj_id_name += "_id"
            if hasattr(model, obj_id_name):
                delattr(model, obj_id_name)
            delattr(field.rel_model, field.backref)

    def rename_column(
        self, model: Union[str, TModelType], old_name: str, new_name: str
    ) -> TModelType:
        """Rename field in model."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        field = meta.fields[old_name]
        if isinstance(field, pw.ForeignKeyField):
            old_name = field.column_name
        self.__del_field__(model, field)
        field.name = field.column_name = new_name
        if isinstance(field, pw.ForeignKeyField):
            field.column_name = field.column_name + "_id"
        meta.add_field(new_name, field)
        self.__ops__.append(
            self.__migrator__.rename_column(meta.table_name, old_name, field.column_name)
        )
        return model

    rename_field = rename_column

    def rename_table(self, model: Union[str, TModelType], new_name: str) -> TModelType:
        """Rename table in database."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        old_name = meta.table_name
        self.orm.remove(model)
        meta.table_name = new_name
        self.orm.add(model)
        self.__ops__.append(self.__migrator__.rename_table(old_name, new_name))
        return model

    def add_index(self, model: Union[str, TModelType], *columns: str, unique=False) -> TModelType:
        """Create indexes."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        meta.indexes.append((columns, unique))
        columns_ = []
        for col in columns:
            field = meta.fields.get(col)

            if len(columns) == 1:
                field.unique = unique
                field.index = not unique

            columns_.append(field.column_name)

        self.__ops__.append(self.__migrator__.add_index(meta.table_name, columns_, unique=unique))
        return model

    def drop_index(self, model: Union[str, TModelType], *columns: str) -> TModelType:
        """Drop indexes."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        columns_ = []
        for col in columns:
            field = meta.fields.get(col)
            if not field:
                continue

            if len(columns) == 1:
                field.unique = field.index = False

            columns_.append(field.column_name)

        index_name = make_index_name(meta.table_name, columns_)
        meta.indexes = [(cols, _) for (cols, _) in meta.indexes if columns != cols]
        self.__ops__.append(self.__migrator__.drop_index(meta.table_name, index_name))
        return model

    def add_not_null(self, model: Union[str, TModelType], *names: str) -> TModelType:
        """Add not null."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        for name in names:
            field = meta.fields[name]
            field.null = False
            self.__ops__.append(self.__migrator__.add_not_null(meta.table_name, field.column_name))
        return model

    def drop_not_null(self, model: Union[str, TModelType], *names: str) -> TModelType:
        """Drop not null."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        for name in names:
            field = meta.fields[name]
            field.null = True
            self.__ops__.append(self.__migrator__.drop_not_null(meta.table_name, field.column_name))
        return model

    def add_default(self, model: Union[str, TModelType], name: str, default: Any) -> TModelType:
        """Add default."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        field = meta.fields[name]
        meta.defaults[field] = field.default = default
        self.__ops__.append(self.__migrator__.apply_default(meta.table_name, name, field))
        return model

    def add_constraint(self, model: Union[str, TModelType], name, constraint):
        """Add constraint."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        self.__ops__.append(self.__migrator__.add_constraint(meta.table_name, name, constraint))
        return model

    def drop_constraints(self, model: Union[str, TModelType], *names: str) -> TModelType:
        """Drop constraints."""
        model = self.__get_model__(model)
        meta = model._meta  # type: ignore[]
        self.__ops__.extend(
            [self.__migrator__.drop_constraint(meta.table_name, name) for name in names]
        )
        return model
