import importlib
import pandas as pd
import numpy as np


def _synthetic_macro(idx):
    # Create simple varying rates
    t = np.arange(len(idx))
    r3m = pd.Series(0.01 + 0.0005 * t, index=idx)
    r2y = pd.Series(0.015 + 0.0004 * t, index=idx)
    r5y = pd.Series(0.02 + 0.0003 * t, index=idx)
    r10y = pd.Series(0.025 + 0.0002 * t, index=idx)
    pce_a = pd.Series(0.024, index=idx)  # annual -> monthly in io_utils
    prim_def = pd.Series(3.0, index=idx)
    gdp = pd.Series(1e12 * (1.0 + 0.003) ** (t), index=idx)
    return r3m, r2y, r5y, r10y, pce_a, prim_def, gdp


def test_calibration_recovers_params_within_tolerance():
    transforms = importlib.import_module('transforms')
    io_utils = importlib.import_module('io_utils')
    calibrate = importlib.import_module('calibrate')

    idx = pd.date_range('2019-10-31', periods=24, freq='M')
    r3m, r2y, r5y, r10y, pce_a, prim_def, gdp = _synthetic_macro(idx)
    # Build macro_df in the same shape as expand_macro_series would produce
    cfg = {
        'model': {
            'start': str(idx[0].date()),
            'now': str(idx[-1].date()),
            'nominal_gdp_initial': {'value': float(gdp.iloc[0]), 'as_of': str(idx[0].date())},
            'debt_public_initial': {'value': 2e12, 'as_of': str(idx[0].date())},
        },
        'macro_series': {}
    }

    # Prepare macro df fields the calibrator needs
    df = pd.DataFrame({
        'r3m': r3m,
        'r2y': r2y,
        'r5y': r5y,
        'r10y': r10y,
        'pce_infl_m': pd.Series( (1+0.024)**(1/12)-1, index=idx ),
        'primary_deficit_pct_gdp': prim_def,
        'nominal_gdp': gdp,
    }, index=idx)

    # True parameters
    hl_SHORT_true = 3.0
    hl_NB_true = 24.0
    alpha_s = transforms.half_life_to_alpha(hl_SHORT_true)
    alpha_nb = transforms.half_life_to_alpha(hl_NB_true)
    r_nb = transforms.weighted_curve(df['r2y'], df['r5y'], df['r10y'], [0.2, 0.4, 0.4])
    r_s_ema = transforms.ema(df['r3m'], alpha_s)
    r_nb_ema = transforms.ema(r_nb, alpha_nb)

    debt0 = cfg['model']['debt_public_initial']['value']
    share_SHORT_true = 0.25
    share_NB_true = 0.60
    share_TIPS_true = 0.10
    other_bps_true = 5.0
    beta_s = debt0 * share_SHORT_true / 12.0
    beta_nb = debt0 * share_NB_true / 12.0
    beta_tips = debt0 * share_TIPS_true / 12.0

    y = beta_s * r_s_ema + beta_nb * r_nb_ema + beta_tips * df['pce_infl_m'] + (other_bps_true/10000.0/12.0) * df['nominal_gdp']

    params = calibrate.calibrate_params(y, df, cfg)

    # Check half-lives approx
    assert abs(params['hl_SHORT'] - hl_SHORT_true) <= 3
    assert abs(params['hl_NB'] - hl_NB_true) <= 6
    # Check shares within ~5pp
    assert abs(params['share_SHORT'] - share_SHORT_true) <= 0.05
    assert abs(params['share_NB'] - share_NB_true) <= 0.05
    assert abs(params['share_TIPS'] - share_TIPS_true) <= 0.05
    # Other within tolerance
    assert abs(params['other_bps'] - other_bps_true) <= 2.0


def test_calibration_constraints_respected():
    calibrate = importlib.import_module('calibrate')
    # Minimal macro df with zeros; any IEOD will drive coefficients to zero
    idx = pd.date_range('2020-01-31', periods=6, freq='M')
    df = pd.DataFrame({
        'r3m': 0.0,
        'r2y': 0.0,
        'r5y': 0.0,
        'r10y': 0.0,
        'pce_infl_m': 0.0,
        'primary_deficit_pct_gdp': 0.0,
        'nominal_gdp': 1e12,
    }, index=idx)
    ieod = pd.Series(1e9, index=idx)
    cfg = {'model': {'start': str(idx[0].date()), 'now': str(idx[-1].date()), 'debt_public_initial': {'value': 1e12, 'as_of': str(idx[0].date())}}}
    p = calibrate.calibrate_params(ieod, df, cfg)
    # Shares in [0,1] and sum ≤ 1
    ssum = p['share_SHORT'] + p['share_NB'] + p['share_TIPS']
    assert 0 <= p['share_SHORT'] <= 1
    assert 0 <= p['share_NB'] <= 1
    assert 0 <= p['share_TIPS'] <= 1
    assert ssum <= 1 + 1e-8


