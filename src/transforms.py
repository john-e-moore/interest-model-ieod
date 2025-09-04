"""Transforms and aggregations for interest model."""

from __future__ import annotations

from typing import Dict
import pandas as pd
import numpy as np


def half_life_to_alpha(half_life_months: float) -> float:
    if half_life_months <= 0:
        raise ValueError("half_life_months must be positive")
    return 1.0 - 0.5 ** (1.0 / float(half_life_months))


def ema(series: pd.Series, alpha: float) -> pd.Series:
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    if series.empty:
        return series.copy()
    out = series.astype(float).copy()
    out.iloc[0] = series.iloc[0]
    for i in range(1, len(series)):
        out.iloc[i] = alpha * float(series.iloc[i]) + (1.0 - alpha) * float(out.iloc[i - 1])
    out.index = series.index
    return out


def weighted_curve(r2y: pd.Series, r5y: pd.Series, r10y: pd.Series, weights) -> pd.Series:
    w = np.asarray(weights, dtype=float)
    if w.shape != (3,):
        raise ValueError("weights must be length-3 for r2y,r5y,r10y")
    # Align indexes
    idx = r2y.index.union(r5y.index).union(r10y.index)
    r2 = r2y.reindex(idx).astype(float)
    r5 = r5y.reindex(idx).astype(float)
    r10 = r10y.reindex(idx).astype(float)
    arr = np.vstack([r2.values, r5.values, r10.values])
    blended = np.nansum(arr.T * w, axis=1)
    return pd.Series(blended, index=idx)


def build_ieod_monthly_total(df_ieod: pd.DataFrame, start: str, now: str) -> pd.Series:
    # df_ieod must be cleaned (dates parsed, GAS excluded)
    df = df_ieod.copy()
    df = df[(df["Record Date"] >= pd.to_datetime(start)) & (df["Record Date"] <= pd.to_datetime(now))]
    df["month"] = df["Record Date"].dt.to_period("M").dt.to_timestamp("M")
    grouped = df.groupby("month")["Current Month Expense Amount"].sum().sort_index()
    grouped.index.name = None
    return grouped


def _aggregate_by_year(series_map: Dict[str, pd.Series], fy: bool) -> pd.DataFrame:
    # Align indexes across series at month-end
    all_idx = None
    for s in series_map.values():
        all_idx = s.index if all_idx is None else all_idx.union(s.index)
    all_idx = pd.DatetimeIndex(sorted(all_idx)) if all_idx is not None else pd.DatetimeIndex([])
    aligned = {k: v.reindex(all_idx).fillna(0.0) for k, v in series_map.items()}
    df = pd.DataFrame(aligned)
    if fy:
        # Fiscal year: Oct–Sep. Label by shifting date by +3 months and taking calendar year
        years = (df.index + pd.DateOffset(months=3)).year
    else:
        years = df.index.year
    out = df.groupby(years).sum()
    out["total"] = out.sum(axis=1)
    return out


def aggregate_cy(series_map: Dict[str, pd.Series]) -> pd.DataFrame:
    return _aggregate_by_year(series_map, fy=False)


def aggregate_fy(series_map: Dict[str, pd.Series]) -> pd.DataFrame:
    return _aggregate_by_year(series_map, fy=True)



