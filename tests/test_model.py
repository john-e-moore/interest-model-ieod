import importlib
import pandas as pd
import numpy as np


def test_import_model_module():
    assert importlib.import_module('model') is not None


def test_constant_rate_closed_form_debt_growth():
    model = importlib.import_module('model')
    transforms = importlib.import_module('transforms')

    idx = pd.date_range('2020-01-31', periods=12, freq='M')
    r = 0.06
    macro_df = pd.DataFrame({
        'r3m': r,
        'r2y': r,
        'r5y': r,
        'r10y': r,
        'pce_infl_m': 0.0,
        'primary_deficit_pct_gdp': 0.0,
        'nominal_gdp': 1e12,
    }, index=idx)
    params = {
        'hl_SHORT': 3.0,
        'hl_NB': 3.0,
        'share_SHORT': 0.3,
        'share_NB': 0.7,
        'share_TIPS': 0.0,
        'other_bps': 0.0,
    }
    debt0 = 1e12
    config = {'model': {'debt_public_initial': {'value': debt0, 'as_of': str(idx[0].date())}}}
    df = model.forecast_monthly(macro_df, params, config)
    S = params['share_SHORT'] + params['share_NB'] + params['share_TIPS']
    expected_last = debt0 * (1 + r * S / 12.0) ** len(idx)
    assert abs(df['Debt'].iloc[-1] - expected_last) / expected_last < 1e-6
    # r_eff consistency
    np.testing.assert_allclose(df['r_eff'].values[1:], 12.0 * (df['NetInt']/df['Debt'].shift(1)).values[1:], rtol=1e-12, atol=1e-12)


def test_tips_accrual_equals_monthly_inflation_times_principal_share():
    model = importlib.import_module('model')
    idx = pd.date_range('2020-01-31', periods=6, freq='M')
    infl_m = 0.003  # 0.3% monthly
    macro_df = pd.DataFrame({
        'r3m': 0.0,
        'r2y': 0.0,
        'r5y': 0.0,
        'r10y': 0.0,
        'pce_infl_m': infl_m,
        'primary_deficit_pct_gdp': 0.0,
        'nominal_gdp': 1e12,
    }, index=idx)
    params = {
        'hl_SHORT': 3.0,
        'hl_NB': 24.0,
        'share_SHORT': 0.0,
        'share_NB': 0.0,
        'share_TIPS': 0.2,
        'other_bps': 0.0,
    }
    debt0 = 1e9
    config = {'model': {'debt_public_initial': {'value': debt0, 'as_of': str(idx[0].date())}, 'r_tips_coupon': 0.0}}
    df = model.forecast_monthly(macro_df, params, config)
    # For t>=1: Int_TIPS[t] == pce_infl_m * Debt[t-1] * share_TIPS (no /12)
    expected = macro_df['pce_infl_m'] * df['Debt'].shift(1) * params['share_TIPS']
    # Ignore first since Debt[t-1] undefined
    pd.testing.assert_series_equal(df['Int_TIPS'].iloc[1:].round(6), expected.iloc[1:].round(6), check_names=False)


