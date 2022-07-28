import peewee as pw


def test_migrator():
    from playhouse.db_url import connect

    from peewee_migrate import Migrator

    database = connect("sqlite:///:memory:")
    migrator = Migrator(database)

    @migrator.create_table
    class Customer(pw.Model):
        name = pw.CharField()

    assert Customer == migrator.orm["customer"]

    @migrator.create_table
    class Order(pw.Model):
        number = pw.CharField()
        uid = pw.CharField(unique=True)

        customer_id = pw.ForeignKeyField(Customer, column_name="customer_id")

    assert Order == migrator.orm["order"]
    migrator.run()

    migrator.add_columns(Order, finished=pw.BooleanField(default=False))
    assert "finished" in Order._meta.fields
    migrator.run()

    migrator.drop_columns("order", "finished", "customer_id", "uid")
    assert "finished" not in Order._meta.fields
    assert not hasattr(Order, "customer_id")
    assert not hasattr(Order, "customer_id_id")
    migrator.run()

    migrator.add_columns(Order, customer=pw.ForeignKeyField(Customer, null=True))
    assert "customer" in Order._meta.fields
    assert Order.customer.name == "customer"
    migrator.run()
    assert Order.customer.name == "customer"

    migrator.rename_column(Order, "number", "identifier")
    assert "identifier" in Order._meta.fields
    migrator.run()

    migrator.drop_not_null(Order, "identifier")
    assert Order._meta.fields["identifier"].null
    assert Order._meta.columns["identifier"].null
    migrator.run()

    migrator.add_default(Order, "identifier", 11)
    assert Order._meta.fields["identifier"].default == 11
    migrator.run()

    migrator.change_columns(Order, identifier=pw.IntegerField(default=0))
    assert Order.identifier.field_type == "INT"
    migrator.run()

    Order.create(identifier=55)
    migrator.sql('UPDATE "order" SET identifier = 77;')
    migrator.run()
    order = Order.get()
    assert order.identifier == 77

    migrator.add_index(Order, "identifier", "customer")
    migrator.run()
    assert Order._meta.indexes
    assert not Order.identifier.index

    migrator.drop_index(Order, "identifier", "customer")
    migrator.run()
    assert not Order._meta.indexes

    migrator.remove_fields(Order, "customer")
    migrator.run()
    assert not hasattr(Order, "customer")

    migrator.add_index(Order, "identifier", unique=True)
    migrator.run()
    assert not Order.identifier.index
    assert Order.identifier.unique
    assert Order._meta.indexes

    migrator.rename_table(Order, "orders")
    assert migrator.orm["orders"]
    assert migrator.orm["orders"]._meta.table_name == "orders"
    migrator.run()

    migrator.change_columns(Order, identifier=pw.IntegerField(default=0))
    assert not Order._meta.indexes


def test_migrator_postgres():
    """
    Ensure change_fields generates queries and
    does not cause exception
    """
    import peewee as pw
    # Monkey patch psycopg2 connect
    import psycopg2
    from playhouse.db_url import connect

    from peewee_migrate import Migrator

    from .mocks import postgres

    psycopg2.connect = postgres.MockConnection

    database = connect("postgres:///fake")

    migrator = Migrator(database)

    @migrator.create_table
    class User(pw.Model):
        name = pw.CharField()
        created_at = pw.DateField()

    assert User == migrator.orm["user"]

    # Date -> DateTime
    migrator.change_fields("user", created_at=pw.DateTimeField())
    migrator.run()
    assert (
        'ALTER TABLE "user" ALTER COLUMN "created_at" TYPE TIMESTAMP'
        in database.cursor().queries
    )

    # Char -> Text
    migrator.change_fields("user", name=pw.TextField())
    migrator.run()
    assert (
        'ALTER TABLE "user" ALTER COLUMN "name" TYPE TEXT' in database.cursor().queries
    )


def test_rename_column(Order, migrator):
    Order = migrator.orm["order"]
    migrator.rename_column("order", "customer", "user")
    assert Order._meta.columns["user_id"]
    assert Order._meta.fields["user"]
    [operation] = migrator.ops
    assert operation.args == ("order", "customer_id", "user_id")

    # Rollback
    migrator.run()
    migrator.rename_column("order", "user", "customer")
    [operation] = migrator.ops
    assert operation.args == ("order", "user_id", "customer_id")


def test_rename_table(Customer, migrator):
    migrator.rename_table("customer", "user")
    [operation] = migrator.ops
    assert operation.args == ("customer", "user")

    class User(pw.Model):
        name = pw.CharField()
        age = pw.IntegerField()

    from peewee_migrate.auto import diff_many

    migrations = diff_many([migrator.orm["user"]], [User], migrator)
    assert not migrations
