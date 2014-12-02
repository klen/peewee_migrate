from peewee import DateTimeField


def migrate(migrator, database):
    migrator.add_column('tag', 'created_at', DateTimeField(null=True))
