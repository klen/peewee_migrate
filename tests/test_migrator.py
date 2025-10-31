from __future__ import annotations

import peewee as pw
import pytest
from playhouse.test_utils import count_queries

from peewee_migrate import Migrator
from peewee_migrate.auto import diff_many


def test_migrator(router):  # noqa: PLR0915
    migrator = Migrator(router.database)

    @migrator.create_model
    class Customer(pw.Model):
        name = pw.CharField()

    assert Customer == migrator.orm["customer"]

    @migrator.create_model
    class Order(pw.Model):
        number = pw.CharField()
        uid = pw.CharField(unique=True)

        customer_id = pw.ForeignKeyField(Customer, column_name="customer_id")

    assert Order == migrator.orm["order"]
    meta = Order._meta  # type: ignore[]
    migrator()

    migrator.add_fields(Order, finished=pw.BooleanField(default=False))
    assert "finished" in meta.fields
    migrator()

    migrator.remove_fields("order", "finished", "customer_id", "uid", legacy=True)
    assert "finished" not in meta.fields
    assert not hasattr(Order, "customer_id")
    assert not hasattr(Order, "customer_id_id")
    migrator()

    migrator.add_fields(Order, customer=pw.ForeignKeyField(Customer, null=True))
    assert "customer" in meta.fields
    assert Order.customer.name == "customer"  # type: ignore[]
    assert Order.customer.column_name == "customer_id"
    migrator()
    assert Order.customer.name == "customer"  # type: ignore[]
    assert Order.customer.column_name == "customer_id"

    migrator.rename_field(Order, "number", "identifier")
    assert "identifier" in meta.fields
    migrator()

    migrator.drop_not_null(Order, "identifier")
    assert meta.fields["identifier"].null
    assert meta.columns["identifier"].null
    migrator()

    migrator.add_default(Order, "identifier", 11)
    assert meta.fields["identifier"].default == 11
    migrator()

    migrator.change_fields(Order, identifier=pw.IntegerField(default=0))
    assert Order.identifier.field_type == "INT"  # type: ignore[]
    migrator()

    Order.create(identifier=55)
    migrator.sql('UPDATE "order" SET identifier = 77;')
    migrator()
    order = Order.get()
    assert order.identifier == 77

    migrator.add_index(Order, "identifier", "customer")
    migrator()
    assert meta.indexes
    assert not Order.identifier.index  # type: ignore[]

    migrator.drop_index(Order, "identifier", "customer")
    migrator()
    assert not meta.indexes

    migrator.remove_fields(Order, "customer", legacy=True)
    migrator()
    assert not hasattr(Order, "customer")

    migrator.add_index(Order, "identifier", unique=True)
    migrator()
    assert not Order.identifier.index  # type: ignore[]
    assert Order.identifier.unique  # type: ignore[]
    assert meta.indexes

    migrator.rename_table(Order, "orders")
    assert migrator.orm["orders"]
    assert migrator.orm["orders"]._meta.table_name == "orders"  # type: ignore[]
    migrator()

    migrator.change_fields(Order, identifier=pw.IntegerField(default=0))
    assert not Order._meta.indexes  # type: ignore[]


def test_add_fields(migrator: Migrator, models):
    _, Order = models
    meta = Order._meta  # type: ignore[]
    migrator.add_fields(Order, finished=pw.BooleanField(default=False))
    assert "finished" in meta.fields
    migrator()


def test_add_fk(migrator: Migrator, models):
    Customer, Order = models
    meta = Order._meta  # type: ignore[]
    migrator.add_fields(Order, guest=pw.ForeignKeyField(Customer, null=True))
    assert "guest" in meta.fields
    assert Order.guest.name == "guest"  # type: ignore[]
    assert Order.guest.column_name == "guest_id"
    migrator()


def test_remove_fields(migrator: Migrator, models):
    _, Order = models
    meta = Order._meta  # type: ignore[]
    to_remove = "customer", "number"
    migrator.remove_fields(Order, *to_remove, legacy=True)
    for field in to_remove:
        assert field not in meta.fields

    migrator()


def test_remove_fk(migrator: Migrator):
    Order = migrator.orm["order"]
    meta = Order._meta  # type: ignore[]
    assert "customer" in meta.fields
    migrator.remove_fields(Order, "customer", legacy=True)
    assert "customer" not in meta.fields
    migrator()


def test_rename_field(migrator: Migrator):
    Order = migrator.orm["order"]
    migrator.rename_field("order", "customer", "user")
    meta = Order._meta  # type: ignore[]
    assert meta.columns["user_id"]
    assert meta.fields["user"]
    [operation] = migrator.__ops__
    assert operation.args == ("order", "customer_id", "user_id")  # type: ignore[union-attr]

    # Rollback
    migrator()
    migrator.rename_field("order", "user", "customer")
    [operation] = migrator.__ops__
    assert operation.args == ("order", "user_id", "customer_id")  # type: ignore[union-attr]


def test_rename_table(migrator: Migrator):
    migrator.rename_table("customer", "user")
    [operation] = migrator.__ops__
    assert operation.args == ("customer", "user")  # type: ignore[union-attr]

    class User(pw.Model):
        name = pw.CharField()
        age = pw.IntegerField()

    migrations = diff_many([migrator.orm["user"]], [User], migrator)
    assert not migrations


def test_migrator_fake(migrator: Migrator):
    @migrator.create_model
    class Customer(pw.Model):
        name = pw.CharField()

    assert migrator.__ops__

    migrator()

    assert not migrator.__ops__

    with migrator.fake():
        migrator.add_fields("customer", is_blocked=pw.BooleanField(default=False))

    assert not migrator.__ops__

    snapshot = migrator.orm["customer"]
    assert "is_blocked" in snapshot._meta.fields  # type: ignore[]


@pytest.mark.parametrize("dburl", ["postgres:///fake"])
def test_migrator_postgres(migrator, database):
    """
    Ensure change_fields generates queries and
    does not cause exception
    """

    @migrator.create_model
    class User(pw.Model):
        name = pw.CharField()
        created_at = pw.DateField()

    assert User == migrator.orm["user"]

    # Date -> DateTime
    migrator.change_fields("user", created_at=pw.DateTimeField())
    migrator()
    queries = database.cursor().queries
    assert 'ALTER TABLE "user" ALTER COLUMN "created_at" TYPE TIMESTAMP' in queries

    # Char -> Text
    migrator.change_fields("user", name=pw.TextField())
    migrator()
    assert 'ALTER TABLE "user" ALTER COLUMN "name" TYPE TEXT' in database.cursor().queries


def test_add_field_unique(migrator: Migrator):
    @migrator.create_model
    class TestTable(pw.Model):
        class Meta:
            table_name = "test_table"

        field = pw.CharField(null=False)

    migrator()
    migrator.add_fields("test_table", field2=pw.CharField(unique=True))
    ops = migrator.__ops__
    assert len(ops) == 1
    assert ops[0].method == "add_column"  # type: ignore[union-attr]


def test_change_field_constraint(migrator: Migrator):
    @migrator.create_model
    class TestTable(pw.Model):
        class Meta:
            table_name = "test_table"

        field_with_check = pw.CharField(
            null=False, constraints=[pw.Check("field_with_check in ('opt1', 'opt2')")]
        )

    migrator()

    tt = migrator.orm["test_table"]
    migrator.change_fields(
        tt,
        field_with_check=pw.CharField(
            null=False,
            constraints=[pw.Check("field_with_check in ('opt1', 'opt2', 'opt3')")],
        ),
    )
    migrator()

    tt.insert(field_with_check="opt3").execute()
    with pytest.raises(pw.IntegrityError):
        tt.insert(field_with_check="opt4").execute()


@pytest.mark.parametrize("dburl", ["postgres:///fake"])
def test_change_field_default(migrator: Migrator, database):
    @migrator.create_model
    class TestTable(pw.Model):
        field_with_default = pw.CharField(constraints=[pw.SQL("DEFAULT 'test'")])

    migrator()

    migrator.change_fields(
        "testtable",
        field_with_default=pw.CharField(default=22),
    )
    with count_queries() as counter:
        migrator()

    queries = counter.get_queries()
    assert queries[0].msg == (
        'ALTER TABLE "testtable" ALTER COLUMN "field_with_default" TYPE VARCHAR(255)',
        [],
    )
    assert queries[1].msg == (
        'ALTER TABLE "testtable" ALTER COLUMN "field_with_default" SET DEFAULT %s',
        ["22"],
    )
    assert queries[2].msg == (
        'ALTER TABLE "testtable" ALTER COLUMN "field_with_default" SET NOT NULL',
        [],
    )
