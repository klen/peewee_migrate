from __future__ import annotations

import pytest
from peewee import CharField, ForeignKeyField, IntegerField, Model, Check


class Customer(Model):
    name = CharField()
    age = IntegerField()


class Order(Model):
    number = CharField()
    uid = CharField(unique=True)

    customer = ForeignKeyField(Customer, column_name="customer_id")


@pytest.fixture()
def router():
    from playhouse.db_url import connect
    from peewee_migrate import Router

    database = connect("sqlite:///:memory:")
    return Router(database)


@pytest.fixture()
def migrator(router):
    from peewee_migrate import Migrator
    from playhouse.db_url import connect

    migrator = Migrator(router.database)
    migrator.create_table(Customer)
    migrator.create_table(Order)
    migrator()
    return migrator
