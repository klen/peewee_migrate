"""Peewee migrations."""

import datetime as dt
import peewee as pw


def migrate(migrator, database, **kwargs):
    """Write your migrations here.

    > Model = migrator.orm['name']

    > migrator.sql(sql)
    > migrator.python(func, *args, **kwargs)
    > migrator.create_model(Model)
    > migrator.store_model(Model)
    > migrator.remove_model(Model, cascade=True)
    > migrator.add_fields(Model, **fields)
    > migrator.change_fields(Model, **fields)
    > migrator.remove_fields(Model, *field_names, cascade=True)
    > migrator.rename_field(Model, old_field_name, new_field_name)
    > migrator.rename_table(Model, new_table_name)
    > migrator.add_index(Model, *col_names, unique=False)
    > migrator.drop_index(Model, index_name)
    > migrator.add_not_null(Model, field_name)
    > migrator.drop_not_null(Model, field_name)
    > migrator.add_default(Model, field_name, default)

    """
    migrator.rename_field('tag', 'created_at', 'updated_at')
    migrator.add_fields('person', is_deleted=pw.BooleanField(default=False))


def rollback(migrator, database, **kwargs):
    migrator.rename_field('tag', 'updated_at', 'created_at')
    migrator.remove_fields('person', 'is_deleted')
