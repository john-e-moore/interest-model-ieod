"""Historical Interest Expense – Step 1 implementation.

This module implements only Step 1 of the work plan:
- Locate the latest `IntExp_*` input file
- Load and filter to public issues interest expense
- Parse dates and derive calendar/fiscal fields

It also provides a small CLI to write a development CSV
`output/historical/spreadsheets/temp_interest_raw.csv` and execute simple
sanity checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import re
from typing import Optional

import pandas as pd


# -----------------------------
# Utilities and configurations
# -----------------------------

PUBLIC_ISSUES_DESC = "INTEREST EXPENSE ON PUBLIC ISSUES"


@dataclass(frozen=True)
class Paths:
    input_dir: Path
    spreadsheets_dir: Path

    @staticmethod
    def from_args(input_dir: Optional[str], out_dir: Optional[str]) -> "Paths":
        base = Path.cwd()
        in_dir = Path(input_dir) if input_dir else base / "input"
        out_spreadsheets = (
            Path(out_dir)
            if out_dir
            else base / "temp"
        )
        return Paths(in_dir, out_spreadsheets)


# -----------------------------
# Step 1: Interest Expense load
# -----------------------------

def _parse_date_from_filename(path: Path) -> Optional[pd.Timestamp]:
    """Try to parse a YYYYMMDD date token from an `IntExp_*` filename.

    Supports patterns like `IntExp_20100531_20250731.csv`.
    Returns the last date token if multiple are present.
    """
    m = re.findall(r"(\d{8})", path.name)
    if not m:
        return None
    try:
        # Prefer the last token which is typically the coverage end date
        return pd.to_datetime(m[-1], format="%Y%m%d", errors="coerce")
    except Exception:
        return None


def find_latest_interest_file(input_dir: Path | str) -> Path:
    """Identify the latest `IntExp_*` file by filename date or modification time.

    Selection order:
    1) If any file has a parseable YYYYMMDD token, pick the one with the
       maximum parsed date.
    2) Otherwise, fall back to the most recently modified file.
    """
    in_dir = Path(input_dir)
    candidates = sorted(in_dir.glob("IntExp_*"))
    if not candidates:
        raise FileNotFoundError(
            f"No files matching 'IntExp_*' in {in_dir.resolve()}"
        )

    dated: list[tuple[pd.Timestamp, Path]] = []
    for p in candidates:
        d = _parse_date_from_filename(p)
        if d is not None and pd.notna(d):
            dated.append((pd.Timestamp(d), p))

    if dated:
        dated.sort(key=lambda t: t[0])
        return dated[-1][1]

    # Fallback: latest by modified time
    candidates.sort(key=lambda p: p.stat().st_mtime)
    return candidates[-1]


def load_interest_expense(path: Path | str) -> pd.DataFrame:
    """Load and filter the interest expense CSV.

    - Filter rows where `Expense Category Description == PUBLIC_ISSUES_DESC`
    - Keep columns of interest: `Record Date`, `Current Month Expense Amount`,
      `Expense Type Description`
    - Parse `Record Date` to pandas datetime
    """
    usecols = [
        "Record Date",
        "Current Month Expense Amount",
        "Expense Type Description",
        "Expense Category Description",
    ]
    df = pd.read_csv(path, usecols=usecols, dtype={"Expense Type Description": "string"})

    # Filter to public issues only
    mask = df["Expense Category Description"].astype("string") == PUBLIC_ISSUES_DESC
    df_filtered = df.loc[mask, [
        "Record Date",
        "Current Month Expense Amount",
        "Expense Type Description",
    ]].copy()

    # Parse dates
    df_filtered["Record Date"] = pd.to_datetime(df_filtered["Record Date"], errors="coerce")
    df_filtered = df_filtered.dropna(subset=["Record Date"])  # drop rows with invalid dates

    # Ensure numeric amount
    df_filtered["Current Month Expense Amount"] = pd.to_numeric(
        df_filtered["Current Month Expense Amount"], errors="coerce"
    )

    return df_filtered.reset_index(drop=True)


def derive_calendar_and_fiscal(df: pd.DataFrame) -> pd.DataFrame:
    """Add Calendar Year, Month, and Fiscal Year columns.

    Fiscal Year = year + 1 if month >= 10 (Oct–Dec) else year
    """
    out = df.copy()
    dates = pd.DatetimeIndex(out["Record Date"]).tz_localize(None)
    out["Calendar Year"] = dates.year.astype(int)
    out["Month"] = dates.month.astype(int)
    out["Fiscal Year"] = (out["Calendar Year"] + (out["Month"] >= 10).astype(int)).astype(int)
    return out


# -----------------------------
# Step 2: GDP loader and monthly expansion
# -----------------------------

def load_and_expand_gdp(gdp_path: Path | str) -> pd.DataFrame:
    """Load quarterly GDP and expand to monthly via linear interpolation.

    Rules per plan:
    - Restrict to years >= 2000
    - Ensure quarterly timestamps on first day of quarter
    - Create monthly index covering min→max quarterly dates; linearly interpolate
      values for in-between months only (no extrapolation)
    - Keep GDP in billions (input is already in billions)
    - Derive `Year` and `Month` for joining later
    """
    dfq = pd.read_csv(gdp_path, usecols=["observation_date", "GDP"])  # billions
    dfq["Date"] = pd.to_datetime(dfq["observation_date"], errors="coerce")
    dfq = dfq.dropna(subset=["Date"]).copy()
    dfq = dfq.loc[dfq["Date"].dt.year >= 2000, ["Date", "GDP"]].copy()

    # Normalize to first day of the quarter
    def quarter_start(ts: pd.Timestamp) -> pd.Timestamp:
        m = ((ts.month - 1) // 3) * 3 + 1
        return pd.Timestamp(year=ts.year, month=m, day=1)

    dfq["Date"] = dfq["Date"].apply(quarter_start)
    dfq = dfq.drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)

    if dfq.empty:
        return pd.DataFrame(columns=["Date", "GDP_billion", "Year", "Month"])  # type: ignore

    # Monthly date range from first to last quarter start
    first = dfq["Date"].min()
    last = dfq["Date"].max()
    monthly_index = pd.date_range(first, last, freq="MS")  # month start

    # Build monthly frame and align quarter values at quarter starts
    gdf = pd.DataFrame({"Date": monthly_index})
    gdf = gdf.merge(dfq[["Date", "GDP"]], on="Date", how="left")

    # Interpolate linearly by index position (equal monthly steps), interior only
    gdf["GDP_billion"] = gdf["GDP"].interpolate(method="linear", limit_area="inside")
    gdf.drop(columns=["GDP"], inplace=True)

    gdf["Year"] = gdf["Date"].dt.year.astype(int)
    gdf["Month"] = gdf["Date"].dt.month.astype(int)
    return gdf


# -----------------------------
# Step 3: Join GDP to Interest Expense
# -----------------------------

def join_gdp(interest_df: pd.DataFrame, gdp_df: pd.DataFrame) -> pd.DataFrame:
    """Join monthly GDP onto interest expense by calendar Year and Month.

    Drops rows where GDP is missing. Caller may choose to warn instead.
    """
    req_interest_cols = {"Calendar Year", "Month"}
    req_gdp_cols = {"Year", "Month", "GDP_billion"}
    if not req_interest_cols.issubset(set(interest_df.columns)):
        raise ValueError("interest_df missing required calendar columns")
    if not req_gdp_cols.issubset(set(gdp_df.columns)):
        raise ValueError("gdp_df missing required columns")

    merged = interest_df.merge(
        gdp_df[["Year", "Month", "GDP_billion"]],
        left_on=["Calendar Year", "Month"],
        right_on=["Year", "Month"],
        how="left",
    )
    # Drop redundant Year
    if "Year" in merged.columns:
        merged = merged.drop(columns=["Year"])  # keep Calendar Year from interest_df
    # Drop rows without GDP coverage
    merged = merged.dropna(subset=["GDP_billion"]).reset_index(drop=True)
    return merged


# -----------------------------
# Dev CSV writer and sanity
# -----------------------------
def write_temp_csv(df: pd.DataFrame, name: str, out_dir: Path | str) -> Path:
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    path = out_dir_p / name
    df.to_csv(path, index=False)
    return path


def reload_and_sanity_check_temp_csv(path: Path | str) -> None:
    df = pd.read_csv(path)
    required_cols = {
        "Record Date",
        "Current Month Expense Amount",
        "Expense Type Description",
        "Calendar Year",
        "Month",
        "Fiscal Year",
    }
    missing = required_cols.difference(df.columns)
    if missing:
        raise AssertionError(f"Temp CSV missing columns: {sorted(missing)}")

    if len(df) == 0:
        raise AssertionError("Temp CSV has zero rows after filtering")

    if df["Current Month Expense Amount"].isna().all():
        raise AssertionError("All amounts are NaN; expected numeric values")

    if not df["Month"].between(1, 12, inclusive="both").all():
        raise AssertionError("Found invalid month values outside 1..12")


def write_temp_gdp(df: pd.DataFrame, out_dir: Path | str, name: str = "temp_gdp_monthly.csv") -> Path:
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    path = out_dir_p / name
    df.to_csv(path, index=False)
    return path


# -----------------------------
# CLI
# -----------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Historical Interest – Step 1 loader")
    p.add_argument("--input-dir", type=str, default=None, help="Directory containing IntExp_* files")
    p.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Output directory for temp CSVs (default: temp/ at project root)",
    )
    p.add_argument(
        "--temp-name",
        type=str,
        default="temp_interest_raw.csv",
        help="Filename for the development CSV",
    )
    p.add_argument(
        "--write-gdp",
        action="store_true",
        help="Also write expanded GDP monthly CSV to the output directory",
    )
    p.add_argument(
        "--write-joined",
        action="store_true",
        help="Also write interest joined with GDP as temp_joined.csv",
    )
    return p


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    paths = Paths.from_args(args.input_dir, args.out_dir)

    latest = find_latest_interest_file(paths.input_dir)
    print(f"Using interest expense file: {latest}")

    df0 = load_interest_expense(latest)
    df1 = derive_calendar_and_fiscal(df0)

    temp_path = write_temp_csv(df1, args.temp_name, paths.spreadsheets_dir)
    print(f"Wrote temp CSV: {temp_path}")

    # Sanity check by reloading
    reload_and_sanity_check_temp_csv(temp_path)
    print(
        "Sanity check passed:",
        f"rows={len(df1)}",
        f"date_range={[df1['Record Date'].min(), df1['Record Date'].max()]}",
    )

    if args.write_gdp:
        gdp_path = Path(paths.input_dir) / "GDP.csv"
        gdp_monthly = load_and_expand_gdp(gdp_path)
        gdp_temp = write_temp_gdp(gdp_monthly, paths.spreadsheets_dir, name="temp_gdp_monthly.csv")
        print(f"Wrote GDP monthly temp CSV: {gdp_temp}")

    if getattr(args, "write_joined", False):
        # Ensure we have GDP monthly
        gdp_path = Path(paths.input_dir) / "GDP.csv"
        gdp_monthly = load_and_expand_gdp(gdp_path)
        joined = join_gdp(df1, gdp_monthly)
        joined_path = write_temp_csv(joined, "temp_joined.csv", paths.spreadsheets_dir)
        print(f"Wrote joined temp CSV: {joined_path}")


if __name__ == "__main__":
    main()

 