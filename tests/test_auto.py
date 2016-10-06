import peewee as pw


def test_auto():
    from peewee_migrate.auto import diff_one, diff_many, model_to_code
    from peewee_migrate.cli import get_router

    router = get_router('tests/migrations', 'sqlite:///:memory:')
    router.run()
    migrator = router.migrator
    models = migrator.orm.values()
    Person_ = migrator.orm['person']
    Tag_ = migrator.orm['tag']

    code = model_to_code(Person_)
    assert code

    changes = diff_many(models, [], migrator=migrator)
    assert len(changes) == 2

    class Person(pw.Model):
        first_name = pw.IntegerField()
        last_name = pw.CharField(max_length=1024, null=True)
        tag = pw.ForeignKeyField(Tag_, on_delete='CASCADE')

    changes = diff_one(Person, Person_, migrator=migrator)
    assert len(changes) == 4
    assert "on_delete='CASCADE'" in changes[0]
    assert changes[-1] == "migrator.drop_not_null('person', 'last_name')"
