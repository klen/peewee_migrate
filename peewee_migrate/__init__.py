"""
    The package description.

"""
import datetime as dt
import logging

import peewee as pw


# Package information
# ===================

__version__ = "1.1.6"
__project__ = "peewee_migrate"
__author__ = "Kirill Klenov <horneds@gmail.com>"
__license__ = "BSD"


LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.StreamHandler())
LOGGER.setLevel(logging.INFO)


class MigrateHistory(pw.Model):

    """Presents the migrations in database."""

    name = pw.CharField()
    migrated_at = pw.DateTimeField(default=dt.datetime.utcnow)

    def __unicode__(self):
        """String representation."""
        return self.name

from .router import Migrator, Router # noqa
