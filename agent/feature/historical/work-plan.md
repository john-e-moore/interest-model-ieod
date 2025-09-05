### Historical Interest Expense – Work Plan

### Scope & Deliverables
- **Implement module**: `src/historical.py` (self-contained entrypoint with functions and a `main()`)
- **Write tests**: `tests/test_historical.py` with synthetic fixtures
- **Spreadsheets**: CSVs in `output/historical/spreadsheets/` and a combined Excel workbook
- **Visualizations**: PNGs in `output/historical/visualizations/`
- **Source data copies**: Files used saved to `output/historical/source_data/`

### Data Inputs
- **Interest Expense**: most recent file in `input/` matching `IntExp_*`
  - Filter rows: `Expense Category Description == "INTEREST EXPENSE ON PUBLIC ISSUES"`
  - Columns of interest: `Record Date`, `Current Month Expense Amount`, `Expense Type Description`
- **GDP**: `input/GDP.csv`
  - Drop rows older than year 2000
  - Quarterly series; expand to monthly via linear interpolation

### Core Processing Steps
1. **Load Interest Expense**
   - Identify latest `IntExp_*` file by modified time or sortable date in filename
   - Read, filter to public issues only; drop non-matching rows
   - Parse `Record Date` to date type; derive:
     - `Calendar Year` = date.year
     - `Month` = date.month (1–12)
     - `Fiscal Year` = `date.year + 1 if date.month >= 10 else date.year`
2. **Prepare GDP**
   - Load `input/GDP.csv`; restrict to year >= 2000
   - Ensure quarterly timestamps on first day of quarter (e.g., 1/1, 4/1, 7/1, 10/1)
   - Create monthly index covering min→max quarterly dates; linearly interpolate values for in-between months only
   - Keep GDP in billions (no unit conversion); derive `Year` and `Month` for join
3. **Join GDP to Interest Expense**
   - Join on calendar `Year` and `Month`
   - Validate join coverage; warn or drop rows with missing GDP
4. **Aggregate Tables** (sum `Current Month Expense Amount`)
   - By `Calendar Year`
   - By `Fiscal Year`
   - By `Calendar Year`, `Month`
   - By `Fiscal Year`, `Month`
   - By `Calendar Year`, `Expense Type Description`
   - By `Fiscal Year`, `Expense Type Description`
   - Post-aggregation:
     - Rename sum to `Interest Expense`
     - Add `Interest Expense (millions)` = `Interest Expense / 1_000_000`
     - Add `Interest Expense (billions)` = `Interest Expense / 1_000_000_000`
     - Add `Interest Expense (% GDP)` = `100 * Interest Expense (billions) / GDP_billion`

### Stepwise Checkpoints (Development Workflow)
- After each core processing step:
  - For every table created or modified, write a CSV in `output/historical/spreadsheets/` prefixed with `temp_` (e.g., `temp_interest_raw.csv`, `temp_joined.csv`, `temp_agg_cy.csv`).
  - Reload that CSV and sanity-check:
    - Row/column counts look reasonable
    - No inappropriate NaNs or all-zero columns
    - Values are in the expected order of magnitude
  - If sanity passes, write/update tests for that step and request review.
  - Do not proceed to the next core step until review approval is given.

### Outputs
- **Spreadsheets (CSVs)**: one CSV per aggregation in `output/historical/spreadsheets/`
  - Clear, deterministic filenames, e.g., `summary_cy.csv`, `summary_fy.csv`, `by_month_cy.csv`, `by_type_fy.csv`, etc.
- **Excel workbook**: combine all tables into `output/historical/spreadsheets/historical_interest.xlsx` with one sheet per table
- **Charts (PNGs)** in `output/historical/visualizations/`:
  - Lines: `Interest Expense (billions)` vs Year (CY and FY separately)
  - Lines: `Interest Expense (% GDP)` vs Year (CY and FY separately)
  - Stacked areas: CY-by-type and FY-by-type for both `billions` and `% GDP` variants (if meaningful)
- **Source data copies**: copy the GDP and the selected `IntExp_*` file to `output/historical/source_data/` preserving filenames

### Implementation Outline (in `src/historical.py`)
- `find_latest_interest_file(input_dir) -> Path`
- `load_interest_expense(path) -> DataFrame`
- `derive_calendar_and_fiscal(df) -> DataFrame`
- `load_and_expand_gdp(gdp_path) -> DataFrame` (monthly, in billions)
- `join_gdp(interest_df, gdp_df) -> DataFrame`
- `build_aggregations(df) -> Dict[str, DataFrame]`
- `add_unit_columns(df) -> DataFrame` (millions, billions, % GDP)
- `write_csvs(tables, out_dir)`
- `write_temp_csv(table, name, out_dir)` (dev-only)
- `reload_and_sanity_check_temp_csv(path) -> None` (dev-only)
- `write_excel(tables, excel_path)`
- `plot_line_and_area_charts(tables, viz_dir)`
- `copy_source_data(files, dest_dir)`
- `main()` to orchestrate; allow running via `python -m src.historical`

### Testing Plan (`tests/test_historical.py`)
- **Development gating**: After each core step passes sanity on `temp_*.csv` and after review approval, implement or update the tests for that step before moving on.
- **Fixtures**: in-memory or temp files with small synthetic datasets
- **Unit tests**:
  - Filters only keep `INTEREST EXPENSE ON PUBLIC ISSUES`
  - Fiscal year derivation (e.g., Sep→FY=year, Oct→FY=year+1)
  - GDP interpolation: correct values for months between quarters
  - Join: all interest months within GDP range get GDP values
  - Aggregations: sums match expected; unit columns computed correctly
  - `% GDP`: uses billions; shape and numeric accuracy
  - Output writers: CSVs exist with expected columns; Excel contains expected sheets
  - Charts: PNG files are created and non-empty

### File/Folder Conventions
- Create directories if missing: `output/historical/spreadsheets/`, `output/historical/visualizations/`, `output/historical/source_data/`
- Deterministic filenames; avoid spaces; use lowercase with underscores

### Acceptance Criteria
- Running the module generates all specified CSVs, a combined Excel workbook, and PNGs
- `% GDP` present and numerically correct for rows with GDP coverage
- Source input files are copied to `output/historical/source_data/`
- All tests pass locally with `pytest`

### Operational Notes & Edge Cases
- If GDP coverage does not span interest months, restrict outputs to overlapping months or drop rows without GDP for `% GDP` only
- No extrapolation beyond first/last GDP quarter; interpolate only between known quarters
- Handle absence of any `IntExp_*` file with a clear error message
- Use pandas for vectorized operations; avoid Python loops over rows


