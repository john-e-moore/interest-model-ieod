import importlib
from pathlib import Path
import time


def test_import_data_ingest_module():
    assert importlib.import_module('data_ingest') is not None


def test_find_latest_ieod_csv_prefers_end_date(tmp_path: Path, monkeypatch):
    # Create candidate files
    p1 = tmp_path / "IntExp_20190531_20200630.csv"
    p1.write_text("Record Date,Expense Group Description,Current Month Expense Amount\n")
    p2 = tmp_path / "IntExp_20100531_20250731.csv"
    p2.write_text("Record Date,Expense Group Description,Current Month Expense Amount\n")

    io_utils = importlib.import_module('io_utils')
    latest = io_utils.find_latest_ieod_csv(str(tmp_path))
    assert latest == p2


def test_find_latest_ieod_csv_fallback_mtime(tmp_path: Path):
    p1 = tmp_path / "IntExp_unknown.csv"
    p2 = tmp_path / "IntExp_na.csv"
    p1.write_text("x\n")
    p2.write_text("x\n")
    # Ensure different mtimes
    old = time.time() - 100
    new = time.time()
    Path(p1).touch()
    Path(p2).touch()
    # Set mtimes
    import os
    os.utime(p1, (old, old))
    os.utime(p2, (new, new))

    io_utils = importlib.import_module('io_utils')
    latest = io_utils.find_latest_ieod_csv(str(tmp_path))
    assert latest == p2


def test_load_ieod_excludes_gas(tmp_path: Path):
    csv_path = tmp_path / "IntExp_20240131_20241231.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Record Date,Expense Group Description,Current Month Expense Amount",
                "2024-01-31,ACCRUED INTEREST EXPENSE,100",
                "2024-01-31,ACCRUAL BASIS GAS EXPENSE,999",
                "2024-01-31,CASH BASIS GAS PAYMENTS,999",
                "2024-01-31,SAVINGS BONDS,50",
            ]
        )
    )
    io_utils = importlib.import_module('io_utils')
    df = io_utils.load_ieod(csv_path)
    assert set(df['Expense Group Description'].unique()) == {"ACCRUED INTEREST EXPENSE", "SAVINGS BONDS"}
    assert df['Current Month Expense Amount'].sum() == 150


def test_load_ieod_validates_schema(tmp_path: Path):
    bad = tmp_path / "IntExp_20240131_20241231.csv"
    # Missing amount column
    bad.write_text("Record Date,Expense Group Description\n2024-01-31,ACCRUED INTEREST EXPENSE\n")
    io_utils = importlib.import_module('io_utils')
    import pytest as _pytest
    with _pytest.raises(ValueError):
        io_utils.load_ieod(bad)


def test_load_fyoint_optional_absent_returns_none(tmp_path: Path):
    io_utils = importlib.import_module('io_utils')
    assert io_utils.load_fyoint_optional(tmp_path / "FYOINT.xlsx") is None


def test_load_fyoint_optional_present_loads(tmp_path: Path):
    import pandas as pd
    io_utils = importlib.import_module('io_utils')
    df = pd.DataFrame({"Year": [2020, 2021], "Value": [1, 2]})
    xls = tmp_path / "FYOINT.xlsx"
    df.to_excel(xls, index=False)
    loaded = io_utils.load_fyoint_optional(xls)
    assert loaded is not None
    assert list(loaded.columns) == ["Year", "Value"]


def test_save_parameters_writes_json(tmp_path: Path):
    import json
    io_utils = importlib.import_module('io_utils')
    params = {"alpha": 0.5, "beta": [1, 2, 3]}
    out = io_utils.save_parameters(params, tmp_path)
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["alpha"] == 0.5


