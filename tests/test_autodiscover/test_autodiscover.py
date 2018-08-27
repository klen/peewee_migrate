from peewee_migrate.router import load_models


def test_autodiscover_two_files_with_models():
    result = load_models('tests.test_autodiscover')
    assert len(result) == 12
