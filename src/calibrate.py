"""Calibration routines for effective-rate passthrough model."""

from __future__ import annotations

from typing import Any, Dict, Tuple
import itertools
import numpy as np
import pandas as pd

try:
    from . import transforms
except ImportError: # pytest.ini compatibility
    import transforms


def _design_matrix(macro_df: pd.DataFrame, hl_short: float, hl_nb: float) -> tuple[pd.DataFrame, float, float]:
    alpha_s = transforms.half_life_to_alpha(hl_short)
    alpha_nb = transforms.half_life_to_alpha(hl_nb)
    r_nb_raw = transforms.weighted_curve(macro_df['r2y'], macro_df['r5y'], macro_df['r10y'], [0.2, 0.4, 0.4])
    r_s = transforms.ema(macro_df['r3m'], alpha_s)
    r_nb = transforms.ema(r_nb_raw, alpha_nb)
    # Orthogonalize r_nb against r_short to improve identifiability
    rs = r_s.fillna(method='ffill').fillna(0.0).astype(float)
    rnb = r_nb.fillna(method='ffill').fillna(0.0).astype(float)
    denom = float((rs * rs).sum()) or 1.0
    a = float((rnb * rs).sum()) / denom
    r_nb_resid = rnb - a * rs
    # Scale GDP to reduce numeric issues
    gdp = macro_df['nominal_gdp'].ffill().fillna(0.0).astype(float)
    gdp_scale = float(abs(gdp.iloc[0])) or 1.0
    gdp_scaled = gdp / gdp_scale
    X = pd.DataFrame({
        'r_short': rs,
        'r_nb_resid': r_nb_resid,
        'tips_m': macro_df['pce_infl_m'].ffill().fillna(0.0).astype(float),
        'gdp_scaled': gdp_scaled,
    }, index=macro_df.index)
    return X, a, gdp_scale


def _ols(y: pd.Series, X: pd.DataFrame) -> Tuple[np.ndarray, float]:
    # Solve min ||y - Xb||^2, no intercept
    A = X.values
    b = y.values
    coef, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
    rss = float(residuals[0]) if residuals.size else float(((A @ coef - b) ** 2).sum())
    return coef, rss


def _coefs_to_params(coef: np.ndarray, debt_initial: float) -> Dict[str, float]:
    # Map coefficients to shares and other_bps
    # coef order: [beta_s, beta_nb, beta_tips, gamma_gdp]
    beta_s, beta_nb, beta_tips, gamma = coef.tolist()
    denom = max(debt_initial, 1.0)
    share_short = max(0.0, min(1.0, 12.0 * beta_s / denom))
    share_nb = max(0.0, min(1.0, 12.0 * beta_nb / denom))
    share_tips = max(0.0, min(1.0, 12.0 * beta_tips / denom))
    other_bps = max(0.0, float(gamma * 12.0 * 10000.0))  # gamma * GDP/12 → annual bps
    # Enforce shares sum ≤ 1 by proportional scaling if necessary
    ssum = share_short + share_nb + share_tips
    if ssum > 1.0:
        scale = 1.0 / ssum
        share_short *= scale
        share_nb *= scale
        share_tips *= scale
    return {
        'share_SHORT': share_short,
        'share_NB': share_nb,
        'share_TIPS': share_tips,
        'other_bps': other_bps,
    }


def calibrate_params(ieod_series: pd.Series, macro_df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
    # Align inputs
    y = ieod_series.reindex(macro_df.index).fillna(0.0)
    debt_initial = float(config.get('model', {}).get('debt_public_initial', {}).get('value', 0.0))
    if debt_initial <= 0:
        # rough fallback: scale to GDP
        debt_initial = float(macro_df['nominal_gdp'].iloc[0])

    # Search grid for half-lives
    hl_short_grid = [3.0, 6.0, 12.0]
    hl_nb_grid = [12.0, 18.0, 24.0, 30.0]
    best = None
    for hl_s, hl_nb in itertools.product(hl_short_grid, hl_nb_grid):
        X, a, gdp_scale = _design_matrix(macro_df, hl_s, hl_nb)
        coef, rss = _ols(y, X)
        # Convert orthogonalized coefficients back to original betas
        beta_nb = float(coef[1])
        beta_s = float(coef[0]) - a * beta_nb
        beta_tips = float(coef[2])
        gamma_scaled = float(coef[3])
        gamma = gamma_scaled / gdp_scale
        coef_orig = np.array([beta_s, beta_nb, beta_tips, gamma], dtype=float)
        params = _coefs_to_params(coef_orig, debt_initial)
        score = rss
        if best is None or score < best[0]:
            best = (score, hl_s, hl_nb, params)

    assert best is not None
    _, hl_s_b, hl_nb_b, params_b = best
    params_b['hl_SHORT'] = hl_s_b
    params_b['hl_NB'] = hl_nb_b
    return params_b



