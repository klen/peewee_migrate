from peewee_migrate.router import load_models


def fqn(obj):
    return obj.__module__ + '.' + obj.__qualname__


def test_autodiscover_two_files_with_models():
    result = load_models('tests.test_autodiscover')
    result = {fqn(x) for x in result}
    assert result == {
        'tests.test_autodiscover.some_folder_one.another_models.Object1',
        'tests.test_autodiscover.some_folder_one.another_models.Object2',
        'tests.test_autodiscover.some_folder_one.one_models.Object3',
        'tests.test_autodiscover.some_folder_three.base_model_s.Model1',
        'tests.test_autodiscover.some_folder_three.nested_referenced_model_s.Model3',
        'tests.test_autodiscover.some_folder_three.referenced_model_s.Model2',
        'tests.test_autodiscover.some_folder_two.another_model.Object1',
        'tests.test_autodiscover.some_folder_two.another_model.Object2',
        'tests.test_autodiscover.some_folder_two.base_model.BaseModel',
        'tests.test_autodiscover.some_folder_two.one_model.Object3',
    }
