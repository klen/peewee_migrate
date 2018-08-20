import peewee as pw
from .referenced_model_s import Model2


class Model1(pw.Model):
    reference = pw.ForeignKeyField(Model2, null=True)