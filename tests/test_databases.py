"""Checks against a real database.

The CI database job sets `PEEWEE_MIGRATE_PG` and `PEEWEE_MIGRATE_MYSQL`; without
them these tests are skipped, so a plain `pytest` run needs no servers.
"""

from __future__ import annotations

import os

import peewee as pw
import pytest
from playhouse.db_url import connect

from peewee_migrate import Router

DATABASES = [
    pytest.param(
        os.environ.get(env),
        id=backend,
        marks=pytest.mark.skipif(not os.environ.get(env), reason=f"{backend} is not configured"),
    )
    for backend, env in (("postgres", "PEEWEE_MIGRATE_PG"), ("mysql", "PEEWEE_MIGRATE_MYSQL"))
]

CREATE = """\
import peewee as pw


def migrate(migrator, database, **kwargs):
    @migrator.create_model
    class Article(pw.Model):
        title = pw.CharField()
"""

ALTER = """\
import peewee as pw


def migrate(migrator, database, **kwargs):
    migrator.add_fields("article", body=pw.TextField(null=True))
    migrator.add_index("article", "title", unique=True)


def rollback(migrator, database, **kwargs):
    migrator.drop_index("article", "title")
    migrator.remove_fields("article", "body")
"""

CHANGE = """\
import peewee as pw


def migrate(migrator, database, **kwargs):
    migrator.change_fields("article", body=pw.TextField(null=False))


def rollback(migrator, database, **kwargs):
    migrator.change_fields("article", body=pw.TextField(null=True))
"""


@pytest.mark.real_db
@pytest.mark.parametrize("url", DATABASES)
def test_migration_round_trip(url, tmp_path):
    db = connect(url)
    migrate_dir = tmp_path / "migrations"
    migrate_dir.mkdir()
    for index, source in enumerate((CREATE, ALTER, CHANGE), start=1):
        name = ("create", "alter", "change")[index - 1]
        (migrate_dir / f"{index:03}_{name}.py").write_text(source)

    router = Router(db, migrate_dir=migrate_dir)

    class Article(pw.Model):
        class Meta:
            database = db
            table_name = "article"

    def columns() -> dict[str, pw.ColumnMetadata]:
        return {column.name: column for column in db.get_columns("article")}

    try:
        assert router.run() == ["001_create", "002_alter", "003_change"]
        assert router.done == ["001_create", "002_alter", "003_change"]

        assert set(columns()) == {"id", "title", "body"}
        assert columns()["body"].null is False
        indexes = db.get_indexes("article")
        assert any(index.unique and index.columns == ["title"] for index in indexes)

        router.rollback()
        assert router.diff == ["003_change"]
        assert columns()["body"].null is True

        router.rollback()
        assert set(columns()) == {"id", "title"}
        # The primary key stays; the unique index on the title is gone.
        assert not any(index.columns == ["title"] for index in db.get_indexes("article"))
    finally:
        Article.drop_table(safe=True)
        router.model.drop_table(safe=True)
        db.close()
