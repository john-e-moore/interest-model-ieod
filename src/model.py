"""Monthly forecast engine for interest model."""

from __future__ import annotations

from typing import Dict, Any
import pandas as pd
import numpy as np

try:
    from . import transforms
except ImportError: # pytest.ini compatibility
    import transforms


def forecast_monthly(macro_df: pd.DataFrame, params: Dict[str, Any], config: Dict[str, Any]) -> pd.DataFrame:
    idx = macro_df.index
    debt0_spec = config.get('model', {}).get('debt_public_initial', {})
    debt0 = float(debt0_spec.get('value', 0.0))
    if debt0 <= 0:
        debt0 = float(macro_df['nominal_gdp'].iloc[0])

    hl_s = float(params.get('hl_SHORT', 3.0))
    hl_nb = float(params.get('hl_NB', 24.0))
    alpha_s = transforms.half_life_to_alpha(hl_s)
    alpha_nb = transforms.half_life_to_alpha(hl_nb)

    # Ensure rate series are float decimals (annual for r_short/r_nb, monthly for tips_m)
    r2y_s = macro_df['r2y'].astype(float)
    r5y_s = macro_df['r5y'].astype(float)
    r10y_s = macro_df['r10y'].astype(float)
    r3m_s = macro_df['r3m'].astype(float)
    tips_m = macro_df['pce_infl_m'].astype(float)

    r_nb_raw = transforms.weighted_curve(r2y_s, r5y_s, r10y_s, [0.2, 0.4, 0.4])
    r_short = transforms.ema(r3m_s, alpha_s)
    r_nb = transforms.ema(r_nb_raw, alpha_nb)

    share_s = float(params.get('share_SHORT', 0.25))
    share_nb = float(params.get('share_NB', 0.60))
    share_tips = float(params.get('share_TIPS', 0.10))
    other_bps = float(params.get('other_bps', 0.0))
    r_tips_coupon = float(config.get('model', {}).get('r_tips_coupon', 0.0))

    debt = pd.Series(index=idx, dtype=float)
    int_short = pd.Series(index=idx, dtype=float)
    int_nb = pd.Series(index=idx, dtype=float)
    int_tips = pd.Series(index=idx, dtype=float)
    int_other = pd.Series(index=idx, dtype=float)
    netint = pd.Series(index=idx, dtype=float)
    r_eff = pd.Series(index=idx, dtype=float)

    # If a debt as_of is provided, ensure the starting state aligns closely with now; for now,
    # we treat provided value as the starting stock at the first index point.
    debt_prev = debt0
    for t, ts in enumerate(idx):
        s_s = share_s
        s_nb = share_nb
        s_t = share_tips

        int_s = r_short.loc[ts] * debt_prev * s_s / 12.0
        intn = r_nb.loc[ts] * debt_prev * s_nb / 12.0
        # TIPS accrual: monthly inflation (already monthly) plus optional coupon on adjusted principal
        intt = (tips_m.loc[ts] + r_tips_coupon/12.0) * debt_prev * s_t
        into = (other_bps / 10000.0 / 12.0) * float(macro_df['nominal_gdp'].astype(float).loc[ts])

        total = int_s + intn + intt + into
        debt_curr = debt_prev + total  # primary deficit set to 0 for these core tests
        reff = 12.0 * total / debt_prev if debt_prev != 0 else 0.0

        int_short.loc[ts] = int_s
        int_nb.loc[ts] = intn
        int_tips.loc[ts] = intt
        int_other.loc[ts] = into
        netint.loc[ts] = total
        r_eff.loc[ts] = reff
        debt.loc[ts] = debt_curr

        debt_prev = debt_curr

    out = pd.DataFrame({
        'Int_SHORT': int_short,
        'Int_NB': int_nb,
        'Int_TIPS': int_tips,
        'Int_OTHER': int_other,
        'NetInt': netint,
        'Debt': debt,
        'r_eff': r_eff,
    }, index=idx)
    return out



