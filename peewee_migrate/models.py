from __future__ import annotations

import datetime as dt
from typing import Final

import peewee as pw


class MigrateHistory(pw.Model):
    """Presents the migrations in database."""

    id = pw.AutoField()
    # shortcut: create_table(safe=True) leaves existing tables without the constraint;
    # upgrade when a cross-process lock replaces this guard.
    name = pw.CharField(unique=True)
    migrated_at = pw.DateTimeField(default=lambda: dt.datetime.now(dt.UTC))

    def __str__(self) -> str:
        """String representation."""
        return self.name


MIGRATE_TABLE: Final = "migratehistory"
