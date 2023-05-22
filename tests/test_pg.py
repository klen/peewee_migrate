import peewee as pw
import pytest


class Customer(pw.Model):
    name = pw.CharField()
    age = pw.IntegerField()


@pytest.mark.parametrize("dburl", ["postgres://localhost:5432/test"])
def test_base(migrator, database):
    migrator()
    queries = database.cursor().queries
    assert queries
