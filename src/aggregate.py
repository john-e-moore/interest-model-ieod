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
    # Use min_count=1 for sums to avoid coercing all-NaN groups to 0.0
    interest_total = grouped['NetInt'].sum(min_count=1)
    debt_avg = grouped['Debt'].mean()
    # `nominal_gdp` in monthly_df is an annual-level series repeated monthly.
    # For CY aggregation, convert to a monthly flow by dividing by 12 when summing across months.
    gdp_total = (
        grouped['nominal_gdp'].sum(min_count=1) / 12.0
        if 'nominal_gdp' in monthly_df.columns else 0.0
    )

    out = pd.DataFrame({
        'interest_total': interest_total,
        'debt_avg': debt_avg,
        'gdp_total': gdp_total,
    })
    # Safe division: r_eff undefined where debt_avg == 0 or NaN
    out['r_eff'] = np.where(out['debt_avg'] > 0, out['interest_total'] / out['debt_avg'], np.nan)
    out['interest_pct_gdp'] = np.where(out['gdp_total'] > 0, out['interest_total'] / out['gdp_total'], np.nan)
    return out


def aggregate_model_fy(monthly_df: pd.DataFrame) -> pd.DataFrame:
    idx = monthly_df.index
    years = _to_year_groups(idx, fy=True)
    grouped = monthly_df.groupby(years)
    interest_total = grouped['NetInt'].sum(min_count=1)
    debt_avg = grouped['Debt'].mean()
    # Convert annual-level monthly `nominal_gdp` to FY flow by dividing by 12 when summing.
    gdp_total = (
        grouped['nominal_gdp'].sum(min_count=1) / 12.0
        if 'nominal_gdp' in monthly_df.columns else 0.0
    )

    out = pd.DataFrame({
        'interest_total': interest_total,
        'debt_avg': debt_avg,
        'gdp_total': gdp_total,
    })
    out['r_eff'] = np.where(out['debt_avg'] > 0, out['interest_total'] / out['debt_avg'], np.nan)
    out['interest_pct_gdp'] = np.where(out['gdp_total'] > 0, out['interest_total'] / out['gdp_total'], np.nan)
    return out



