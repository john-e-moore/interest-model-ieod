from __future__ import annotations

from pathlib import Path
import pandas as pd

try:
    from src.historical import (
        load_interest_expense,
        derive_calendar_and_fiscal,
        find_latest_interest_file,
    )
except Exception:  # pragma: no cover - pytest path setup fallback
    from historical import (
        load_interest_expense,
        derive_calendar_and_fiscal,
        find_latest_interest_file,
    )


CSV_TEXT = """Record Date,Current Month Expense Amount,Expense Type Description,Expense Category Description,Other
2024-09-30,100.0,Treasury Notes,INTEREST EXPENSE ON PUBLIC ISSUES,x
2024-10-31,200.0,Treasury Bonds,INTEREST EXPENSE ON PUBLIC ISSUES,y
2024-10-31,300.0,Other,NOT PUBLIC,z
"""


def test_load_interest_expense_filters_and_parses(tmp_path: Path) -> None:
    csv_path = tmp_path / "IntExp_20240101_20241231.csv"
    csv_path.write_text(CSV_TEXT)

    df = load_interest_expense(csv_path)
    # Only two rows should remain after filtering by category
    assert len(df) == 2
    assert set(df.columns) == {
        "Record Date",
        "Current Month Expense Amount",
        "Expense Type Description",
    }
    assert pd.api.types.is_datetime64_any_dtype(df["Record Date"])  # parsed dates
    assert df["Current Month Expense Amount"].dtype.kind in {"i", "u", "f"}


def test_derive_calendar_and_fiscal_rules() -> None:
    df = pd.DataFrame(
        {
            "Record Date": pd.to_datetime(["2024-09-30", "2024-10-31"]),
            "Current Month Expense Amount": [100.0, 200.0],
            "Expense Type Description": ["A", "B"],
        }
    )
    out = derive_calendar_and_fiscal(df)
    assert list(out["Calendar Year"]) == [2024, 2024]
    assert list(out["Month"]) == [9, 10]
    # Oct should map to FY = year + 1
    assert list(out["Fiscal Year"]) == [2024, 2025]


def test_find_latest_interest_file_by_filename_date(tmp_path: Path) -> None:
    # Older by date
    (tmp_path / "IntExp_20190101_20191231.csv").write_text("a")
    # Newer by date
    (tmp_path / "IntExp_20200101_20250731.csv").write_text("b")
    # A file without parseable token should be ignored for date comparison
    (tmp_path / "IntExp_misc.csv").write_text("c")

    p = find_latest_interest_file(tmp_path)
    assert p.name == "IntExp_20200101_20250731.csv"
