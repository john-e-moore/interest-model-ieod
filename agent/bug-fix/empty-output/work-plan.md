Title: Fix exploding gdp_total and empty interest/debt outputs

Scope: Diagnose and correct unit handling and NaN propagation that lead to (a) unrealistically fast GDP growth and (b) zero/blank outputs for interest_total, debt_avg, and r_eff in the summary files.

Root causes (confirmed):
- Percent-as-decimal misuse:
  - In `input/macro.yaml`, annual rates are provided as percentages (e.g., 4.40 = 4.40%), but `src/io_utils.py` uses those values directly in compounding and rates math. This causes monthly compounding to treat 4.40 as 440% rather than 4.40%.
  - Affected series: `r3m`, `r2y`, `r5y`, `r10y`, `pce_infl` (annual), and `nominal_gdp_growth` (annual growth). All need conversion from percent to decimal prior to compounding or EMAs.
- NaN propagation from annual series starting in 2025:
  - Annual macro series in `macro.yaml` begin in 2025, but the model index starts at 2010. The current annual-to-monthly expansion forward-fills from the first annual observation, leaving 2010–2024 as NaN. These NaNs flow into model math and aggregation, yielding zeros/blank for `interest_total`, `debt_avg`, and `r_eff` in earlier years.
  - Specifically: `expand_macro_series` builds monthly index 2010–2055, expands annual series by forward-fill from 2025 onward, leaving pre-2025 values as NaN.

Fix plan:
1) Normalize units at load time
   - File: `src/io_utils.py`
   - In `expand_macro_series`, after retrieving each macro series, convert percentage inputs to decimal by dividing by 100.0 before any math:
     - For annual rate series (`pce_infl` and `nominal_gdp_growth`), divide the annual percentages by 100.0, then apply `_annual_to_monthly_compounded`.
     - For monthly/annual yield levels used directly in EMAs (`r3m`, `r2y`, `r5y`, `r10y`), divide by 100.0.
   - Ensure `primary_deficit` (given as % of GDP) is also divided by 100.0 at load so later conversions to levels use decimals.

2) Backfill annual series to model start
   - File: `src/io_utils.py`
   - For `get_series(..., default_freq="A")`, after building the annual series and reindexing to year-end points, use both ffill and bfill across the monthly index window so that pre-2025 months have the 2025 value rather than NaN. Specifically, when reindexing to `idx`, apply `method="ffill"` and then `.fillna(method="bfill")` so the entire 2010–2055 span is populated.
   - Alternatively, explicitly align to the full monthly index and call `.reindex(idx).ffill().bfill()`.

3) Correct GDP level construction
   - File: `src/io_utils.py`
   - Ensure `gdp_growth_a` values are decimals (step 1) before compounding to `gdp_growth_m` using `_annual_to_monthly_compounded`.
   - Verify `nominal_gdp_initial.value` is a level in USD. The compounding loop should multiply by `(1 + monthly_growth)` each month. No percent units should remain.

4) Validate interest math units
   - File: `src/model.py`
   - Confirm that `r_short`, `r_nb`, and `tips_m` are decimal monthly rates when used:
     - `r_short` and `r_nb` should be decimal annual rates passed through an EMA and then divided by 12.0 when applied to monthly interest calculations, or alternatively converted to monthly rates before use. The current code uses `r_short * debt_prev * share / 12.0` which assumes `r_short` is an annual decimal rate. With step 1 applied (divide by 100 at load), this remains consistent.
     - `tips_m` should represent monthly decimal inflation; with step 1 and `_annual_to_monthly_compounded`, this is already monthly. Keep `int_tips = (tips_m + r_tips_coupon/12) * debt_prev * share_tips`.
   - Ensure `other_bps` usage remains in basis points with conversion `(bps / 10000 / 12) * GDP`.

5) Guard against NaNs in aggregation
   - File: `src/aggregate.py`
   - After grouping, call `.fillna(0.0)` for `interest_total` and `Debt` before computing means/sums if necessary, or rely on step 2 which removes NaNs at the source. Optionally compute `r_eff` with safe division: set to NaN where `debt_avg == 0`.

6) Add tests and quick checks
   - Files: `tests/` (new tests) or augment existing ones
   - Add a unit test to assert that expanding `macro.yaml` produces decimal rates and non-NaN values over `model.start..end`.
   - Add a small sanity check asserting `gdp_total` CY grows approximately at specified annual growth, not orders of magnitude too fast.

Implementation notes:
- Be explicit about percent-to-decimal conversion immediately after parsing each series.
- Maintain current API; only fix unit conversions and backfilling behavior.

Acceptance criteria:
- `gdp_total` grows at realistic rates consistent with `nominal_gdp_growth` (as percent inputs).
- `interest_total` is nonzero post-fix; `debt_avg` and `r_eff` columns populate for CY and FY summaries across 2010–2055.
- No NaNs in `macro_df` over the model index for used columns.

Affected files:
- `src/io_utils.py`
- `src/model.py`
- `src/aggregate.py` (optional safeguard)

Rollout steps:
1. Implement `io_utils` fixes (percent normalization, backfill annual series).
2. Verify `model` math consistency post-normalization.
3. Rerun pipeline and spot-check `output/*/spreadsheets/summary_*.csv`.
4. Add/execute tests for macro expansion and aggregation sanity.


