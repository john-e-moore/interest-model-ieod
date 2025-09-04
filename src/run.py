"""CLI runner for end-to-end pipeline."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import argparse
import logging
import time

import pandas as pd

from . import io_utils  # type: ignore
from . import transforms  # type: ignore
from . import calibrate  # type: ignore
from . import model as model_mod  # type: ignore
from . import aggregate  # type: ignore
from . import charts  # type: ignore


def main(config_path: str = 'input/macro.yaml', input_dir: str = 'input', output_dir: str = 'output', calibrate: bool = True, use_cached_params: bool = False) -> None:
    t0 = time.time()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    logger = logging.getLogger(__name__)

    logger.info('Loading IEOD and macro config...')
    ieod_path = io_utils.find_latest_ieod_csv(input_dir)
    df_ieod = io_utils.load_ieod(ieod_path)
    cfg = io_utils.load_macro_yaml(config_path)
    macro_df = io_utils.expand_macro_series(cfg)

    logger.info('Building IEOD monthly totals...')
    ieod_series = transforms.build_ieod_monthly_total(df_ieod, cfg['model']['start'], cfg['model']['now'])

    logger.info('Calibrating parameters...' if calibrate else 'Using default parameters...')
    if calibrate:
        params = calibrate_params_wrapper(ieod_series, macro_df, cfg, output_dir)
    else:
        params = {
            'hl_SHORT': cfg.get('model', {}).get('buckets', {}).get('SHORT', {}).get('lag_half_life_months', 3.0),
            'hl_NB': cfg.get('model', {}).get('buckets', {}).get('N_BONDS', {}).get('lag_half_life_months', 24.0),
            'share_SHORT': cfg.get('model', {}).get('buckets', {}).get('SHORT', {}).get('share_initial', 0.25),
            'share_NB': cfg.get('model', {}).get('buckets', {}).get('N_BONDS', {}).get('share_initial', 0.60),
            'share_TIPS': cfg.get('model', {}).get('buckets', {}).get('TIPS', {}).get('share_initial', 0.10),
            'other_bps': cfg.get('model', {}).get('buckets', {}).get('OTHER', {}).get('pct_gdp_bps', 5.0),
        }

    logger.info('Running monthly forecast...')
    monthly = model_mod.forecast_monthly(macro_df, params, cfg)
    # pass through nominal_gdp for aggregation
    if 'nominal_gdp' in macro_df.columns:
        monthly = monthly.join(macro_df[['nominal_gdp']], how='left')

    logger.info('Aggregating to CY and FY...')
    cy = aggregate.aggregate_model_cy(monthly)
    fy = aggregate.aggregate_model_fy(monthly)

    logger.info('Writing outputs...')
    charts.ensure_output_dirs(output_dir)
    charts.write_workbooks(cy, fy, macro_df, params, output_dir)
    charts.plot_basic_charts(cy, fy, output_dir)

    logger.info('Done in %.2fs', time.time() - t0)


def calibrate_params_wrapper(ieod_series: pd.Series, macro_df: pd.DataFrame, cfg: dict[str, Any], output_dir: str) -> dict[str, Any]:
    params = calibrate.calibrate_params(ieod_series, macro_df, cfg)
    io_utils.save_parameters(params, output_dir)
    return params


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', dest='config_path', default='input/macro.yaml')
    parser.add_argument('--input', dest='input_dir', default='input')
    parser.add_argument('--output', dest='output_dir', default='output')
    parser.add_argument('--no-calibrate', dest='calibrate', action='store_false')
    args = parser.parse_args()
    main(config_path=args.config_path, input_dir=args.input_dir, output_dir=args.output_dir, calibrate=args.calibrate)


