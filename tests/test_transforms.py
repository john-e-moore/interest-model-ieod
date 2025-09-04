import importlib


def test_import_transforms_module():
    assert importlib.import_module('transforms') is not None


