import pytest

from peewee_migrate.router import load_models


@pytest.mark.parametrize(
    ("path", "expected_count"),
    [
        ("tests.test_autodiscover.models1", 3),
        ("tests.test_autodiscover.models2", 4),
        ("tests.test_autodiscover.models3", 3),
    ],
)
def test_load_models(path, expected_count):
    result = load_models(path)
    assert len(result) == expected_count


def test_load_models_parent():
    result = load_models("tests.test_autodiscover")
    assert len(result) == 10
