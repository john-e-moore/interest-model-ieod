Title: Time-frame fixes, visuals, macro initial alignment, and calibration weights

Scope: Diagnose and fix (a) output time window and chart axes to align with `model.now..model.end`, (b) add total interest as % of GDP visualization with correct percent formatting, (c) correct application of initial GDP and Debt `as_of` dates in monthly macro expansion, (d) ensure pre-`now` period is only used for calibration and not simulated/emitted, and (e) investigate/fix `parameters.json` weights (NB = 0, OTHER = 0) during calibration.

References (current behavior):
- Time grid expansion: `src/io_utils.py:expand_macro_series` builds monthly index with `start..end` and returns `macro_df`.
- Aggregation: `src/aggregate.py:aggregate_model_cy/aggregate_model_fy` group monthly model output by year and compute `interest_total`, `debt_avg`, `gdp_total`, `r_eff`, `interest_pct_gdp`.
- Charts: `src/charts.py:plot_basic_charts` calls `_plot_line` for `r_eff` and total interest; `_plot_line` ignores the `x` arg and plots the series directly from index.
- Pipeline: `src/run.py:main` passes full `macro_df` to `model.forecast_monthly`, aggregates, and writes outputs and charts; it also persists `parameters.json` via `io_utils.save_parameters`.
- Calibration: `src/calibrate.py` builds a design matrix and maps coefficients to `share_*` and `other_bps` in `_coefs_to_params`.

Problems to address (from bullets):
1) Visualizations should show x-axis from "now" to "end"; outputs should not include pre-`now` periods.
2) Add visualization: total interest as a percentage of GDP (CY and FY).
3) Format y-axis as percentage where appropriate (effective rate, % of GDP charts).
4) `macro_inputs_fy.csv` shows initial nominal GDP level applied at 2010 rather than at `model.nominal_gdp_initial.as_of` (same likely for initial debt). Fix alignment.
5) Pre-`now` should only be used for calibration; model should not simulate it, and outputs must only reflect `now..end`.
6) `parameters.json` shows SHORT=0.5, TIPS=0.5, NB=0, OTHER=0. Investigate whether calibration is working; fix if mapping/logic is wrong.

Diagnosis plan:
- Confirm `now` and `end` from `input/macro.yaml` are read as strings and parseable to timestamps. Trace through `run.main -> io_utils.load_macro_yaml -> expand_macro_series`.
- Inspect `macro_df.index.min()/max()` and compare to `start/now/end`. Verify that `macro_df` spans `start..end` (it does) and that initial GDP/debt alignment ignores `as_of` (current code compounds from `start`).
- Verify `model.forecast_monthly` consumes the full index and returns monthly output for the full window, which then gets fully aggregated to CY/FY including pre-`now`.
- Check `_plot_line` uses index implicitly for x; adjust slicing and axis limits to `now..end`.
- In `src/calibrate.py:_coefs_to_params`, confirm all three shares are returned. Currently `share_NB` is computed but not returned, which likely explains NB=0 in `parameters.json`.

Edits (concrete changes):
1) Timeframe: simulate with pre-`now` for state, but emit only `now..end`
  - File: `src/run.py`
    - After `monthly = model_mod.forecast_monthly(...)`, slice the DataFrame to `now..end` before aggregation and outputs:
      - `now_ts = pd.to_datetime(cfg['model']['now'])`
      - `end_ts = pd.to_datetime(cfg['model']['end'])`
      - `monthly_emit = monthly.loc[now_ts:end_ts]`
      - Pass `monthly_emit` into `aggregate_model_cy/fy` and downstream writers.
  - Rationale: Pre-`now` months remain available for calibration/state (e.g., EMAs) but are not included in outputs.

2) Charts: restrict x-axis and add % of GDP plots with percent formatting
  - File: `src/charts.py`
    - Update `_plot_line` to accept an optional `xlim` tuple and an optional y-axis formatter (percent when applicable). Ensure the x-axis start/end reflect `now.year..end.year` given CY/FY inputs indexed by year.
    - Add two charts: `total_interest_cy_pctgdp.png` and `total_interest_fy_pctgdp.png` based on `interest_pct_gdp`.
    - For `r_eff` and `% of GDP` charts, apply `matplotlib.ticker.PercentFormatter(1.0)` to the y-axis.
    - Ensure we plot only rows within desired year range (slice by index) and label axes appropriately.

3) Macro initial GDP and Debt alignment by `as_of`
  - File: `src/io_utils.py`
    - GDP:
      - Parse `as_of = cfg['model']['nominal_gdp_initial']['as_of']`.
      - Build `gdp_growth_m` as today, then construct `nominal_gdp` such that the level at the month containing `as_of` equals the provided initial value:
        - Find `anchor = idx[idx.get_indexer([pd.to_datetime(as_of)], method='nearest')[0]]` snapped to month-end within the model index.
        - Set `gdp.loc[anchor] = initial_level`.
        - Forward: for t > anchor, `gdp[t] = gdp[t-1] * (1 + g[t])`.
        - Backward: for t < anchor, `gdp[t] = gdp[t+1] / (1 + g[t+1])`.
      - This ensures initial GDP is applied at its `as_of` date, not at `start`.
    - Debt:
      - In `src/model.py`, treat `debt0` as the debt level at `now` (month-end), sourced from `model.debt_public_initial.value` with `as_of` nearest to `now`. If `as_of` differs from `now`, optionally scale via months of growth in a follow-up (usually negligible if very close); minimally, log a warning if mismatched.

4) Outputs limited to `now..end`
  - File: `src/charts.py` and `src/run.py`
    - Ensure only the sliced monthly and the derived CY/FY rows for years overlapping `now..end` are written to CSV/XLSX and plotted. For CY/FY, this will include partial first years; consider a config option later to start from first full CY/FY.

5) Calibration weights bug and validation
  - File: `src/calibrate.py`
    - In `_coefs_to_params`, include `'share_NB': share_nb` in the returned dict. Currently it is computed but not returned, which explains NB=0 in `parameters.json`.
    - Add lightweight logging (or return alongside params during development) of raw coefficients and resulting shares to debug odd splits like SHORT=0.5, TIPS=0.5, NB=0.
    - Ensure `ieod_series` and `macro_df` are aligned and restricted to `start..now` inside `calibrate_params` (they already align to `macro_df.index`; confirm we pass a `macro_df` clipped to `..now` from the runner).

6) Y-axis percent formatting
  - File: `src/charts.py`
    - Apply percent formatter to `r_eff` and `interest_pct_gdp` charts, while keeping dollar/billions formatting for level charts. Consider reading `options.chart_units_billions` from `macro.yaml` in a later pass to format level axes and labels consistently.

Testing and acceptance:
- Unit-level sanity checks:
  - Expand macro: assert `nominal_gdp` at `as_of` equals provided initial, and nearby months compound correctly forward/backward.
  - Calibration: create a synthetic macro/IEOD case (see `tests/test_calibrate.py` fixture patterns) and assert that the returned params include nonzero `'share_NB'` and that the sum of shares ≤ 1.
  - Runner slice: after `monthly_emit` slice, assert `monthly_emit.index.min() >= now_ts` and `max() <= end_ts`.
  - Aggregation slice: CY/FY outputs contain only years within `[now.year, end.year]`.
- Visuals: Verify files exist
  - `eff_rate_{cy,fy}.png` now display percent y-axis.
  - New: `total_interest_{cy,fy}_pctgdp.png` exist with percent y-axis.
  - Existing total interest level charts remain.
- CSVs/XLSX:
  - `spreadsheets/macro_inputs_fy.csv` shows `nominal_gdp` with the initial level at `as_of` month-end, not back at 2010.
  - `summary_{cy,fy}.csv` contain only years ≥ `now.year`.
- Parameters:
  - `parameters.json` includes `'share_NB'` and `'other_bps'` is reasonable (> 0 unless data strongly implies otherwise).

Proposed implementation order:
1) Fix calibration return dict to include `'share_NB'`; rerun quick test to validate `parameters.json`.
2) Implement `run.py` slicing (`monthly_emit`), wire into aggregation and charts/writers.
3) Update `charts.py` to (a) respect x-range and (b) add % GDP charts with percent formatting; also apply percent formatting to `r_eff`.
4) Implement GDP `as_of` anchoring (and minor debt `as_of` handling/logging) in `io_utils.expand_macro_series` and `model.forecast_monthly` respectively.
5) Add/adjust tests and rerun end-to-end.

Notes and tradeoffs:
- Clipping monthly data before aggregation yields partial CY/FY for the first/last years; this matches the "now..end only" requirement. If full-year-only rows are desired, add a config option later to drop partial boundary years.
- Anchoring GDP at `as_of` introduces backward compounding for pre-anchor months; those months are used only for calibration and state. This is acceptable since outputs are clipped to `now..end`.


