import importlib
import yaml
import pandas as pd


def test_import_transforms_module():
    assert importlib.import_module('transforms') is not None


def test_macro_yaml_loading_and_expand(fixtures_dir):
    io_utils = importlib.import_module('io_utils')
    cfg = io_utils.load_macro_yaml(fixtures_dir / 'macro.yaml')
    assert 'model' in cfg and 'macro_series' in cfg
    # Expand with empty series should still return a monthly DataFrame with required columns
    df = io_utils.expand_macro_series(cfg)
    # Expect columns exist even if empty
    expected_cols = {"r3m", "r2y", "r5y", "r10y", "pce_infl_m", "primary_deficit_pct_gdp", "nominal_gdp"}
    assert expected_cols.issubset(set(df.columns))


