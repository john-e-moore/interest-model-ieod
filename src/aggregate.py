"""Aggregation utilities for CY/FY tables from monthly model output."""

from __future__ import annotations

import pandas as pd
import numpy as np


def _to_year_groups(idx: pd.DatetimeIndex, fy: bool) -> pd.Index:
    if fy:
        return (idx + pd.DateOffset(months=3)).year
    return idx.year


def aggregate_model_cy(monthly_df: pd.DataFrame) -> pd.DataFrame:
    idx = monthly_df.index
    years = _to_year_groups(idx, fy=False)
    grouped = monthly_df.groupby(years)
    out = pd.DataFrame({
        'interest_total': grouped['NetInt'].sum(),
        'debt_avg': grouped['Debt'].mean(),
        'gdp_total': grouped['nominal_gdp'].sum() if 'nominal_gdp' in monthly_df.columns else 0.0,
    })
    out['r_eff'] = out['interest_total'] / out['debt_avg']
    out['interest_pct_gdp'] = np.where(out['gdp_total'] > 0, out['interest_total'] / out['gdp_total'], np.nan)
    return out


def aggregate_model_fy(monthly_df: pd.DataFrame) -> pd.DataFrame:
    idx = monthly_df.index
    years = _to_year_groups(idx, fy=True)
    grouped = monthly_df.groupby(years)
    out = pd.DataFrame({
        'interest_total': grouped['NetInt'].sum(),
        'debt_avg': grouped['Debt'].mean(),
        'gdp_total': grouped['nominal_gdp'].sum() if 'nominal_gdp' in monthly_df.columns else 0.0,
    })
    out['r_eff'] = out['interest_total'] / out['debt_avg']
    out['interest_pct_gdp'] = np.where(out['gdp_total'] > 0, out['interest_total'] / out['gdp_total'], np.nan)
    return out



