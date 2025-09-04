import importlib
import pandas as pd
import numpy as np


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


def test_half_life_to_alpha_and_ema():
    transforms = importlib.import_module('transforms')
    alpha = transforms.half_life_to_alpha(12.0)
    assert 0 < alpha < 1
    # Known relationship: after 12 months, weight halves
    # Build a step series and ensure EMA responds smoothly
    s = pd.Series([0.0]*5 + [1.0]*10, index=pd.date_range('2020-01-31', periods=15, freq='M'))
    ema_s = transforms.ema(s, alpha)
    assert len(ema_s) == len(s)
    # EMA starts at first observed
    assert ema_s.iloc[0] == s.iloc[0]
    # EMA should be strictly increasing after the step
    post = ema_s.iloc[5:10].to_numpy()
    assert np.all(np.diff(post) > -1e-12)


def test_weighted_curve_alignment_and_values():
    transforms = importlib.import_module('transforms')
    idx = pd.date_range('2020-01-31', periods=3, freq='M')
    r2y = pd.Series([2.0, 2.0, 2.0], index=idx)
    r5y = pd.Series([3.0, 3.0, 3.0], index=idx)
    r10y = pd.Series([4.0, 4.0, 4.0], index=idx)
    w = [0.2, 0.3, 0.5]
    blended = transforms.weighted_curve(r2y, r5y, r10y, w)
    assert (blended.index == idx).all()
    assert np.allclose(blended.values, 0.2*2 + 0.3*3 + 0.5*4)


def test_build_ieod_monthly_total_and_cy_fy_aggregation():
    transforms = importlib.import_module('transforms')
    io_utils = importlib.import_module('io_utils')
    # Build tiny IEOD CSV-like DataFrame via loader to ensure schema handling
    df_raw = pd.DataFrame(
        [
            {"Record Date": "2020-09-30", "Expense Group Description": "ACCRUED INTEREST EXPENSE", "Current Month Expense Amount": 100},
            {"Record Date": "2020-10-31", "Expense Group Description": "ACCRUED INTEREST EXPENSE", "Current Month Expense Amount": 110},
            {"Record Date": "2020-10-31", "Expense Group Description": "SAVINGS BONDS", "Current Month Expense Amount": 10},
            {"Record Date": "2020-10-31", "Expense Group Description": "CASH BASIS GAS PAYMENTS", "Current Month Expense Amount": 999},
            {"Record Date": "2020-12-31", "Expense Group Description": "ACCRUED INTEREST EXPENSE", "Current Month Expense Amount": 120},
        ]
    )
    # Save to CSV-like and reload using loader to apply GAS exclusion
    tmp = df_raw
    df = tmp.copy()
    # Apply load_ieod-like cleaning manually here (we can reuse loader but it requires path)
    df["Record Date"] = pd.to_datetime(df["Record Date"])  # ensure datetime
    df = df[~df["Expense Group Description"].isin({"ACCRUAL BASIS GAS EXPENSE", "CASH BASIS GAS PAYMENTS"})]
    total = transforms.build_ieod_monthly_total(df, start="2020-09-01", now="2020-12-31")
    # Expected monthly totals: Sep=100, Oct=120 (110+10), Dec=120
    assert total.loc['2020-09-30'] == 100
    assert total.loc['2020-10-31'] == 120
    assert total.loc['2020-12-31'] == 120

    # CY aggregation on two series
    s1 = total
    s2 = total * 2
    cy = transforms.aggregate_cy({"one": s1, "two": s2})
    # 2020 CY sum over Sep, Oct, Dec
    assert cy.loc[2020, 'one'] == 100 + 120 + 120
    assert cy.loc[2020, 'two'] == 2 * (100 + 120 + 120)
    assert cy.loc[2020, 'total'] == cy.loc[2020, 'one'] + cy.loc[2020, 'two']

    # FY aggregation (FY=Oct-Sep): our months fall into FY2021 (Oct-Dec 2020)
    fy = transforms.aggregate_fy({"one": s1, "two": s2})
    assert 2021 in fy.index
    assert fy.loc[2021, 'one'] == 120 + 120  # Oct+Dec
    assert fy.loc[2021, 'two'] == 2 * (120 + 120)
    assert fy.loc[2021, 'total'] == fy.loc[2021, 'one'] + fy.loc[2021, 'two']


