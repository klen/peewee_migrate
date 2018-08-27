import peewee as pw
from .base_model import BaseModel


class Object1(BaseModel):
    field_1 = pw.TextField(null=True)


class Object2(BaseModel):
    field_2 = pw.TextField(null=True)
