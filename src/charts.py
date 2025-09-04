"""Output writers and charts for CY/FY results."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import json

import pandas as pd
import matplotlib.pyplot as plt


def ensure_output_dirs(base: str | Path) -> None:
    base = Path(base)
    for sub in [
        base / 'calendar_year' / 'spreadsheets',
        base / 'calendar_year' / 'visualizations',
        base / 'fiscal_year' / 'spreadsheets',
        base / 'fiscal_year' / 'visualizations',
    ]:
        sub.mkdir(parents=True, exist_ok=True)


def write_workbooks(cy: pd.DataFrame, fy: pd.DataFrame, macro_df: pd.DataFrame, params: Dict[str, Any], base: str | Path) -> None:
    base = Path(base)
    cy_path = base / 'calendar_year' / 'spreadsheets' / 'results_cy.xlsx'
    fy_path = base / 'fiscal_year' / 'spreadsheets' / 'results_fy.xlsx'
    with pd.ExcelWriter(cy_path, engine='openpyxl') as xw:
        cy.to_excel(xw, sheet_name='summary')
        macro_df.to_excel(xw, sheet_name='macro_inputs')
        pd.DataFrame({'param': list(params.keys()), 'value': list(params.values())}).to_excel(xw, sheet_name='parameters', index=False)
    with pd.ExcelWriter(fy_path, engine='openpyxl') as xw:
        fy.to_excel(xw, sheet_name='summary')
        macro_df.to_excel(xw, sheet_name='macro_inputs')
        pd.DataFrame({'param': list(params.keys()), 'value': list(params.values())}).to_excel(xw, sheet_name='parameters', index=False)


def _plot_line(df: pd.DataFrame, x: str, y: str, title: str, out: Path) -> None:
    plt.figure()
    df[y].plot()
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out)
    plt.close()


def plot_basic_charts(cy: pd.DataFrame, fy: pd.DataFrame, base: str | Path) -> None:
    base = Path(base)
    _plot_line(cy, x='year', y='r_eff', title='Effective Rate CY', out=base / 'calendar_year' / 'visualizations' / 'eff_rate_cy.png')
    _plot_line(fy, x='year', y='r_eff', title='Effective Rate FY', out=base / 'fiscal_year' / 'visualizations' / 'eff_rate_fy.png')
    _plot_line(cy, x='year', y='interest_total', title='Total Interest CY', out=base / 'calendar_year' / 'visualizations' / 'total_interest_cy_levels.png')
    _plot_line(fy, x='year', y='interest_total', title='Total Interest FY', out=base / 'fiscal_year' / 'visualizations' / 'total_interest_fy_levels.png')



