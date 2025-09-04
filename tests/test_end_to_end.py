import importlib
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib

matplotlib.use('Agg')


def test_outputs_directories_and_files_created(tmp_path: Path):
    charts = importlib.import_module('charts')
    # Create CY/FY small tables
    cy = pd.DataFrame({'interest_total': [1,2], 'debt_avg': [10, 20], 'gdp_total': [100, 200], 'r_eff': [0.1, 0.1], 'interest_pct_gdp': [0.01, 0.01]}, index=[2019, 2020])
    fy = cy.copy()
    params = {'k': 1}
    outdir = tmp_path / 'output'
    charts.ensure_output_dirs(outdir)
    # Write workbooks and charts
    charts.write_workbooks(cy, fy, pd.DataFrame(), params, outdir)
    charts.plot_basic_charts(cy, fy, outdir)

    # Assert directory structure and files
    assert (outdir / 'calendar_year' / 'spreadsheets' / 'results_cy.xlsx').exists()
    assert (outdir / 'fiscal_year' / 'spreadsheets' / 'results_fy.xlsx').exists()
    # Some charts
    assert any(p.suffix == '.png' for p in (outdir / 'calendar_year' / 'visualizations').glob('*.png'))
    assert any(p.suffix == '.png' for p in (outdir / 'fiscal_year' / 'visualizations').glob('*.png'))


def test_run_main_creates_outputs_with_default_params(tmp_path: Path, fixtures_dir: Path):
    run = importlib.import_module('run')
    # Prepare temp input with IEOD CSV
    input_dir = tmp_path / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    ieod = input_dir / 'IntExp_20180131_20181231.csv'
    ieod.write_text('\n'.join([
        'Record Date,Expense Group Description,Current Month Expense Amount',
        '2018-01-31,ACCRUED INTEREST EXPENSE,100',
        '2018-02-28,SAVINGS BONDS,10',
        '2018-02-28,CASH BASIS GAS PAYMENTS,999'
    ]))

    outdir = tmp_path / 'output'
    # Use fixture macro.yaml
    cfg_path = fixtures_dir / 'macro.yaml'
    run.main(config_path=str(cfg_path), input_dir=str(input_dir), output_dir=str(outdir), calibrate=False)

    assert (outdir / 'calendar_year' / 'spreadsheets' / 'results_cy.xlsx').exists()
    assert (outdir / 'fiscal_year' / 'spreadsheets' / 'results_fy.xlsx').exists()
    assert any((outdir / 'calendar_year' / 'visualizations').glob('*.png'))
    assert any((outdir / 'fiscal_year' / 'visualizations').glob('*.png'))


