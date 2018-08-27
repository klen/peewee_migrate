import peewee as pw
from .base_model import BaseModel


class Object3(BaseModel):
    field_3 = pw.TextField(null=True)
