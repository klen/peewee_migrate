import peewee as pw


class Person(pw.Model):
    first_name = pw.IntegerField()
    last_name = pw.CharField(max_length=1024, null=True, unique=True)
    email = pw.CharField(index=True, unique=True)


class Color(pw.Model):
    id = pw.AutoField()
    name = pw.CharField(default='red')
