import importlib


def test_import_model_module():
    assert importlib.import_module('model') is not None


