import os
from peewee_migrate.router import load_models, load_models_via_autodiscover

if os.name == 'nt':
    MODELS_ROOT_DIR = 'tests\\test_autodiscover'
    MIGRATIONS_DIR = 'tests\\test_autodiscover\\migrations'
else:
    MODELS_ROOT_DIR = 'tests/test_autodiscover'
    MIGRATIONS_DIR = 'tests/test_autodiscover/migrations'


class TestAutoDiscover:

    def test_autodiscover_two_files_with_models(self):
        result = load_models_via_autodiscover('.*models$', root_directory=MODELS_ROOT_DIR)
        assert len(result) == 3

    def test_autodiscover_two_files_model_extend(self):
        result = load_models_via_autodiscover('.*model$', root_directory=MODELS_ROOT_DIR)
        assert len(result) == 4


class TestProblemDescribe:
    def test_auto_one_model_missed(self):
        """Shows situation discribed in commit"""
        res = load_models('tests.test_autodiscover.some_folder_three.base_model_s')
        assert len(res) == 2
        """that's the problem, migrator based on other migrations and missed model creates 
         migration with no Model3(if Model3 wasnt previously created)/Model3 deletion(if Model3 was created)
         """

    def test_autodiscover_all_models_imported_for_migration(self):
        """Situation_fix"""
        res = load_models_via_autodiscover('.*model_s$', root_directory=MODELS_ROOT_DIR)
        assert len(res) == 3  # here all models imported, correct migration will be generated
