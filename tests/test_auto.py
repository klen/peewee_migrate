import peewee as pw


def test_auto():
    from peewee_migrate.auto import diff_one, diff_many, model_to_code
    from peewee_migrate.cli import get_router

    router = get_router('tests/migrations', 'sqlite:///:memory:')
    router.run()
    migrator = router.migrator
    models = migrator.orm.values()
    Person_, _ = models

    code = model_to_code(Person_)
    assert code

    changes = diff_many(models, [])
    assert len(changes) == 2

    class Person(pw.Model):
        first_name = pw.IntegerField()
        last_name = pw.CharField(max_length=1024)

    changes = diff_one(Person_, Person)
    assert len(changes) == 2
