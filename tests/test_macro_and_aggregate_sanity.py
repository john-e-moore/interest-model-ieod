import importlib
import pandas as pd
import numpy as np


def test_expand_macro_units_and_nonan():
    io_utils = importlib.import_module('io_utils')

    cfg = {
        'model': {
            'start': '2020-01-01',
            'end': '2020-12-31',
            'nominal_gdp_initial': {'value': 100.0, 'as_of': '2019-12-31'},
        },
        'macro_series': {
            # Annual percent inputs
            'r3m': {'frequency': 'A', 'values': {'2020': 4.8}},
            'r2y': {'frequency': 'A', 'values': {'2020': 5.0}},
            'r5y': {'frequency': 'A', 'values': {'2020': 5.2}},
            'r10y': {'frequency': 'A', 'values': {'2020': 5.4}},
            'pce_infl': {'frequency': 'A', 'values': {'2020': 2.4}},
            'primary_deficit': {'frequency': 'A', 'values': {'2020': -3.0}},
            'nominal_gdp_growth': {'frequency': 'A', 'values': {'2020': 4.0}},
        },
    }

    df = io_utils.expand_macro_series(cfg)

    # No NaNs across required columns
    cols = ['r3m', 'r2y', 'r5y', 'r10y', 'pce_infl_m', 'primary_deficit_pct_gdp', 'nominal_gdp']
    assert df[cols].isna().sum().sum() == 0

    # Rates are decimals
    assert abs(float(df['r3m'].iloc[0]) - 0.048) < 1e-12
    # Monthly inflation equals compounded monthly from 2.4% annual
    expected_monthly_infl = (1.0 + 0.024) ** (1.0 / 12.0) - 1.0
    assert abs(float(df['pce_infl_m'].iloc[0]) - expected_monthly_infl) < 1e-12
    # Primary deficit as decimal
    assert abs(float(df['primary_deficit_pct_gdp'].iloc[0]) - (-0.03)) < 1e-12
    # GDP compounding should increase level over the year
    assert float(df['nominal_gdp'].iloc[-1]) > float(df['nominal_gdp'].iloc[0])


def test_aggregate_sanity_interest_pct_gdp_and_r_eff():
    aggregate = importlib.import_module('aggregate')

    idx = pd.date_range('2020-01-31', periods=12, freq='M')
    netint_monthly = 120.0
    debt_series = np.linspace(1000.0, 1300.0, num=12)
    gdp_monthly = 10000.0

    monthly_df = pd.DataFrame({
        'NetInt': netint_monthly,
        'Debt': debt_series,
        'nominal_gdp': gdp_monthly,
    }, index=idx)

    cy = aggregate.aggregate_model_cy(monthly_df)

    # Expected totals
    interest_total_expected = netint_monthly * 12.0
    gdp_total_expected = gdp_monthly * 12.0
    debt_avg_expected = float(np.mean(debt_series))

    assert abs(float(cy.loc[2020, 'interest_total']) - interest_total_expected) < 1e-12
    assert abs(float(cy.loc[2020, 'gdp_total']) - gdp_total_expected) < 1e-12
    assert abs(float(cy.loc[2020, 'debt_avg']) - debt_avg_expected) < 1e-12

    # r_eff and interest_pct_gdp formulas
    r_eff_expected = interest_total_expected / debt_avg_expected
    pct_gdp_expected = interest_total_expected / gdp_total_expected
    assert abs(float(cy.loc[2020, 'r_eff']) - r_eff_expected) < 1e-12
    assert abs(float(cy.loc[2020, 'interest_pct_gdp']) - pct_gdp_expected) < 1e-12


