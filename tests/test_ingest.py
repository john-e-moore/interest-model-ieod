import importlib


def test_import_data_ingest_module():
    assert importlib.import_module('data_ingest') is not None


