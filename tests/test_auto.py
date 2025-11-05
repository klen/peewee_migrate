from __future__ import annotations

import datetime as dt
from enum import Enum
from pathlib import Path

import peewee as pw
from playhouse.postgres_ext import (
    ArrayField,
    BinaryJSONField,
    DateTimeTZField,
    HStoreField,
    IntervalField,
    JSONField,
    TSVectorField,
)

from peewee_migrate.auto import (
    compare_fields,
    diff_many,
    diff_model,
    field_to_code,
    model_to_code,
)
from peewee_migrate.cli import get_router

from .models import Person

CURDIR = Path(__file__).parent


def test_auto_base():
    router = get_router(CURDIR / "migrations", "sqlite:///:memory:")
    router.run()
    migrator = router.migrator
    TagSource = migrator.orm.Tag
    PersonSource = migrator.orm.Person

    code = model_to_code(PersonSource)
    assert code
    assert 'table_name = "person"' in code

    changes = diff_many(list(migrator), [], migrator=migrator)
    assert len(changes) == 2

    class Person(pw.Model):  # type: ignore[]
        first_name = pw.CharField(unique=True)
        last_name = pw.CharField(max_length=255, index=True)

        dob = pw.DateField(null=True)
        is_deleted = pw.BooleanField(default=False)
        email = pw.CharField(index=True, unique=True)
        birthday = pw.DateField(default=dt.datetime.now)

    changes = diff_model(Person, PersonSource, migrator=migrator)
    assert not changes

    class Person(pw.Model):
        first_name = pw.IntegerField()
        last_name = pw.CharField(max_length=1024, null=True, unique=True)
        tag = pw.ForeignKeyField(TagSource, on_delete="CASCADE", backref="persons")
        email = pw.CharField(index=True, unique=True)

    changes = diff_model(Person, PersonSource, migrator=migrator)
    assert len(changes) == 9
    assert changes[0].startswith("migrator.add_fields(")
    assert "on_delete='CASCADE'" in changes[0]
    assert "backref='persons'" not in changes[0]

    assert changes[1].startswith("migrator.remove_fields('person'")
    assert changes[2].startswith("migrator.change_fields('person', first_name=")
    assert changes[3].startswith("migrator.change_fields('person', last_name=")
    assert changes[4].startswith("migrator.drop_not_null('person', 'last_name')")
    assert changes[5].startswith("migrator.add_index('person', 'tag'")
    assert changes[6].startswith("migrator.drop_index('person', 'first_name')")
    assert changes[7].startswith("migrator.drop_index('person', 'last_name')")
    assert changes[8].startswith("migrator.add_index('person', 'last_name', unique=True)")


def test_model_to_code():
    class Object(pw.Model):
        name = pw.CharField()
        age = pw.IntegerField(default=0)

        class Meta:
            table_name = "object"

    code = model_to_code(Object)
    assert code
    assert "class Object(pw.Model):" in code
    assert "name = pw.CharField(max_length=255)" in code
    assert "age = pw.IntegerField()" in code
    assert 'table_name = "object"' in code


def test_auto_postgresext():
    class Object(pw.Model):
        array_field = ArrayField()
        binary_json_field = BinaryJSONField()
        dattime_tz_field = DateTimeTZField()
        hstore_field = HStoreField()
        interval_field = IntervalField()
        json_field = JSONField()
        ts_vector_field = TSVectorField()

    code = model_to_code(Object)
    assert code
    assert "json_field = pw_pext.JSONField()" in code
    assert "hstore_field = pw_pext.HStoreField(index=True)" in code


def test_auto_multi_column_index():
    class Object(pw.Model):
        first_name = pw.CharField()
        last_name = pw.CharField()

        class Meta:
            indexes = ((("first_name", "last_name"), True),)

    code = model_to_code(Object)
    assert code
    assert "indexes = [(('first_name', 'last_name'), True)]" in code


def test_auto_self_referencing_foreign_key_on_model_create():
    class Employee(pw.Model):
        manager = pw.ForeignKeyField("self")

    code = field_to_code(Employee.manager)
    assert "model='self'" in code


def test_auto_default():
    code = field_to_code(Person.is_deleted)
    assert code == "is_deleted = pw.BooleanField()"


def test_auto_on_update_on_delete():
    class Employee(pw.Model):
        manager = pw.ForeignKeyField("self", on_update="CASCADE", on_delete="CASCADE")

    code = field_to_code(Employee.manager)
    assert "on_update='CASCADE'" in code
    assert "on_delete='CASCADE'" in code


def test_diff_multi_column_index():
    class Object(pw.Model):
        first_name = pw.CharField()
        last_name = pw.CharField()

    ObjectWithUniqueIndex = type(  # type: ignore[]
        "Object",
        (pw.Model,),
        {
            "first_name": pw.CharField(),
            "last_name": pw.CharField(),
            "Meta": type(
                "Meta",
                (),
                {
                    "table_name": "object",
                    "indexes": ((("first_name", "last_name"), True),),
                },
            ),
        },
    )

    ObjectWithNonUniqueIndex = type(  # type: ignore[]
        "Object",
        (pw.Model,),
        {
            "first_name": pw.CharField(),
            "last_name": pw.CharField(),
            "Meta": type(
                "Meta",
                (),
                {
                    "table_name": "object",
                    "indexes": ((("first_name", "last_name"), False),),
                },
            ),
        },
    )

    changes = diff_model(ObjectWithUniqueIndex, Object)
    assert len(changes) == 1
    assert changes[0] == "migrator.add_index('object', 'first_name', 'last_name', unique=True)"

    changes = diff_model(ObjectWithNonUniqueIndex, Object)
    assert len(changes) == 1
    assert changes[0] == "migrator.add_index('object', 'first_name', 'last_name', unique=False)"

    changes = diff_model(ObjectWithNonUniqueIndex, ObjectWithUniqueIndex)
    assert len(changes) == 2
    assert changes[0] == "migrator.drop_index('object', 'first_name', 'last_name')"
    assert changes[1] == "migrator.add_index('object', 'first_name', 'last_name', unique=False)"


def test_diff_model_index():
    class Order1(pw.Model):
        active = pw.BooleanField()
        order_id = pw.CharField()

        class Meta:
            table_name = "order"

    class Order2(pw.Model):
        active = pw.BooleanField()
        order_id = pw.CharField()

        class Meta:
            table_name = "order"

    Order2.add_index(Order2.active, Order2.order_id, where=(Order2.active))

    changes = diff_model(Order2, Order1)
    assert changes


def test_diff_self_referencing_foreign_key_on_field_added():
    class Employee(pw.Model):
        name = pw.CharField()

    class EmployeeNew(pw.Model):
        name = pw.CharField()
        manager = pw.ForeignKeyField("self")

        class Meta:
            table_name = "employee"

    changes = diff_model(EmployeeNew, Employee)
    assert "migrator.add_fields" in changes[0]
    assert "model='self'" in changes[0]


def test_custom_fields():
    class Test(pw.Model):
        dtfield = pw.DateTimeField(default=dt.datetime.now)
        datetime_tz_field = DateTimeTZField()

    code = field_to_code(Test.dtfield)
    assert code == "dtfield = pw.DateTimeField()"

    code = field_to_code(Test.datetime_tz_field)
    assert code == "datetime_tz_field = pw_pext.DateTimeTZField()"

    class CustomDatetimeField(pw.DateTimeField):
        pass

    class Test2(Test):
        dtfield = CustomDatetimeField()

    code = field_to_code(Test2.dtfield)
    assert code == "dtfield = pw.DateTimeField()"

    res = compare_fields(Test2.dtfield, Test.dtfield)
    assert not res


def test_custom_fields2():
    class EnumField(pw.CharField):
        def __init__(self, enum, *args, **kwargs):
            """Initialize the field."""
            self.enum = enum
            super().__init__(*args, **kwargs)

        def db_value(self, value):
            """Convert python value to database."""
            if value is None:
                return value

            return value.value

        def python_value(self, value):
            """Convert database value to python."""
            if value is None:
                return value

            return self.enum(value)

    class TestEnum(Enum):
        A = "a"
        B = "b"

    class Test(pw.Model):
        enum_field = EnumField(TestEnum, default=TestEnum.A)

    code = field_to_code(Test.enum_field)
    assert code == "enum_field = pw.CharField(max_length=255)"


def test_diff_fk_on_delete(migrator):
    class Test(pw.Model):
        pass

    class Test2(pw.Model):
        test = pw.ForeignKeyField(Test, null=True, on_delete="CASCADE")

    class Test3(pw.Model):
        test = pw.ForeignKeyField(Test, null=True, on_delete="SET NULL")

    res = compare_fields(Test2.test, Test3.test)
    assert not res


def test_diff_null(migrator):
    class Test(pw.Model):
        pass

    class Test2(pw.Model):
        test = pw.ForeignKeyField(Test, null=True)

    class Test3(pw.Model):
        test = pw.ForeignKeyField(Test, null=False)

    res = compare_fields(Test3.test, Test2.test)
    assert res
