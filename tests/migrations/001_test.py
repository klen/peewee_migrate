from peewee import * # noqa


class Tag(Model):
    tag = CharField()


class Person(Model):
    first_name = CharField()
    last_name = CharField()
    dob = DateField(null=True)


def migrate(migrator, database):
    migrator.create_table(Tag)
    migrator.create_table(Person)
