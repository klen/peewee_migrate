import peewee as pw


class Object1(pw.Model):
    field_1 = pw.TextField(null=True)


class Object2(pw.Model):
    field_2 = pw.TextField(null=True)
