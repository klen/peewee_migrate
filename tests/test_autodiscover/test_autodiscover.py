import os
from peewee_migrate.router import load_models_via_autodiscover

if os.name == 'nt':
    MODELS_ROOT_DIR = 'tests\\test_autodiscover'
else:
    MODELS_ROOT_DIR = 'tests/test_autodiscover'


class TestAutoDiscover:

    def test_autodiscover_two_files_with_models(self):
        result = load_models_via_autodiscover('.*models$', root_directory=MODELS_ROOT_DIR)
        assert len(result) == 3

    def test_autodiscover_two_files_model_extend(self):
        result = load_models_via_autodiscover('.*model$', root_directory=MODELS_ROOT_DIR)
        assert len(result) == 4
