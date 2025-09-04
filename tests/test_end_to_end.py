import importlib


def test_import_run_module():
    assert importlib.import_module('run') is not None


