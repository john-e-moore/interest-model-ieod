"""CLI runner for end-to-end pipeline."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import argparse
import logging
import time

import pandas as pd

try:
    from . import io_utils  # type: ignore
    from . import transforms  # type: ignore
    from . import calibrate  # type: ignore
    from . import model as model_mod  # type: ignore
    from . import aggregate  # type: ignore
    from . import charts  # type: ignore
except ImportError: # pytest.ini compatibility
    import io_utils  # type: ignore
    import transforms  # type: ignore
    import calibrate  # type: ignore
    import model as model_mod  # type: ignore
    import aggregate  # type: ignore
    import charts  # type: ignore

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

    # Create timestamped run directory once for this run
    ts = pd.Timestamp.utcnow().strftime('%Y%m%dT%H%M%SZ')
    run_dir = Path(output_dir) / ts

    logger.info('Calibrating parameters...' if calibrate else 'Using default parameters...')
    if calibrate:
        params = calibrate_params_wrapper(ieod_series, macro_df, cfg, str(run_dir))
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

    logger.info('Writing outputs to %s...', run_dir)
    charts.ensure_output_dirs(run_dir)
    charts.write_workbooks(cy, fy, macro_df, params, run_dir)
    charts.plot_basic_charts(cy, fy, run_dir)

    # Copy inputs into run_dir/inputs
    inputs_dir = run_dir / 'inputs'
    inputs_dir.mkdir(parents=True, exist_ok=True)
    import shutil as _shutil
    # Copy macro.yaml
    try:
        _shutil.copy2(str(Path(config_path)), str(inputs_dir / Path(config_path).name))
    except Exception:
        pass
    # Copy IEOD CSV
    try:
        _shutil.copy2(str(ieod_path), str(inputs_dir / ieod_path.name))
    except Exception:
        pass
    # Copy FYOINT.xlsx if present
    fyoint_path = Path(input_dir) / 'FYOINT.xlsx'
    if fyoint_path.exists():
        try:
            _shutil.copy2(str(fyoint_path), str(inputs_dir / 'FYOINT.xlsx'))
        except Exception:
            pass

    logger.info('Done in %.2fs', time.time() - t0)


def calibrate_params_wrapper(ieod_series: pd.Series, macro_df: pd.DataFrame, cfg: dict[str, Any], output_dir: str) -> dict[str, Any]:
    params = calibrate.calibrate_params(ieod_series, macro_df, cfg)
    # Save parameters in the provided output directory (run_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
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


