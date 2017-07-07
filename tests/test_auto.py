import os.path as path

import peewee as pw


CURDIR = path.abspath(path.dirname(__file__))


def test_auto():
    from peewee_migrate.auto import diff_one, diff_many, model_to_code
    from peewee_migrate.cli import get_router

    router = get_router(path.join(CURDIR, 'migrations'), 'sqlite:///:memory:')
    router.run()
    migrator = router.migrator
    models = migrator.orm.values()
    Person_ = migrator.orm['person']
    Tag_ = migrator.orm['tag']

    code = model_to_code(Person_)
    assert code
    assert "default=dt.datetime.now" in code
    assert 'db_table = "person"' in code
    assert "order_by = ('-dob',)" in code

    changes = diff_many(models, [], migrator=migrator)
    assert len(changes) == 2

    class Person(pw.Model):
        first_name = pw.IntegerField()
        last_name = pw.CharField(max_length=1024, null=True, unique=True)
        tag = pw.ForeignKeyField(Tag_, on_delete='CASCADE', related_name='persons')

    changes = diff_one(Person, Person_, migrator=migrator)
    assert len(changes) == 6
    assert "on_delete='CASCADE'" in changes[0]
    assert "related_name='persons'" in changes[0]
    assert changes[-3] == "migrator.drop_not_null('person', 'last_name')"
    assert changes[-2] == "migrator.drop_index('person', 'last_name')"
    assert changes[-1] == "migrator.add_index('person', 'last_name', unique=True)"
