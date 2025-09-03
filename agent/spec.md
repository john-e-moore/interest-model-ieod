# Spec: Top-Down Net Interest Projection (Effective Rate Passthrough, IEOD-Calibrated)

**Goal:** Produce accurate-enough **30-year projections** of U.S. **net interest outlays** at **fiscal year (FY)** and **calendar year (CY)** frequency using a parsimonious, issuance-agnostic model that is **calibrated to IEOD history** and driven by macro paths (yield curve, inflation, primary deficit, GDP).

**Stack:** Python 3.x, **numpy/pandas/matplotlib** (+ pyyaml for config).

---

## 1) High-Level Approach

We model net interest as the sum of 3–4 **portfolio buckets** whose **effective rates** pass through market rates with bucket-specific lags. The debt stock evolves by the **budget identity**. Parameters (lags, bucket shares, small residuals) are calibrated to **historical IEOD** aggregates.

**Buckets (recommended):**
1. **Bills/FRN-like (SHORT)** — accrues at short rate with fast passthrough.  
2. **Notes & Bonds (N&B)** — accrues at a curve blend with slow passthrough; includes premium/discount amortization implicitly.  
3. **TIPS** — coupon on adjusted principal + monthly inflation accrual driven by CPI.  
4. **Other / Nonmarketable (OTHER)** — small residual (Savings Bonds, misc.); modeled as small % of GDP or % of debt.

**Exclude** intragovernmental (GAS) groups when matching **net interest outlays**:
- `ACCRUAL BASIS GAS EXPENSE`
- `CASH BASIS GAS PAYMENTS`

**Core recursions (monthly):**
- **Debt identity:** `Debt[t] = Debt[t-1] + PrimaryDef[t] + NetInt[t]`  
- **Net interest:** `NetInt[t] = Σ_bucket Int_bucket[t] + Other[t]`  
- **Effective rate passthrough:** exponential/distributed lags of market rates by bucket

Outputs are aggregated to **CY** and **FY**; both **spreadsheets** (for chart data) and **visualizations** are produced.

---

## 2) Repository Layout & I/O Conventions

```
project/
  input/
    IEOD.csv                         # Interest Expense on the Public Debt Outstanding (monthly)
    macro.yaml                       # Macro scenarios & config (see schema below)
    optional/
      FYOINT.xlsx                    # For historical QA (optional)
  output/
    calendar_year/
      spreadsheets/
        results_cy.xlsx              # tidy tables for charts & audit
      visualizations/
        eff_rate_cy.png
        interest_by_bucket_cy_levels.png
        interest_by_bucket_cy_pctgdp.png
        total_interest_cy_levels.png
        total_interest_cy_pctgdp.png
        eff_rate_vs_interest_cy_levels.png
        eff_rate_vs_interest_cy_pctgdp.png
    fiscal_year/
      spreadsheets/
        results_fy.xlsx
      visualizations/
        eff_rate_fy.png
        interest_by_bucket_fy_levels.png
        interest_by_bucket_fy_pctgdp.png
        total_interest_fy_levels.png
        total_interest_fy_pctgdp.png
        eff_rate_vs_interest_fy_levels.png
        eff_rate_vs_interest_fy_pctgdp.png
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
  README.md
```

> All **inputs** are placed in `input/`. All **outputs** are written under `output/` split into **calendar_year/** and **fiscal_year/**, each with **spreadsheets/** and **visualizations/** subfolders.

---

## 3) Input Specifications

### 3.1 IEOD (CSV)
- Columns (minimum expected):  
  - `Record Date` (YYYY-MM-DD)  
  - `Expense Group Description` ∈ {`ACCRUED INTEREST EXPENSE`, `AMORTIZED DISCOUNT`, `AMORTIZED PREMIUM`, `MISCELLANEOUS INTEREST EXPENSE`, `SAVINGS BONDS`, `ACCRUAL BASIS GAS EXPENSE`, `CASH BASIS GAS PAYMENTS`}  
  - `Current Month Expense Amount` (USD)
- Validation:
  - Parse monthly; drop rows with null `Record Date` or amount.  
  - **Exclude GAS** groups (`ACCRUAL BASIS GAS EXPENSE`, `CASH BASIS GAS PAYMENTS`).

### 3.2 `macro.yaml` (Scenario & Parameters)

```yaml
meta:
  scenario_name: "baseline_2025q4"
  author: "you"

model:
  # Time grid
  start: "2010-01-01"   # historical calibration start
  now:   "2025-07-31"   # last historical month in IEOD
  end:   "2055-12-31"   # projection horizon
  freq: "M"             # monthly
  base_currency: "USD"
  nominal_gdp_units: "USD"   # level series; if annual, will be monthly-interpolated

  # Initial state
  debt_public_initial:
    value: 28100000000000   # optional; else infer from calibration
    as_of: "2025-09-30"

  # Bucket configuration
  buckets:
    SHORT:
      rate_source: "r3m"         # 3m T-bill proxy or FFR
      lag_half_life_months: 3    # passthrough speed (to calibrate; can override)
      share_initial: 0.25        # share of outstanding (for effective-rate mix)
    N_BONDS:
      rate_source: ["r2y","r5y","r10y"]
      rate_weights: [0.2,0.4,0.4]
      lag_half_life_months: 24
      share_initial: 0.60
    TIPS:
      rate_source: "cpi_infl_m"  # monthly inflation for accrual
      lag_half_life_months: 1
      share_initial: 0.10
    OTHER:
      rule: "pct_gdp"            # or "pct_debt"
      pct_gdp_bps: 5             # 0.05% of GDP per year (calibrated)

  # Optional dynamic share drift (simple; not issuance modeling)
  share_drift:
    enabled: false
    target_shares: {SHORT: 0.25, N_BONDS: 0.60, TIPS: 0.10, OTHER: 0.05}
    half_life_months: 60

macro_series:
  # Provide monthly series or annual values expanded to monthly.
  r3m:   {frequency: "M", values: {}}
  r2y:   {frequency: "M", values: {}}
  r5y:   {frequency: "M", values: {}}
  r10y:  {frequency: "M", values: {}}
  cpi_infl_m: {frequency: "M", values: {}}   # monthly rate (e.g., 0.003 = 0.3% m/m)
  primary_deficit: {frequency: "A", values: {}}  # USD level, annual -> monthly
  nominal_gdp:     {frequency: "A", values: {}}  # USD level, annual -> monthly

options:
  interpolation:
    annual_to_monthly: "repeat"  # or "linear"; for GDP levels often "linear"
  chart_units_billions: true
  random_seed: 42
```

---

## 4) Data Processing & Calibration

### 4.1 Ingest & Clean (`data_ingest.py`)
- Load IEOD, trim to `start..now`.  
- Remove GAS groups.  
- Create `month` key, ensure monthly amounts per group.  
- Produce historical **IEOD_total[m]** = sum of included groups.

### 4.2 Construct Historical Targets (`transforms.py`)
- Build **FY** (Oct–Sep) and **CY** (Jan–Dec) aggregations:  
  - `interest_total_{fy,cy}` (USD)  
  - Optional: import FYOINT for QA; compute `% diff`.

### 4.3 Effective Rate Buckets & Calibration (`calibrate.py`)
- **Effective rate filters (EMA):**  
  `α = 1 - 0.5**(1/half_life_months)`;  
  `r_eff_bucket[t] = α*r_src[t] + (1-α)*r_eff_bucket[t-1]`.
- **Bucket shares:** fixed from config or calibrated constants.  
- **TIPS accrual:** monthly accrual `tips_accr[t] = tips_principal[t-1] * cpi_infl_m[t]`.  
  - In top-down simplification, approximate `tips_principal ≈ share_TIPS * Debt[t-1]`.  
  - Optionally fit a scalar κ to IEOD history.  
- **Other:** rule-based (`pct_gdp` or `pct_debt`), with parameter to fit.  
- **Objective:** minimize FY (primary) and CY (secondary) errors vs **IEOD_total** (least squares).  
- **Outputs:** calibrated half-lives, shares, `OTHER` scalar(s), and historical bucket contributions.

---

## 5) Forecast Engine (`model.py`)

### 5.1 Monthly Step
1. **Pull macro**: `r3m, r2y, r5y, r10y, cpi_infl_m, primary_deficit, nominal_gdp`.  
2. **Effective rates:**  
   - `r_SHORT[t]  = ema(r3m, hl_SHORT)`  
   - `r_NB[t]     = ema(wavg(r2y,r5y,r10y), hl_NB)`  
   - `tips_acc[t] = cpi_infl_m[t]` (accrual; coupon optional as small constant)  
3. **Bucket sizes:** `Debt[t-1] * share_bucket[t]` (shares constant or slow drift).  
4. **Bucket interest:**
   - `Int_SHORT[t]  = r_SHORT[t]  * Debt[t-1] * share_SHORT[t] / 12`  
   - `Int_NB[t]     = r_NB[t]     * Debt[t-1] * share_NB[t]    / 12`  
   - `Int_TIPS[t]   = (tips_acc[t] + r_tips_coupon) * Debt[t-1] * share_TIPS[t] / 12` (default `r_tips_coupon = 0`)  
   - `Int_OTHER[t]  = other_rule(primary vars)` (e.g., `bps_gdp * GDP[t] / 10000 / 12`)  
5. **Net interest:** `NetInt[t] = Int_SHORT + Int_NB + Int_TIPS + Int_OTHER`.  
6. **Debt recursion:** `Debt[t] = Debt[t-1] + PrimaryDef[t] + NetInt[t]`.  
7. **Effective portfolio rate:** `r_eff_port[t] = 12 * NetInt[t] / Debt[t-1]`.

### 5.2 Aggregation (`aggregate.py`)
- **CY** and **FY** totals:
  - `interest_total_{cy,fy}`  
  - `interest_by_bucket_{cy,fy}`  
  - `r_eff_{cy,fy} = interest_total / avg_debt_{cy,fy}`  
  - `% of GDP` metrics using CY/FY GDP aggregates.

---

## 6) Outputs

### 6.1 Spreadsheets (Excel)
One workbook per period (`results_cy.xlsx`, `results_fy.xlsx`) with tidy tabs:

- `summary`: `year`, `debt_avg`, `interest_total`, `r_eff`, `gdp`, `interest_pct_gdp`  
- `by_bucket_level`: `year`, `SHORT`, `N_BONDS`, `TIPS`, `OTHER`, `total`  
- `by_bucket_pct_gdp`: same columns divided by GDP  
- `macro_inputs`: the **actual** periodized macro series used (post-interpolation)  
- `parameters`: calibrated or configured parameters used  
- `audit`: optional historical comparison vs IEOD/FYOINT if provided

### 6.2 Visualizations (Matplotlib)
> Use **matplotlib** only, single plot per chart, no seaborn or custom styles.

1. **Line:** Average effective rate paid by year (CY & FY)  
2. **Stacked area:** Interest expense by security type and year  
   - **Levels (USD, millions)** and **% of GDP**  
3. **Line:** Total interest expense by year  
   - **Levels (USD, millions)** and **% of GDP**  
4. **Combo (twin axes):** r_eff (line, left axis) and total interest (bars or line, right axis)  
   - **Levels** and **% of GDP** versions

**File names (examples):**
- `eff_rate_fy.png`  
- `interest_by_bucket_fy_levels.png`, `interest_by_bucket_fy_pctgdp.png`  
- `total_interest_fy_levels.png`, `total_interest_fy_pctgdp.png`  
- `eff_rate_vs_interest_fy_levels.png`, `eff_rate_vs_interest_fy_pctgdp.png`  
(Same for `_cy_` variants.)

**Units:**
- Render levels in **billions** on axes; store spreadsheet values in **USD**.  
- `% of GDP` uses FY/CY GDP aggregates.

---

## 7) Implementation Details

### 7.1 Utilities (`io_utils.py`)
- Load IEOD CSV with schema validation.  
- Load `macro.yaml`, expand annual → monthly:
  - **Rates**: annual to monthly via repeat or linear (configurable).  
  - **Primary deficit**: annual → monthly by equal split or supplied seasonal vector.  
  - **Nominal GDP**: annual level → monthly via linear interpolation of level.  
- Ensure monthly date index aligns to month-end.

### 7.2 Lag Filters (`transforms.py`)
- `half_life_to_alpha(hl_m) = 1 - 0.5**(1/hl_m)`  
- `ema(series, alpha)` with backcast (initialize with first observed).  
- Weighted curve blend for N&B.

### 7.3 Calibration (`calibrate.py`)
- Inputs: cleaned IEOD monthly totals and macro history.  
- Decision variables (unless fixed): `hl_SHORT`, `hl_NB`, `share_SHORT`, `share_NB`, `share_TIPS`, `other_bps`.  
- Loss: weighted MSE on FY levels (primary) + penalty on CY errors (secondary).  
- Constraints: shares sum ≤ 1 (remainder to OTHER) or fix OTHER via rule.  
- Output: parameter JSON/dict to be saved in `output/parameters_{timestamp}.json` and embedded in spreadsheets.

### 7.4 Model Runner (`run.py`)
CLI (or function) that:
1. Loads inputs.  
2. Calibrates (or loads stored params).  
3. Runs monthly projection to `end`.  
4. Aggregates to CY and FY.  
5. Writes spreadsheets + charts to the specified folders.

---

## 8) Testing Strategy (pytest)

**Unit**
- `test_ingest.py`: IEOD load, GAS exclusion, monthly sums.  
- `test_transforms.py`: half-life → α; EMA filter; CY/FY aggregation (edge months); %-of-GDP math.  
- `test_calibrate.py`: calibration on synthetic data recovers known params within tolerance.  
- `test_model.py`: constant-rate scenario produces closed-form results (e.g., geometric debt growth); TIPS accrual equals CPI path × principal share.  
- `test_aggregate.py`: aggregation matches manual calculations on toy data.

**Integration**
- `test_end_to_end.py`: tiny scenario (e.g., 2018–2022) asserts:
  - Output files exist in correct folders.  
  - FY totals within X% of IEOD when using historical macro.  
  - Charts render without error.

**Golden files** (optional):
- Store a small golden output and assert stability unless parameters change.

---

## 9) Acceptance Criteria

- Historical **FY** error vs IEOD ≤ **~3%** on average over 2015–2024 (allowing a bit more in high-inflation years if TIPS coupon is omitted).  
- Correct creation of all **CY** and **FY** spreadsheets & charts in the specified directory structure.  
- Reproducible runs from a single `macro.yaml` and IEOD CSV.  
- Tests pass locally/CI.

---

## 10) Pseudocode Snapshot

```python
# === Monthly loop ===
Debt[t] = Debt[t-1] + PrimaryDef[t] + NetInt[t]

r_short[t] = ema(r3m[t], alpha_short)
r_nb[t]    = ema(wavg([r2y[t], r5y[t], r10y[t]], w), alpha_nb)
tips_m[t]  = cpi_infl_m[t]

Int_SHORT = r_short[t] * Debt[t-1] * share_SHORT / 12
Int_NB    = r_nb[t]    * Debt[t-1] * share_NB    / 12
Int_TIPS  = (tips_m[t] + r_tips_coupon) * Debt[t-1] * share_TIPS / 12  # default r_tips_coupon=0
Int_OTHER = other_rule(params, GDP[t], Debt[t])

NetInt[t] = Int_SHORT + Int_NB + Int_TIPS + Int_OTHER
Debt[t]   = Debt[t-1] + PrimaryDef[t] + NetInt[t]
r_eff[t]  = 12 * NetInt[t] / Debt[t-1]
```
