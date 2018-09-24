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
    @migrator.create_model
    class Tag(pw.Model):
        tag = pw.CharField()

    @migrator.create_model
    class Person(pw.Model):
        first_name = pw.CharField()
        last_name = pw.CharField(index=True)
        dob = pw.DateField(null=True)
        birthday = pw.DateField(default=dt.datetime.now)
        email = pw.CharField(index=True, unique=True)
