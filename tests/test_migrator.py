from __future__ import annotations

import peewee as pw
import pytest
from playhouse.migrate import MySQLDatabase
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


def test_sql_params(migrator: Migrator, models):
    Customer, Order = models
    customer = Customer.create(name="c", age=1)
    Order.create(number="1", uid="u1", customer=customer)
    Order.create(number="2", uid="u2", customer=customer)

    migrator.sql('UPDATE "order" SET number = ? WHERE uid = ?', "3", "u1")
    migrator()

    assert Order.get(Order.uid == "u1").number == "3"
    assert Order.get(Order.uid == "u2").number == "2"


def test_add_fields(migrator: Migrator, models):
    _, Order = models
    meta = Order._meta  # type: ignore[]
    migrator.add_fields(Order, finished=pw.BooleanField(default=False))
    assert "finished" in meta.fields
    migrator()


def test_add_fields_default(migrator: Migrator, models):
    Customer, _ = models
    customer = Customer.create(name="c", age=1)

    migrator.add_fields(Customer, status=pw.CharField(default="new", null=True))
    migrator()

    customer = Customer.get(Customer.id == customer.id)
    assert customer.status == "new"


def test_add_fields_allow_not_null(migrator: Migrator):
    migrator.add_fields("customer", blocked=pw.BooleanField(null=False), allow_not_null=True)
    migrator()

    field = migrator.orm["customer"]._meta.fields["blocked"]  # type: ignore[]
    assert not field.null


def test_add_fields_with_foreign_keys():
    db = pw.SqliteDatabase(":memory:", pragmas={"foreign_keys": 1})

    class User(pw.Model):
        class Meta:
            database = db

    class TgAccount(pw.Model):
        owner = pw.ForeignKeyField(User)

        class Meta:
            database = db

    User.create_table()
    TgAccount.create_table()
    user = User.create()
    TgAccount.create(owner=user)

    migrator = Migrator(db)
    migrator.add_fields(User, name=pw.CharField(default="John"))
    migrator()

    assert User.get(User.id == user.id).name == "John"


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


def test_remove_model(migrator: Migrator, database):
    assert "customer" in database.get_tables()

    migrator.remove_model("customer", cascade=True)
    migrator()

    assert "customer" not in database.get_tables()


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
    migrator()

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
    assert ops[0].fn.__name__ == "add_column"  # type: ignore[union-attr]


def test_alter_model_created_in_same_migration():
    db = pw.SqliteDatabase(":memory:")

    class TestTable(pw.Model):
        name = pw.CharField()

        class Meta:
            table_name = "test_table"

    migrator = Migrator(db)
    migrator.create_model(TestTable)

    with pytest.raises(ValueError, match="created in this migration"):
        migrator.add_fields("test_table", extra=pw.CharField(null=True))


def test_unknown_column_raises(migrator: Migrator):
    with pytest.raises(ValueError, match="Column typo not found in customer"):
        migrator.add_index("customer", "typo")

    with pytest.raises(ValueError, match="Column typo not found in customer"):
        migrator.drop_index("customer", "typo")


def test_change_field_drop_unique(migrator: Migrator, models):
    Customer, Order = models
    customer = Customer.create(name="c", age=1)

    migrator.change_fields(Order, uid=pw.CharField(unique=False))
    migrator()

    assert not Order._meta.fields["uid"].unique
    Order.create(number="1", uid="same", customer=customer)
    Order.create(number="2", uid="same", customer=customer)
    assert Order.select().count() == 2


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
def test_change_field_null(migrator, database):
    @migrator.create_model
    class Thing(pw.Model):
        name = pw.CharField()

    migrator()
    migrator.change_fields("thing", name=pw.CharField(null=True))
    migrator()

    assert 'ALTER TABLE "thing" ALTER COLUMN "name" DROP NOT NULL' in database.cursor().queries


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


def test_change_foreign_key(migrator: Migrator, models):
    Customer, Order = models

    migrator.change_fields(Order, customer=pw.ForeignKeyField(Customer, on_delete="CASCADE"))

    [dropped, added] = migrator.__ops__
    assert dropped.fn.__name__ == "drop_foreign_key_constraint"
    assert dropped.args == ("order", "customer_id")
    assert added.fn.__name__ == "add_foreign_key_constraint"
    assert added.args == ("order", "customer_id", "customer", "id", "CASCADE", "RESTRICT")


def test_change_foreign_key_to_plain_field(migrator: Migrator):
    migrator.change_fields("order", customer=pw.IntegerField(column_name="customer_id"))

    [dropped, changed] = migrator.__ops__
    assert dropped.fn.__name__ == "drop_foreign_key_constraint"
    assert changed.fn.__name__ == "change_column"
    assert not isinstance(migrator.orm["order"]._meta.fields["customer"], pw.ForeignKeyField)


def test_add_not_null(migrator: Migrator):
    order = migrator.orm["order"]
    migrator.drop_not_null("order", "number")
    migrator()
    assert order._meta.fields["number"].null

    migrator.add_not_null("order", "number")
    migrator()

    assert order._meta.fields["number"].null is False


def test_add_and_drop_constraints(migrator: Migrator):
    with migrator.fake():
        migrator.add_constraint("order", "uid_check", "CHECK (uid <> '')")
        migrator.drop_constraints("order", "uid_check")

        [added, dropped] = migrator.__ops__
        assert added.fn.__name__ == "add_constraint"
        assert added.args == ("order", "uid_check", "CHECK (uid <> '')")
        assert dropped.fn.__name__ == "drop_constraint"
        assert dropped.args == ("order", "uid_check")


def test_unsupported_database():
    with pytest.raises(ValueError, match="Unsupported database"):
        Migrator(pw.Database("test"))


def test_migrator_accepts_a_proxy():
    database = pw.SqliteDatabase(":memory:")
    proxy = pw.Proxy()
    proxy.initialize(database)
    migrator = Migrator(proxy)

    assert migrator.orm is not None
    migrator.create_model(type("Item", (pw.Model,), {}))
    migrator()
    assert "item" in database.get_tables()


def test_unknown_model_raises(migrator: Migrator):
    with pytest.raises(ValueError, match="Model nope not found"):
        migrator.add_fields("nope", name=pw.CharField())


def test_run_python_callable(migrator: Migrator):
    calls = []

    migrator.run(calls.append, "done")
    assert calls == []

    migrator()
    assert calls == ["done"]


def test_change_field_column_name(migrator: Migrator, models):
    _, Order = models

    migrator.change_fields(Order, uid=pw.CharField(column_name="order_uid"))

    renamed = [op for op in migrator.__ops__ if op.fn.__name__ == "rename_column"]
    assert [op.args for op in renamed] == [("order", "uid", "order_uid")]


def test_change_field_to_unique(migrator: Migrator, models):
    _, Order = models

    migrator.change_fields(Order, number=pw.CharField(unique=True))

    [added] = [op for op in migrator.__ops__ if op.fn.__name__ == "add_index"]
    assert added.args == ("order", ("number",), True)


def test_drop_single_column_index(migrator: Migrator, models):
    _, Order = models
    database = migrator.__database__

    migrator.add_index("order", "number")
    migrator()
    assert Order._meta.fields["number"].index
    assert "order_number" in [index.name for index in database.get_indexes("order")]

    migrator.drop_index("order", "number")
    migrator()

    assert Order._meta.fields["number"].index is False
    assert "order_number" not in [index.name for index in database.get_indexes("order")]


@pytest.mark.parametrize(
    ("database", "expected"),
    [
        (pw.SqliteDatabase(":memory:"), "SqliteMigrator"),
        (MySQLDatabase("test"), "MySQLMigrator"),
        (pw.PostgresqlDatabase("test"), "PostgresqlMigrator"),
    ],
)
def test_backend_selection(database, expected):
    assert type(Migrator(database).__migrator__).__name__ == expected


def test_add_callable_default(migrator: Migrator):
    migrator.add_default("order", "number", lambda: "generated")
    meta = migrator.orm["order"]._meta

    assert meta.fields["number"].default() == "generated"
    assert [name for name, _ in meta._default_callable_list if name == "number"] == ["number"]

    migrator()
    migrator.change_fields("order", number=pw.CharField(null=True))
    migrator()

    assert meta.fields["number"].null


def test_add_default_updates_peewee_bookkeeping(migrator: Migrator):
    migrator.add_default("order", "number", "generated")
    meta = migrator.orm["order"]._meta

    assert meta._default_by_name["number"] == "generated"

    migrator()
    # peewee 4.5 fails here if the bookkeeping above is missing.
    migrator.change_fields("order", number=pw.CharField(null=True))
    migrator()

    assert meta.fields["number"].null


def test_model_lookup_by_class_name(migrator: Migrator):
    migrator.add_fields("Order", extra=pw.CharField(null=True))

    assert "extra" in migrator.orm["order"]._meta.fields
