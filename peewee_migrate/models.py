from __future__ import annotations

import datetime as dt
from typing import Final

import peewee as pw


class MigrateHistory(pw.Model):
    """Presents the migrations in database."""

    id = pw.AutoField()
    name = pw.CharField()
    migrated_at = pw.DateTimeField(default=lambda: dt.datetime.now(dt.timezone.utc).replace(tzinfo=None))

    def __str__(self) -> str:
        """String representation."""
        return self.name  # type: ignore[]


MIGRATE_TABLE: Final = "migratehistory"
