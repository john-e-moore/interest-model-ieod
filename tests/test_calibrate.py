import importlib


def test_import_calibrate_module():
    assert importlib.import_module('calibrate') is not None


