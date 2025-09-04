"""I/O utilities for IEOD interest model.

Implements:
- find_latest_ieod_csv
- load_ieod
- load_macro_yaml
- expand_macro_series
- load_fyoint_optional
- save_parameters
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Any
import json
import re
import yaml
import pandas as pd
import numpy as np


_IEOD_PATTERN = re.compile(r"^IntExp_([0-9]{8})_([0-9]{8})\\.csv$")
_EXCLUDE_GAS = {
    "ACCRUAL BASIS GAS EXPENSE",
    "CASH BASIS GAS PAYMENTS",
}


def find_latest_ieod_csv(input_dir: str | Path) -> Path:
    input_path = Path(input_dir)
    candidates = sorted([p for p in input_path.glob("IntExp_*.csv") if p.is_file()])
    if not candidates:
        raise FileNotFoundError(f"No IEOD CSV found under {input_path} matching IntExp_*.csv")

    def key_by_end_date(p: Path):
        m = _IEOD_PATTERN.match(p.name)
        if not m:
            return None
        try:
            return int(m.group(2))
        except Exception:
            return None

    parsed = [(p, key_by_end_date(p)) for p in candidates]
    with_dates = [p for p, k in parsed if k is not None]
    if with_dates:
        # choose max end date
        best = max(parsed, key=lambda pk: (-1, 0) if pk[1] is None else (0, pk[1]))
        return best[0]
    # Fallback to mtime
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest


def load_ieod(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path)
    required_cols = {"Record Date", "Expense Group Description", "Current Month Expense Amount"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"IEOD missing columns: {missing}")

    df = df.dropna(subset=["Record Date", "Current Month Expense Amount"])  # type: ignore[arg-type]
    # Parse dates
    df["Record Date"] = pd.to_datetime(df["Record Date"], errors="coerce")
    df = df.dropna(subset=["Record Date"])  # type: ignore[arg-type]
    # Exclude GAS
    df = df[~df["Expense Group Description"].isin(_EXCLUDE_GAS)].copy()
    return df


def load_macro_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("macro.yaml must parse to a dict")
    for key in ("model", "macro_series"):
        if key not in data:
            raise ValueError(f"macro.yaml missing required section: {key}")
    return data  # type: ignore[return-value]


def _month_end_range(start: str, end: str) -> pd.DatetimeIndex:
    idx = pd.date_range(start=start, end=end, freq="ME")
    return idx


def _annual_to_monthly_compounded(rate_annual: float) -> float:
    # Flat monthly rate such that (1+m)^12 - 1 = annual
    return (1.0 + rate_annual) ** (1.0 / 12.0) - 1.0


def expand_macro_series(cfg: dict[str, Any]) -> pd.DataFrame:
    model = cfg.get("model", {})
    start = model.get("start")
    end = model.get("end", model.get("now"))
    if not start or not end:
        raise ValueError("model.start and model.end/now required for macro expansion")
    idx = _month_end_range(start, end)

    ms = cfg.get("macro_series", {})
    def get_series(name: str, default_freq: str = "M") -> pd.Series:
        spec = ms.get(name, {}) or {}
        freq = spec.get("frequency", default_freq)
        values = spec.get("values", {}) or {}
        if freq == "M":
            # Map YYYY-MM to value or YYYY-MM-DD
            s = pd.Series(dtype=float)
            for k, v in values.items():
                d = pd.to_datetime(k)
                s.loc[d] = float(v)
            s = s.sort_index()
            s = s.reindex(idx)
            return s
        if freq == "A":
            # annual keyed by YYYY or YYYY-12-31
            s = pd.Series(dtype=float)
            for k, v in values.items():
                y = pd.to_datetime(k).year
                s.loc[pd.Timestamp(year=y, month=12, day=31)] = float(v)
            s = s.sort_index()
            # Expand to monthly by repeat
            s = s.reindex(pd.date_range(start=idx.min(), end=idx.max(), freq="YE"))
            s = s.reindex(idx, method="ffill")
            return s
        raise ValueError(f"Unsupported frequency for {name}: {freq}")

    r3m = get_series("r3m")
    r2y = get_series("r2y")
    r5y = get_series("r5y")
    r10y = get_series("r10y")

    # Annual PCE inflation to monthly rate path
    pce_a = get_series("pce_infl", default_freq="A").fillna(0.0)
    pce_m = pce_a.apply(_annual_to_monthly_compounded)

    # Primary deficit (% of GDP) annual → monthly by forward-fill
    prim_def_pct = get_series("primary_deficit", default_freq="A").fillna(0.0)

    # Nominal GDP: construct monthly level using initial level and annual growth
    gdp_growth_a = get_series("nominal_gdp_growth", default_freq="A").fillna(0.0)
    gdp_growth_m = gdp_growth_a.apply(_annual_to_monthly_compounded)
    gdp_initial = model.get("nominal_gdp_initial", {}).get("value", 0.0)
    # Build a monthly gdp level by compounding
    gdp = pd.Series(index=idx, dtype=float)
    level = float(gdp_initial)
    for i, ts in enumerate(idx):
        # apply monthly growth for that calendar year
        y = ts.year
        monthly_g = gdp_growth_m.loc[ts]
        level = level * (1.0 + monthly_g)
        gdp.iloc[i] = level

    out = pd.DataFrame(
        {
            "r3m": r3m.reindex(idx),
            "r2y": r2y.reindex(idx),
            "r5y": r5y.reindex(idx),
            "r10y": r10y.reindex(idx),
            "pce_infl_m": pce_m.reindex(idx),
            "primary_deficit_pct_gdp": prim_def_pct.reindex(idx),
            "nominal_gdp": gdp.reindex(idx),
        },
        index=idx,
    )
    return out


def load_fyoint_optional(path: str | Path = "input/FYOINT.xlsx") -> Optional[pd.DataFrame]:
    p = Path(path)
    if not p.exists():
        return None
    return pd.read_excel(p)


def save_parameters(params: dict[str, Any], output_dir: str | Path) -> Path:
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    ts = pd.Timestamp.utcnow().strftime("%Y%m%dT%H%M%SZ")
    outpath = outdir / f"parameters_{ts}.json"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, sort_keys=True)
    return outpath



