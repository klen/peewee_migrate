from peewee import *


class Tag(Model):
    tag = CharField()

class Person(Model):
    first_name = CharField()
    last_name = CharField()
    dob = DateField(null=True)
