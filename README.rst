Peewee Migrate
##############

.. _description:

Peewee Migrate -- A simple migration engine for Peewee

.. _badges:

.. image:: http://img.shields.io/travis/klen/peewee_migrate.svg?style=flat-square
    :target: http://travis-ci.org/klen/peewee_migrate
    :alt: Build Status

.. image:: http://img.shields.io/coveralls/klen/peewee_migrate.svg?style=flat-square
    :target: https://coveralls.io/r/klen/pewee_migrate
    :alt: Coverals

.. image:: http://img.shields.io/pypi/v/peewee_migrate.svg?style=flat-square
    :target: https://pypi.python.org/pypi/peewee_migrate
    :alt: Version

.. image:: http://img.shields.io/pypi/dm/peewee_migrate.svg?style=flat-square
    :target: https://pypi.python.org/pypi/peewee_migrate
    :alt: Downloads

.. _contents:

.. contents::

.. _requirements:

Requirements
=============

- python 2.7,3.3,3.4

.. _installation:

Installation
=============

**Peewee Migrate** should be installed using pip: ::

    pip install peewee_migrate

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
        --auto TEXT       Create migrations automatically. Set path to your models module.
        --database TEXT   Database connection
        --directory TEXT  Directory where migrations are stored
        -v, --verbose
        --help            Show this message and exit.

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

From python
-----------
::

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

Each migration file must specify ``migrate()`` function and may specify ``rollback()`` function::

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


Contributors
=============

* klen_ (Kirill Klenov)

.. _license:

License
=======

Licensed under a `BSD license`_.

.. _links:

.. _BSD license: http://www.linfo.org/bsdlicense.html
.. _klen: https://klen.github.io/
.. _Flask: http://flask.pocoo.org/
.. _Flask-PW: https://github.com/klen/flask-pw
