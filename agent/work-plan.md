## Work Plan: Top-Down Net Interest Projection (IEOD-Calibrated)

### Scope & Deliverables
- **Goal**: Implement a parsimonious top-down model that projects U.S. net interest outlays monthly out to 30 years and aggregates to CY and FY, calibrated to IEOD history.
- **Primary outputs**: CY/FY spreadsheets and matplotlib charts under `output/` as specified.
- **Inputs**: Latest IEOD CSV (`input/IntExp_*` → choose most recent), `input/macro.yaml`, optional `input/FYOINT.xlsx` for QA.
- **Stack**: Python 3.x, numpy, pandas, matplotlib, pyyaml, openpyxl/xlsxwriter.

### Repository Layout to Implement
```
project/
  input/
    IntExp_20100531_20250731.csv      # example; code will auto-pick most recent matching IntExp_*
    FYOINT.xlsx                        # QA optional (present here)
    macro.yaml                         # scenarios & config
  output/
    calendar_year/{spreadsheets,visualizations}
    fiscal_year/{spreadsheets,visualizations}
  src/
    data_ingest.py
    transforms.py
    calibrate.py
    model.py
    aggregate.py
    charts.py
    io_utils.py
    run.py
  tests/
    test_ingest.py
    test_transforms.py
    test_calibrate.py
    test_model.py
    test_aggregate.py
    test_end_to_end.py
```

### Milestones & Tasks

#### 1) Project scaffolding
- Create `src/` and `tests/` directories and the files listed above (empty stubs initially).
- Verify `requirements.txt` includes: numpy, pandas, matplotlib, pyyaml, openpyxl or xlsxwriter, pytest.
- Set up `pytest.ini` and a minimal `conftest.py` (fixtures for sample data paths).

#### 2) I/O utilities (`src/io_utils.py`)
- **IEOD file discovery**:
  - Implement `find_latest_ieod_csv(input_dir: str) -> Path` that selects the most recent file matching `IntExp_*` in `input/`.
  - Prefer parsing the trailing end-date in filenames (e.g., `IntExp_YYYYMMDD_YYYYMMDD.csv`) to pick the max end date; fall back to file modified time if parsing fails.
- **Loaders**:
  - `load_ieod(path: Path) -> pd.DataFrame`: enforce columns, parse dates, drop nulls, exclude GAS groups: `ACCRUAL BASIS GAS EXPENSE`, `CASH BASIS GAS PAYMENTS`.
  - `load_macro_yaml(path: Path) -> dict`: read YAML and validate required sections.
  - `expand_macro_series(cfg: dict) -> pd.DataFrame`: expand annual to monthly (repeat/linear per options), align to month-end index on `start..end`. For `pce_infl` (A), compute a flat monthly rate compounding to the annual rate; construct monthly `nominal_gdp` level from `nominal_gdp_initial` and `nominal_gdp_growth` (A→M); convert `primary_deficit` (% of GDP) to monthly USD: `(pct/100) * GDP_m / 12`.
  - `load_fyoint_optional(path: Path = 'input/FYOINT.xlsx') -> Optional[pd.DataFrame]`: load if present for QA.
- **Persistence**:
  - `save_parameters(params: dict, output_dir: Path) -> Path` writes `output/parameters_{timestamp}.json`.

#### 3) Ingest & transforms (`src/data_ingest.py`, `src/transforms.py`)
- `build_ieod_monthly_total(df_ieod: pd.DataFrame, start: str, now: str) -> pd.Series`:
  - Filter to `start..now`, group by month-end, sum included groups to `IEOD_total[m]`.
- Calendar & fiscal year aggregations:
  - `aggregate_cy(series_map: dict[str, pd.Series]) -> pd.DataFrame`.
  - `aggregate_fy(series_map: dict[str, pd.Series]) -> pd.DataFrame` (FY = Oct–Sep).
- Helper transforms:
  - `half_life_to_alpha(hl_m: float) -> float` and `ema(series, alpha) -> pd.Series` (backcast using first observed).
  - Weighted curve blend for N&B: `weighted_curve(r2y, r5y, r10y, weights)`.
- Optional QA:
  - If `FYOINT.xlsx` exists, compute FY totals from IEOD vs FY OMB series and report `% diff`.

#### 4) Calibration (`src/calibrate.py`)
- Inputs: `IEOD_total[m]`, macro history, and config defaults.
- Decision variables: `hl_SHORT`, `hl_NB`, `share_SHORT`, `share_NB`, `share_TIPS`, `other_bps` (unless fixed in config).
- Objective: weighted MSE on FY totals (primary) + penalty on CY errors (secondary).
- Constraints: shares sum ≤ 1 (remainder OTHER) or fix OTHER via rule.
- Outputs: calibrated params dict and historical bucket contributions; persist via `save_parameters`.
- API:
  - `calibrate_params(ieod_series, macro_df, config) -> dict[str, Any]`.

#### 5) Forecast engine (`src/model.py`)
- Monthly loop on grid `start..end`:
  - Pull macro: `r3m, r2y, r5y, r10y, pce_infl (monthly-ized), primary_deficit_pct_gdp (A→M), nominal_gdp (level from initial + growth)`.
  - Compute effective rates with EMAs per calibrated half-lives:
    - `r_SHORT = ema(r3m)`; `r_NB = ema(weighted_curve)`; `tips_acc = pce_infl_m`.
  - Bucket sizes: `Debt[t-1] * share_bucket[t]` (shares constant or slow drift per config).
  - Bucket interest:
    - `Int_SHORT = r_SHORT * Debt[t-1] * share_SHORT / 12`
    - `Int_NB    = r_NB    * Debt[t-1] * share_NB    / 12`
    - `Int_TIPS  = (tips_acc + r_tips_coupon) * Debt[t-1] * share_TIPS / 12` (default coupon 0)
    - `Int_OTHER = other_rule(params, GDP[t])` (e.g., `bps_gdp * GDP / 10000 / 12`)
  - Net interest and debt recursion:
    - `NetInt = sum(bucket)`; `Debt[t] = Debt[t-1] + PrimaryDef_level[t] + NetInt[t]`, with `PrimaryDef_level[t] = (primary_deficit_pct_gdp[y]/100) * GDP[t] / 12`.
  - Effective portfolio rate: `r_eff = 12 * NetInt[t] / Debt[t-1]`.
- Return monthly DataFrame with buckets, totals, `Debt`, `r_eff`.

#### 6) Aggregation (`src/aggregate.py`)
- Build CY and FY tables:
  - `interest_total_{cy,fy}`, `interest_by_bucket_{cy,fy}`.
  - `r_eff_{cy,fy} = interest_total / avg_debt_{cy,fy}`.
  - `% of GDP` metrics using CY/FY GDP aggregates.

#### 7) Outputs (`src/charts.py` and Excel writers)
- Excel workbooks: `output/calendar_year/spreadsheets/results_cy.xlsx`, `output/fiscal_year/spreadsheets/results_fy.xlsx` with tabs:
  - `summary`, `by_bucket_level`, `by_bucket_pct_gdp`, `macro_inputs`, `parameters`, `audit` (if QA available).
- Charts (matplotlib only), filenames per spec:
  - `eff_rate_{cy,fy}.png`
  - `interest_by_bucket_{cy,fy}_levels.png`, `interest_by_bucket_{cy,fy}_pctgdp.png`
  - `total_interest_{cy,fy}_levels.png`, `total_interest_{cy,fy}_pctgdp.png`
  - `eff_rate_vs_interest_{cy,fy}_levels.png`, `eff_rate_vs_interest_{cy,fy}_pctgdp.png`
- Implement simple helper: `ensure_output_dirs()` to create directories.

#### 8) CLI runner (`src/run.py`)
- CLI or callable `main(config_path='input/macro.yaml', output_dir='output/', calibrate=True, use_cached_params=False)`:
  1. Resolve IEOD path via `find_latest_ieod_csv('input')` and load IEOD.
  2. Load macro config, expand macro series, align monthly grid.
  3. Calibrate or load stored params from `output/`.
  4. Run monthly forecast to `end`.
  5. Aggregate CY/FY.
  6. Write spreadsheets and charts to `output/` subfolders.
- Add basic logging (INFO level) and elapsed time reporting.

#### 9) Testing (pytest)
- Unit tests:
  - `test_ingest.py`: discovery of latest IEOD file; schema validation; GAS exclusion; monthly sums.
  - `test_transforms.py`: half-life → alpha; EMA filter; CY/FY aggregation; % of GDP math; N&B weighted curve; annual→monthly compounding for PCE inflation and GDP growth.
  - `test_calibrate.py`: synthetic data recovers known params approximation; constraints respected.
  - `test_model.py`: constant-rate scenario closed-form checks; TIPS accrual equals PCE-derived monthly inflation × share × principal.
  - `test_aggregate.py`: CY/FY aggregations match manual calculations on toy data.
- Integration:
  - `test_end_to_end.py`: tiny historical window (e.g., 2018–2022) ensures outputs exist, FY totals within tolerance vs IEOD, charts render.
- Fixtures:
  - Minimal `macro.yaml` and tiny synthetic IEOD CSV in `tests/fixtures/` for speed.

### Data Location & File Pattern Requirements
- **IEOD CSV**: Automatically select the most recent file matching `input/IntExp_*`.
  - Prefer parsing the filename end date; fallback to file modified time if needed.
- **FYOINT**: Optional QA input located at `input/FYOINT.xlsx`.

### Config schema (`input/macro.yaml`)
- Implement per spec (time grid, bucket config, macro series, options). Validate required fields; support annual→monthly repeat or linear as configured. Include `nominal_gdp_initial` (value/as_of), `nominal_gdp_growth` (A), `pce_infl` (A), and `primary_deficit` as % of GDP (A).

### Acceptance Criteria
- Average historical FY error vs IEOD ≤ ~3% over 2015–2024 (allow a bit more in high-inflation years if TIPS coupon is omitted).
- All CY/FY spreadsheets and charts created in correct directory structure with proper naming.
- Reproducible runs from a single `macro.yaml` and IEOD CSV.
- All unit and integration tests pass locally.

### Risks & Mitigations
- TIPS simplification (coupon=0) may bias levels in high-inflation years → document, allow optional coupon scalar.
- Macro interpolation choices affect results → configurable with tests for both repeat and linear.
- IEOD schema changes → strict column validation and clear error messages.

### Runbook (once implemented)
- Prepare `input/macro.yaml` and ensure IEOD/FYOINT files are in `input/`.
- Run: `python -m src.run --config input/macro.yaml` (or call `main()` in `src/run.py`).
- Inspect outputs under `output/`.
