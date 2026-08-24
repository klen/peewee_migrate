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
    assert "age = pw.IntegerField(default=0)" in code
    assert 'table_name = "object"' in code


def test_model_to_code_multi_column_index():
    class Object(pw.Model):
        first_name = pw.CharField()
        last_name = pw.CharField()

        class Meta:
            indexes = ((("first_name", "last_name"), True),)

    code = model_to_code(Object)
    assert code
    assert "indexes = [(('first_name', 'last_name'), True)]" in code


def test_model_to_code_postgresext():
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


def test_field_to_code():
    code = field_to_code(Person.id)  # type: ignore[]
    assert code == "id = pw.AutoField()"


def test_field_to_code_default():
    code = field_to_code(Person.is_deleted)
    assert code == "is_deleted = pw.BooleanField(default=False)"


def test_field_to_code_self_referencing_foreign_key_on_model_create():
    class Employee(pw.Model):
        manager = pw.ForeignKeyField("self")

    code = field_to_code(Employee.manager)
    assert "model='self'" in code


def test_field_to_code_on_update_on_delete():
    class Employee(pw.Model):
        manager = pw.ForeignKeyField("self", on_update="CASCADE", on_delete="CASCADE")

    code = field_to_code(Employee.manager)
    assert "on_update='CASCADE'" in code
    assert "on_delete='CASCADE'" in code


def test_field_to_code_custom_fields():
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


def test_field_to_code_custom_fields2():
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
    assert code == "enum_field = pw.CharField(default='a', max_length=255)"


def test_diff_models():
    class Person(pw.Model):  # type: ignore[]
        first_name = pw.CharField(unique=True)
        last_name = pw.CharField(max_length=255, index=True)

        dob = pw.DateField(null=True)
        is_deleted = pw.BooleanField(default=False)
        email = pw.CharField(index=True, unique=True)
        birthday = pw.DateField(default=dt.datetime.now)

    class Tag(pw.Model):
        tag = pw.CharField()

    class Person2(pw.Model):
        first_name = pw.IntegerField()
        last_name = pw.CharField(max_length=1024, null=True, unique=True)
        email = pw.CharField(index=True, unique=True)
        tag = pw.ForeignKeyField(Tag, on_delete="CASCADE", backref="persons")

        class Meta:
            table_name = "person"
            legacy_table_names = False

    changes = diff_model(Person2, Person)
    # Note: no separate `add_index('person', 'tag', ...)` is emitted for the
    # newly added `tag` ForeignKeyField — peewee's `add_column` will create
    # that index implicitly because `ForeignKeyField` defaults to `index=True`.
    assert len(changes) == 8
    assert changes[0].startswith("migrator.add_fields(")
    assert "on_delete='CASCADE'" in changes[0]
    assert "backref='persons'" not in changes[0]

    assert changes[1].startswith("migrator.remove_fields('person'")
    assert changes[2].startswith("migrator.change_fields('person', first_name=")
    assert changes[3].startswith("migrator.change_fields('person', last_name=")
    assert changes[4].startswith("migrator.drop_not_null('person', 'last_name')")
    assert changes[5].startswith("migrator.drop_index('person', 'first_name')")
    assert changes[6].startswith("migrator.drop_index('person', 'last_name')")
    assert changes[7].startswith("migrator.add_index('person', 'last_name', unique=True)")
    assert not any("add_index('person', 'tag'" in c for c in changes)


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


def test_diff_no_redundant_index_for_added_fk():
    """Regression: adding a ForeignKeyField to an existing model must not
    emit a separate `migrator.add_index(...)` call for the FK's auto-index.

    `playhouse.migrate.SchemaMigrator.add_column` already creates the index
    implicitly because `ForeignKeyField` defaults to `index=True`. A separate
    `add_index` call collides with the implicit one and fails on a fresh DB
    with `OperationalError: index <table>_<fk>_id already exists`.
    """

    class Tag(pw.Model):
        name = pw.CharField()

    class BookOld(pw.Model):
        title = pw.CharField()

        class Meta:
            table_name = "book"

    class BookNew(pw.Model):
        title = pw.CharField()
        tag = pw.ForeignKeyField(Tag, null=True)

        class Meta:
            table_name = "book"

    changes = diff_model(BookNew, BookOld)
    assert any("migrator.add_fields" in c for c in changes)
    assert not any("migrator.add_index" in c for c in changes), (
        f"FK auto-index should not be re-emitted; got: {changes}"
    )


def test_diff_no_redundant_drop_index_for_removed_fk():
    """Symmetric regression: removing a ForeignKeyField must not emit a
    separate `migrator.drop_index(...)` call. `drop_column` removes the
    field's auto-index implicitly.
    """

    class Tag(pw.Model):
        name = pw.CharField()

    class BookOld(pw.Model):
        title = pw.CharField()
        tag = pw.ForeignKeyField(Tag, null=True)

        class Meta:
            table_name = "book"

    class BookNew(pw.Model):
        title = pw.CharField()

        class Meta:
            table_name = "book"

    changes = diff_model(BookNew, BookOld)
    assert any("migrator.remove_fields" in c for c in changes)
    assert not any("migrator.drop_index" in c for c in changes), (
        f"FK auto-index should not be re-dropped; got: {changes}"
    )


def test_diff_no_redundant_index_for_added_unique_field():
    """`unique=True` on a field also triggers an implicit index in
    `add_column` (the unique constraint is the index). A separate
    `add_index(unique=True)` would collide on a fresh DB.
    """

    class WidgetOld(pw.Model):
        name = pw.CharField()

        class Meta:
            table_name = "widget"

    class WidgetNew(pw.Model):
        name = pw.CharField()
        slug = pw.CharField(unique=True)

        class Meta:
            table_name = "widget"

    changes = diff_model(WidgetNew, WidgetOld)
    assert any("migrator.add_fields" in c for c in changes)
    assert not any("migrator.add_index" in c for c in changes), (
        f"unique-field auto-index should not be re-emitted; got: {changes}"
    )


def test_diff_composite_index_on_added_fields_still_emitted():
    """Negative case: a multi-column `Meta.indexes` entry covering newly
    added fields must STILL be emitted explicitly. `add_column` only auto-
    creates single-column indexes from field flags; composite indexes are
    not created as a side effect of field additions.
    """

    class WidgetOld(pw.Model):
        existing = pw.CharField()

        class Meta:
            table_name = "widget"

    class WidgetNew(pw.Model):
        existing = pw.CharField()
        a = pw.CharField()
        b = pw.CharField()

        class Meta:
            table_name = "widget"
            indexes = ((("a", "b"), False),)

    changes = diff_model(WidgetNew, WidgetOld)
    assert any("migrator.add_index('widget', 'a', 'b'" in c for c in changes), (
        f"Composite index over newly added fields must be emitted; got: {changes}"
    )


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


def test_diff_defaults():
    class Object(pw.Model):
        f1 = pw.BooleanField(default=True)
        f2 = pw.BooleanField(default=False)

    res = compare_fields(Object.f1, Object.f2)
    assert not res


def test_diff_many():
    router = get_router(CURDIR / "migrations", "sqlite:///:memory:")
    router.run()
    migrator = router.migrator

    changes = diff_many(list(migrator), [], migrator=migrator)
    assert len(changes) == 2
