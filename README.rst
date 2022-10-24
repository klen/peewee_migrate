Peewee Migrate
##############

.. _description:

Peewee Migrate -- A simple migration engine for Peewee_ ORM

.. _badges:

.. image:: https://github.com/klen/peewee_migrate/workflows/tests/badge.svg
    :target: https://github.com/klen/peewee_migrate/actions/workflows/tests.yml
    :alt: Tests Status

.. image:: https://github.com/klen/peewee_migrate/workflows/release/badge.svg
    :target: https://github.com/klen/peewee_migrate/actions/workflows/release.yml
    :alt: Build Status

.. image:: https://img.shields.io/pypi/v/peewee-migrate
    :target: https://pypi.org/project/peewee-migrate/
    :alt: PYPI Version

.. image:: https://img.shields.io/pypi/pyversions/peewee-migrate
    :target: https://pypi.org/project/peewee-migrate/
    :alt: Python Versions

.. _contents:

.. contents::

.. _requirements:

Requirements
=============

- peewee >= 3.7

Dependency Note
---------------

For ``Peewee<3.0`` please use ``Peewee-Migrate==0.14.0``.
For ``Python<3.7`` please use ``Peewee-Migrate==1.1.6``.

.. _installation:

Installation
=============

**Peewee Migrate** should be installed using pip: ::

    pip install peewee-migrate

.. _usage:

Usage
=====

Do you want Flask_ integration? Look at Flask-PW_.

From shell
----------

Getting help: ::

    $ pw_migrate --help

    Usage: pw_migrate [OPTIONS] COMMAND [ARGS]...

    Options:
        --help  Show this message and exit.

    Commands:
        create   Create migration.
        migrate  Run migrations.
        rollback Rollback migration.

Create migration: ::

    $ pw_migrate create --help

    Usage: pw_migrate create [OPTIONS] NAME

        Create migration.

    Options:
        --auto                  FLAG  Scan sources and create db migrations automatically. Supports autodiscovery.
        --auto-source           TEXT  Set to python module path for changes autoscan (e.g. 'package.models'). Current directory will be recursively scanned by default.
        --database              TEXT  Database connection
        --directory             TEXT  Directory where migrations are stored
        -v, --verbose
        --help                        Show this message and exit.

Run migrations: ::

    $ pw_migrate migrate --help

    Usage: pw_migrate migrate [OPTIONS]

        Run migrations.

    Options:
        --name TEXT       Select migration
        --database TEXT   Database connection
        --directory TEXT  Directory where migrations are stored
        -v, --verbose
        --help            Show this message and exit.

Rollback migrations: ::

    $ pw_migrate rollback --help

    Usage: pw_migrate rollback [OPTIONS]

        Rollback a migration with given steps --count of last migrations as integer number

    Options:
        --count INTEGER   Number of last migrations to be rolled back.Ignored in
                            case of non-empty name

        --database TEXT   Database connection
        --directory TEXT  Directory where migrations are stored
        -v, --verbose
        --help            Show this message and exit.


From python
-----------

.. code-block:: python

    from peewee_migrate import Router
    from peewee import SqliteDatabase

    router = Router(SqliteDatabase('test.db'))

    # Create migration
    router.create('migration_name')

    # Run migration/migrations
    router.run('migration_name')

    # Run all unapplied migrations
    router.run()

Migration files
---------------

By default, migration files are looked up in ``os.getcwd()/migrations`` directory, but custom directory can be given.

Migration files are sorted and applied in ascending order per their filename.

Each migration file must specify ``migrate()`` function and may specify ``rollback()`` function

.. code-block:: python

    def migrate(migrator, database, fake=False, **kwargs):
        pass

    def rollback(migrator, database, fake=False, **kwargs):
        pass

.. _bugtracker:

Bug tracker
===========

If you have any suggestions, bug reports or
annoyances please report them to the issue tracker
at https://github.com/klen/peewee_migrate/issues

.. _contributing:

Contributing
============

Development of starter happens at github: https://github.com/klen/peewee_migrate


.. _license:

License
========

Licensed under a `BSD license`_.

.. _links:

.. _BSD license: http://www.linfo.org/bsdlicense.html
.. _klen: https://klen.github.io/
.. _Flask: http://flask.pocoo.org/
.. _Flask-PW: https://github.com/klen/flask-pw
.. _Peewee: http://docs.peewee-orm.com/en/latest
