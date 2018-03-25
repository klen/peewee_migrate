import peewee as pw
from playhouse.migrate import (
    MySQLMigrator as MqM,
    PostgresqlMigrator as PgM,
    SchemaMigrator as ScM,
    SqliteMigrator as SqM,
    Operation, SQL, Entity, PostgresqlDatabase, operation, SqliteDatabase, MySQLDatabase
)

from peewee_migrate import LOGGER
from peewee_migrate.compat import (
    add_field_to_class, Clause, get_table_name, get_field_name, IS_PEEWEE_2
)


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
        # @TODO: (peewee-3-compat) This is broken in Peewee 3 because of the
        # rewritten query compiler.
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
        field.db_column = field.column_name = column_name
        # @TODO: (peewee-3-compat) This is broken in Peewee 3 because of the
        # rewritten query compiler.
        field_clause = self.database.compiler().field_definition(field)
        field.column_name = column_name
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

    def alter_change_column(self, table, column, field):
        """Support change columns for mysql Distrib 5.6.33."""
        field_null, field.null = field.null, True
        # @TODO: (peewee-3-compat) This is broken in Peewee 3 because of the
        # rewritten query compiler.
        field_clause = self.database.compiler().field_definition(field)
        field.null = field_null
        return Clause(SQL('ALTER TABLE'),
                      Entity(table),
                      SQL('MODIFY COLUMN'),
                      field_clause)


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
            # @TODO: (peewee-3-compat) This is broken in Peewee 3 because of
            # the rewritten query compiler.
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
        self.orm[get_table_name(model)] = model
        model._meta.database = self.database
        self.ops.append(model.create_table)
        return model

    create_model = create_table

    @get_model
    def drop_table(self, model, cascade=True):
        """Drop model and table from database.

        >> migrator.drop_table(model, cascade=True)
        """
        del self.orm[get_table_name(model)]
        self.ops.append(self.migrator.drop_table(model, cascade))

    remove_model = drop_table

    @get_model
    def add_columns(self, model, **fields):
        """Create new fields."""
        for name, field in fields.items():
            add_field_to_class(field, model, name)
            self.ops.append(self.migrator.add_column(
                get_table_name(model), get_field_name(field), field))
            if field.unique:
                self.ops.append(self.migrator.add_index(
                    get_table_name(model), (get_field_name(field),), unique=True))
        return model

    add_fields = add_columns

    @get_model
    def change_columns(self, model, **fields):
        """Change fields."""
        for name, field in fields.items():
            old_field = model._meta.fields.get(name, field)
            old_db_column = old_field and get_field_name(old_field)

            model._meta.validate_backrefs = False
            add_field_to_class(field, model, name)
            model._meta.validate_backrefs = True

            if isinstance(old_field, pw.ForeignKeyField):
                self.ops.append(self.migrator.drop_foreign_key_constraint(
                    get_table_name(model), old_db_column))

            if old_db_column != get_field_name(field):
                self.ops.append(
                    self.migrator.rename_column(
                        get_table_name(model), old_db_column, field.db_column))

            if isinstance(field, pw.ForeignKeyField):
                on_delete = field.on_delete if field.on_delete else 'RESTRICT'
                on_update = field.on_update if field.on_update else 'RESTRICT'
                self.ops.append(self.migrator.add_foreign_key_constraint(
                    get_table_name(model), get_field_name(field),
                    get_table_name(field.rel_model), field.to_field.name,
                    on_delete, on_update))
                continue

            self.ops.append(self.migrator.change_column(
                get_table_name(model), get_field_name(field), field))

            if field.unique == old_field.unique:
                continue

            if field.unique:
                index = (get_field_name(field),), field.unique
                self.ops.append(self.migrator.add_index(get_table_name(model), *index))
                model._meta.indexes.append(index)
            else:
                index = (get_field_name(field),), old_field.unique
                self.ops.append(self.migrator.drop_index(get_table_name(model), *index))
                model._meta.indexes.remove(index)

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
                # @TODO: (peewee-3-compat) This is broken in Peewee 3 because
                # of the rewritten query compiler.
                compiler = self.database.compiler()
                index_name = compiler.index_name(get_table_name(model), (get_field_name(field),))
                self.ops.append(self.migrator.drop_index(get_table_name(model), index_name))
            self.ops.append(
                self.migrator.drop_column(get_table_name(model), get_field_name(field), cascade=cascade))
        return model

    remove_fields = drop_columns

    def __del_field__(self, model, field):
        """Delete field from model."""
        model._meta.remove_field(field.name)
        delattr(model, field.name)
        if isinstance(field, pw.ForeignKeyField):
            obj_id_name = get_field_name(field)
            if get_field_name(field) == field.name:
                obj_id_name += '_id'
            delattr(model, obj_id_name)
            delattr(field.rel_model, field.related_name)
            del field.rel_model._meta.reverse_rel[field.related_name]

    @get_model
    def rename_column(self, model, old_name, new_name):
        """Rename field in model."""
        field = model._meta.fields[old_name]
        if isinstance(field, pw.ForeignKeyField):
            old_name = get_field_name(field)
        self.__del_field__(model, field)
        field.name = field.column_name = field.db_column = new_name
        add_field_to_class(field, model, new_name)
        if isinstance(field, pw.ForeignKeyField):
            field.db_column = field.column_name = new_name = get_field_name(field) + '_id'
        self.ops.append(self.migrator.rename_column(get_table_name(model), old_name, new_name))
        return model

    rename_field = rename_column

    @get_model
    def rename_table(self, model, new_name):
        """Rename table in database."""
        del self.orm[get_table_name(model)]
        model._meta.table_name = new_name
        model._meta.db_table = new_name
        self.orm[get_table_name(model)] = model
        self.ops.append(self.migrator.rename_table(get_table_name(model), new_name))
        return model

    @get_model
    def add_index(self, model, *columns, **kwargs):
        """Create indexes."""
        unique = kwargs.pop('unique', False)
        model._meta.indexes.append((columns, unique))
        columns_ = []
        for col in columns:
            field = model._meta.fields.get(col)

            if len(columns) == 1:
                field.unique = unique
                field.index = not unique

            if isinstance(field, pw.ForeignKeyField):
                col = col + '_id'

            columns_.append(col)
        self.ops.append(self.migrator.add_index(get_table_name(model), columns_, unique=unique))
        return model

    @get_model
    def drop_index(self, model, *columns):
        """Drop indexes."""
        columns_ = []
        for col in columns:
            field = model._meta.fields.get(col)

            if len(columns) == 1:
                field.unique = False
                field.index = False

            if isinstance(field, pw.ForeignKeyField):
                col = col + '_id'
            columns_.append(col)
        index_name = self.migrator.database.compiler().index_name(get_table_name(model), columns_)
        model._meta.indexes = [(cols, _) for (cols, _) in model._meta.indexes if columns != cols]
        self.ops.append(self.migrator.drop_index(get_table_name(model), index_name))
        return model

    @get_model
    def add_not_null(self, model, *names):
        """Add not null."""
        for name in names:
            field = model._meta.fields[name]
            field.null = False
            self.ops.append(self.migrator.add_not_null(get_table_name(model), get_field_name(field)))
        return model

    @get_model
    def drop_not_null(self, model, *names):
        """Drop not null."""
        for name in names:
            field = model._meta.fields[name]
            field.null = True
            self.ops.append(self.migrator.drop_not_null(get_table_name(model), get_field_name(field)))
        return model

    @get_model
    def add_default(self, model, name, default):
        """Add default."""
        field = model._meta.fields[name]
        model._meta.defaults[field] = field.default = default
        self.ops.append(self.migrator.apply_default(get_table_name(model), name, field))
        return model

#  pylama:ignore=W0223,W0212,R
