import peewee as pw
from .nested_referenced_model_s import Model3


class Model2(pw.Model):
    inner_reference = pw.ForeignKeyField(Model3, null=True)
