from __future__ import annotations

import pytest
from peewee import CharField, ForeignKeyField, IntegerField, Model


class Customer(Model):
    name = CharField()
    age = IntegerField()


class Order(Model):
    number = CharField()
    uid = CharField(unique=True)

    customer = ForeignKeyField(Customer, column_name="customer_id")


@pytest.fixture()
def dburl():
    return "sqlite:///:memory:"


@pytest.fixture()
def router(dburl):
    from playhouse.db_url import connect

    from peewee_migrate import Router

    database = connect(dburl)
    return Router(database)


@pytest.fixture()
def migrator(database):
    from peewee_migrate import Migrator

    migrator = Migrator(database)
    migrator.create_model(Customer)
    migrator.create_model(Order)
    migrator()
    return migrator


@pytest.fixture()
def database(router):
    return router.database


@pytest.fixture(autouse=True)
def _patch_postgres(dburl):
    # Monkey patch psycopg2 connect
    import psycopg2

    from .mocks import postgres

    psycopg2.connect = postgres.MockConnection
