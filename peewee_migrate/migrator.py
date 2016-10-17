import peewee as pw
from playhouse.migrate import (
    MySQLMigrator as MqM,
    PostgresqlMigrator as PgM,
    SchemaMigrator as ScM,
    SqliteMigrator as SqM,
    Operation, SQL, Entity, Clause, PostgresqlDatabase, operation, SqliteDatabase, MySQLDatabase
)

from peewee_migrate import LOGGER


class SchemaMigrator(ScM):

    """Implement migrations."""

    @classmethod
    def from_database(cls, database):
        """Initialize migrator by db."""
        if isinstance(database, PostgresqlDatabase):
            return PostgresqlMigrator(database)
        if isinstance(database, SqliteDatabase):
            return SqliteMigrator(database)
        if isinstance(database, MySQLDatabase):
            return MySQLMigrator(database)
        return super(SchemaMigrator, cls).from_database(database)

    def drop_table(self, model, cascade=True):
        return lambda: model.drop_table(cascade=cascade)

    @operation
    def change_column(self, table, column_name, field):
        """Change column."""
        operations = [self.alter_change_column(table, column_name, field)]
        if not field.null:
            operations.extend([self.add_not_null(table, column_name)])
        return operations

    def alter_change_column(self, table, column, field):
        """Support change columns."""
        field_null, field.null = field.null, True
        field_clause = self.database.compiler().field_definition(field)
        field.null = field_null
        return Clause(SQL('ALTER TABLE'), Entity(table), SQL('ALTER COLUMN'), field_clause)

    @operation
    def sql(self, sql, *params):
        """Execute raw SQL."""
        return Clause(SQL(sql, *params))

    @operation
    def alter_add_column(self, table, column_name, field):
        """Keep fieldname unchanged."""
        # Make field null at first.
        field_null, field.null = field.null, True
        field.db_column = column_name
        field_clause = self.database.compiler().field_definition(field)
        field.null = field_null
        parts = [
            SQL('ALTER TABLE'),
            Entity(table),
            SQL('ADD COLUMN'),
            field_clause]
        if isinstance(field, pw.ForeignKeyField):
            parts.extend(self.get_inline_fk_sql(field))
        else:
            field.name = column_name
        return Clause(*parts)


class MySQLMigrator(SchemaMigrator, MqM):

    """Support the migrations in MySQL."""

    def alter_change_column(self, table, column_name, field):
        """Support change columns."""
        clause = super(MySQLMigrator, self).alter_change_column(table, column_name, field)
        field_clause = clause.nodes[-1]
        field_clause.nodes.insert(1, SQL('TYPE'))
        return clause


class PostgresqlMigrator(SchemaMigrator, PgM):

    """Support the migrations in postgresql."""

    def alter_change_column(self, table, column_name, field):
        """Support change columns."""
        clause = super(PostgresqlMigrator, self).alter_change_column(table, column_name, field)
        field_clause = clause.nodes[-1]
        field_clause.nodes.insert(1, SQL('TYPE'))
        return clause


class SqliteMigrator(SchemaMigrator, SqM):

    """Support the migrations in sqlite."""

    def drop_table(self, model, cascade=True):
        """SQLite doesnt support cascade syntax by default."""
        return lambda: model.drop_table(cascade=False)

    def alter_change_column(self, table, column, field):
        """Support change columns."""
        def _change(column_name, column_def):
            compiler = self.database.compiler()
            clause = compiler.field_definition(field)
            sql, _ = compiler.parse_node(clause)
            return sql
        return self._update_column(table, column, _change)


def get_model(method):
    """Convert string to model class."""
    def wrapper(migrator, model, *args, **kwargs):
        if isinstance(model, str):
            return method(migrator, migrator.orm[model], *args, **kwargs)
        return method(migrator, model, *args, **kwargs)
    return wrapper


class Migrator(object):

    """Provide migrations."""

    def __init__(self, database):
        """Initialize the migrator."""
        if isinstance(database, pw.Proxy):
            database = database.obj

        self.database = database
        self.orm = dict()
        self.ops = list()
        self.migrator = SchemaMigrator.from_database(self.database)

    def run(self):
        """Run operations."""
        for opn in self.ops:
            if isinstance(opn, Operation):
                LOGGER.info("%s %s", opn.method, opn.args)
                opn.run()
            else:
                opn()
        self.clean()

    def python(self, func, *args, **kwargs):
        """Run python code."""
        self.ops.append(lambda: func(*args, **kwargs))

    def sql(self, sql, *params):
        """Execure raw SQL."""
        self.ops.append(self.migrator.sql(sql, *params))

    def clean(self):
        """Clean the operations."""
        self.ops = list()

    def create_table(self, model):
        """Create model and table in database.

        >> migrator.create_table(model)
        """
        self.orm[model._meta.db_table] = model
        model._meta.database = self.database
        self.ops.append(model.create_table)
        return model

    create_model = create_table

    @get_model
    def drop_table(self, model, cascade=True):
        """Drop model and table from database.

        >> migrator.drop_table(model, cascade=True)
        """
        del self.orm[model._meta.db_table]
        self.ops.append(self.migrator.drop_table(model, cascade))

    remove_model = drop_table

    @get_model
    def add_columns(self, model, **fields):
        """Create new fields."""
        for name, field in fields.items():
            field.add_to_class(model, name)
            self.ops.append(self.migrator.add_column(model._meta.db_table, field.db_column, field))
            if field.unique:
                self.ops.append(self.migrator.add_index(
                    model._meta.db_table, (field.db_column,), unique=True))
        return model

    add_fields = add_columns

    @get_model
    def change_columns(self, model, **fields):
        """Change fields."""
        for name, field in fields.items():
            field.add_to_class(model, name)
            self.ops.append(self.migrator.change_column(
                model._meta.db_table, field.db_column, field))
            if field.unique:
                self.ops.append(self.migrator.add_index(
                    model._meta.db_table, (field.db_column,), unique=True))
        return model

    change_fields = change_columns

    @get_model
    def drop_columns(self, model, *names, **kwargs):
        """Remove fields from model."""
        fields = [field for field in model._meta.fields.values() if field.name in names]
        cascade = kwargs.pop('cascade', True)
        for field in fields:
            self.__del_field__(model, field)
            if field.unique:
                compiler = self.database.compiler()
                index_name = compiler.index_name(model._meta.db_table, (field.db_column,))
                self.ops.append(self.migrator.drop_index(model._meta.db_table, index_name))
            self.ops.append(
                self.migrator.drop_column(model._meta.db_table, field.db_column, cascade=cascade))
        return model

    remove_fields = drop_columns

    def __del_field__(self, model, field):
        """Delete field from model."""
        model._meta.remove_field(field.name)
        delattr(model, field.name)
        if isinstance(field, pw.ForeignKeyField):
            delattr(field.rel_model, field.related_name)
            del field.rel_model._meta.reverse_rel[field.related_name]

    @get_model
    def rename_column(self, model, old_name, new_name):
        """Rename field in model."""
        field = model._meta.fields[old_name]
        if isinstance(field, pw.ForeignKeyField):
            old_name = field.db_column
        self.__del_field__(model, field)
        field.name = field.db_column = new_name
        field.add_to_class(model, new_name)
        if isinstance(field, pw.ForeignKeyField):
            field.db_column = new_name = field.db_column + '_id'
        self.ops.append(self.migrator.rename_column(model._meta.db_table, old_name, new_name))
        return model

    rename_field = rename_column

    @get_model
    def rename_table(self, model, new_name):
        """Rename table in database."""
        del self.orm[model._meta.db_table]
        model._meta.db_table = new_name
        self.orm[model._meta.db_table] = model
        self.ops.append(self.migrator.rename_table(model._meta.db_table, new_name))
        return model

    @get_model
    def add_index(self, model, *columns, **kwargs):
        """Create indexes."""
        unique = kwargs.pop('unique', False)
        model._meta.indexes.append((columns, unique))
        columns_ = []
        for col in columns:
            field = model._meta.fields.get(col)
            if isinstance(field, pw.ForeignKeyField):
                col = col + '_id'
            columns_.append(col)
        self.ops.append(self.migrator.add_index(model._meta.db_table, columns_, unique=unique))
        return model

    @get_model
    def drop_index(self, model, *columns):
        """Drop indexes."""
        columns_ = []
        for col in columns:
            field = model._meta.fields.get(col)
            if isinstance(field, pw.ForeignKeyField):
                col = col + '_id'
            columns_.append(col)
        index_name = self.migrator.database.compiler().index_name(model._meta.db_table, columns_)
        model._meta.indexes = [(cols, _) for (cols, _) in model._meta.indexes if columns != cols]
        self.ops.append(self.migrator.drop_index(model._meta.db_table, index_name))
        return model

    @get_model
    def add_not_null(self, model, *names):
        """Add not null."""
        for name in names:
            field = model._meta.fields[name]
            field.null = False
            self.ops.append(self.migrator.add_not_null(model._meta.db_table, field.db_column))
        return model

    @get_model
    def drop_not_null(self, model, *names):
        """Drop not null."""
        for name in names:
            field = model._meta.fields[name]
            field.null = True
            self.ops.append(self.migrator.drop_not_null(model._meta.db_table, field.db_column))
        return model

    @get_model
    def add_default(self, model, name, default):
        """Add default."""
        field = model._meta.fields[name]
        model._meta.defaults[field] = field.default = default
        self.ops.append(self.migrator.apply_default(model._meta.db_table, name, field))
        return model

#  pylama:ignore=W0223,W0212,R
