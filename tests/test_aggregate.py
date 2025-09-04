import importlib
import pandas as pd
import numpy as np


def test_import_aggregate_module():
    assert importlib.import_module('aggregate') is not None


def test_aggregate_model_outputs_to_cy_fy():
    aggregate = importlib.import_module('aggregate')
    # Build monthly outputs
    idx = pd.date_range('2019-10-31', periods=6, freq='M')  # Oct 2019 .. Mar 2020
    df = pd.DataFrame({
        'Int_SHORT': [10, 10, 10, 10, 10, 10],
        'Int_NB': [5, 5, 5, 5, 5, 5],
        'Int_TIPS': [1, 1, 1, 1, 1, 1],
        'Int_OTHER': [2, 2, 2, 2, 2, 2],
        'NetInt': [18]*6,
        'Debt': [100, 110, 120, 130, 140, 150],
        'r_eff': [0.02]*6,
        'nominal_gdp': [1000, 1000, 1000, 1000, 1000, 1000],
    }, index=idx)

    cy = aggregate.aggregate_model_cy(df)
    # CY 2019 has Oct-Dec 2019 (3 months): interest totals = 3*18
    assert cy.loc[2019, 'interest_total'] == 54
    # Average debt for CY2019 is simple mean for those months
    assert cy.loc[2019, 'debt_avg'] == np.mean([100,110,120])
    # FY: Oct-Sep, so our 6 months span FY2020 (Oct 2019 - Mar 2020)
    fy = aggregate.aggregate_model_fy(df)
    assert fy.loc[2020, 'interest_total'] == 6*18
    assert fy.loc[2020, 'debt_avg'] == np.mean([100,110,120,130,140,150])


