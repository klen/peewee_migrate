import pytest


@pytest.fixture
def migrator():
    from playhouse.db_url import connect

    from peewee_migrate import Migrator

    database = connect("sqlite:///:memory:")
    return Migrator(database)


@pytest.fixture
def Customer(migrator):
    from peewee import CharField, IntegerField, Model

    @migrator.create_table
    class Customer(Model):
        name = CharField()
        age = IntegerField()

    return Customer


@pytest.fixture
def Order(Customer, migrator):
    from peewee import CharField, ForeignKeyField, Model

    @migrator.create_table
    class Order(Model):
        number = CharField()
        uid = CharField(unique=True)

        customer = ForeignKeyField(Customer, column_name="customer_id")

    return Order


@pytest.fixture(autouse=True)
def run_migrator(Customer, Order, migrator):
    migrator.run()
