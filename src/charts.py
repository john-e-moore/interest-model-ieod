"""Output writers and charts for CY/FY results."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any
import json

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def ensure_output_dirs(base: str | Path) -> None:
    base = Path(base)
    for sub in [
        base / 'spreadsheets',
        base / 'visualizations',
    ]:
        sub.mkdir(parents=True, exist_ok=True)


def write_workbooks(cy: pd.DataFrame, fy: pd.DataFrame, macro_df: pd.DataFrame, params: Dict[str, Any], base: str | Path) -> None:
    base = Path(base)
    spreadsheets_dir = base / 'spreadsheets'
    cy_path = spreadsheets_dir / 'results_cy.xlsx'
    fy_path = spreadsheets_dir / 'results_fy.xlsx'
    with pd.ExcelWriter(cy_path, engine='openpyxl') as xw:
        cy.to_excel(xw, sheet_name='summary')
        macro_df.to_excel(xw, sheet_name='macro_inputs')
        pd.DataFrame({'param': list(params.keys()), 'value': list(params.values())}).to_excel(xw, sheet_name='parameters', index=False)
    with pd.ExcelWriter(fy_path, engine='openpyxl') as xw:
        fy.to_excel(xw, sheet_name='summary')
        macro_df.to_excel(xw, sheet_name='macro_inputs')
        pd.DataFrame({'param': list(params.keys()), 'value': list(params.values())}).to_excel(xw, sheet_name='parameters', index=False)

    # Also write individual CSVs for summary and macro_inputs in each spreadsheets folder
    spreadsheets_dir.mkdir(parents=True, exist_ok=True)
    # Save CSVs
    (spreadsheets_dir / 'summary_cy.csv').write_text(cy.to_csv(index=True))
    (spreadsheets_dir / 'summary_fy.csv').write_text(fy.to_csv(index=True))
    (spreadsheets_dir / 'macro_inputs_cy.csv').write_text(macro_df.to_csv(index=True))
    (spreadsheets_dir / 'macro_inputs_fy.csv').write_text(macro_df.to_csv(index=True))


def _plot_line(df: pd.DataFrame, x: str, y: str, title: str, out: Path, as_percent: bool = False, xlim: tuple | None = None) -> None:
    plt.figure()
    df[y].plot()
    plt.title(title)
    ax = plt.gca()
    if as_percent:
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
    if xlim is not None:
        try:
            ax.set_xlim(xlim)
        except Exception:
            pass
    plt.tight_layout()
    plt.savefig(out)
    plt.close()


def plot_basic_charts(cy: pd.DataFrame, fy: pd.DataFrame, base: str | Path) -> None:
    base = Path(base)
    vis_dir = base / 'visualizations'
    # Determine x-axis limits from data (already sliced to now..end upstream)
    cy_xlim = (int(cy.index.min()), int(cy.index.max())) if not cy.empty else None
    fy_xlim = (int(fy.index.min()), int(fy.index.max())) if not fy.empty else None
    # Effective rate (percentage)
    _plot_line(cy, x='year', y='r_eff', title='Effective Rate CY', out=vis_dir / 'eff_rate_cy.png', as_percent=True, xlim=cy_xlim)
    _plot_line(fy, x='year', y='r_eff', title='Effective Rate FY', out=vis_dir / 'eff_rate_fy.png', as_percent=True, xlim=fy_xlim)
    _plot_line(cy, x='year', y='interest_total', title='Total Interest CY', out=vis_dir / 'total_interest_cy_levels.png', xlim=cy_xlim)
    _plot_line(fy, x='year', y='interest_total', title='Total Interest FY', out=vis_dir / 'total_interest_fy_levels.png', xlim=fy_xlim)
    # Total interest as % of GDP (percentage)
    if 'interest_pct_gdp' in cy.columns:
        _plot_line(cy, x='year', y='interest_pct_gdp', title='Total Interest CY (% of GDP)', out=vis_dir / 'total_interest_cy_pctgdp.png', as_percent=True, xlim=cy_xlim)
    if 'interest_pct_gdp' in fy.columns:
        _plot_line(fy, x='year', y='interest_pct_gdp', title='Total Interest FY (% of GDP)', out=vis_dir / 'total_interest_fy_pctgdp.png', as_percent=True, xlim=fy_xlim)



