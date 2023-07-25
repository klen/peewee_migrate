from __future__ import annotations

import datetime as dt
from typing import Final

import peewee as pw


class MigrateHistory(pw.Model):
    """Presents the migrations in database."""

    id = pw.AutoField()  # noqa: A003
    name = pw.CharField()
    migrated_at = pw.DateTimeField(default=dt.datetime.utcnow)

    def __str__(self) -> str:
        """String representation."""
        return self.name  # type: ignore[]


MIGRATE_TABLE: Final = "migratehistory"
