import peewee as pw


class Model3(pw.Model):
    text = pw.TextField(null=True)
