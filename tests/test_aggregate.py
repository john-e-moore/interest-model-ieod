import importlib


def test_import_aggregate_module():
    assert importlib.import_module('aggregate') is not None


