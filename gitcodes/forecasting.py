import gzip
import json
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

def find_data_file(filename: str) -> Path:
    candidates = [BASE_DIR / filename, Path(filename), Path("..") / filename]
    for c in candidates:
        if c.exists():
            return c
    return BASE_DIR / filename

def train_and_forecast_demand(horizon_days: int = 14) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Trains a LightGBM (Tweedie) demand model and compares it against a previous-week
    moving average baseline on a held-out final window. Forecasts the next `horizon_days`
    directly: every feature is at least `horizon_days` old, so nothing is fed back recursively.
    Falls back to embedded pre-aggregated daily_demand.json.gz when raw requests.csv is excluded (e.g. Render).
    Returns:
        forecast_df: Projected daily demand per facility and blood group with confidence intervals.
        metrics: Evaluation results on chronological holdout set.
    """
    valid_bgs = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
    req_path = find_data_file('requests.csv')
    demand_fixture = FIXTURES_DIR / "daily_demand.json.gz"

    if req_path.exists():
        req_df = pd.read_csv(req_path)
        bg_col = 'blood_group' if 'blood_group' in req_df.columns else [c for c in req_df.columns if 'group' in c or 'type' in c][0]
        req_df = req_df[req_df[bg_col].isin(valid_bgs)].copy()
        req_df['requested_at'] = pd.to_datetime(req_df['requested_at'])
        req_df['date'] = pd.to_datetime(req_df['requested_at'].dt.date)
        daily_req = req_df.groupby(['date', 'facility_id', bg_col])['units_requested'].sum().reset_index().rename(columns={bg_col: 'blood_group'})
    elif demand_fixture.exists():
        with gzip.open(demand_fixture, 'rt', encoding='utf-8') as f:
            daily_req = pd.DataFrame(json.load(f))
        daily_req['date'] = pd.to_datetime(daily_req['date'])
    else:
        raise FileNotFoundError("Neither requests.csv nor daily_demand.json.gz fixture was found.")
    
    # Complete time grid
    idx = pd.date_range(daily_req['date'].min(), daily_req['date'].max())
    facilities = daily_req['facility_id'].unique()
    blood_groups = valid_bgs
    
    multi_idx = pd.MultiIndex.from_product([idx, facilities, blood_groups], names=['date', 'facility_id', 'blood_group'])
    df_grid = pd.DataFrame(index=multi_idx).reset_index()
    
    df_demand = pd.merge(
        df_grid, 
        daily_req, 
        on=['date', 'facility_id', 'blood_group'], 
        how='left'
    ).fillna({'units_requested': 0})
    
    df_demand = df_demand.sort_values(['facility_id', 'blood_group', 'date']).reset_index(drop=True)
    
    # Feature Engineering
    # Every feature uses information at least `horizon_days` old, so the same
    # features exist for every day of the forecast window (direct forecast, no recursion).
    grp = df_demand.groupby(['facility_id', 'blood_group'])['units_requested']
    H = horizon_days
    for lag in [H, H + 7, H + 14]:
        df_demand[f'demand_lag_{lag}'] = grp.shift(lag)
    for w in [7, 14, 28, 56]:
        df_demand[f'demand_roll_mean_{w}'] = grp.transform(lambda x, w=w: x.shift(H).rolling(w).mean())
    # Simple baseline: mean of the previous week (days t-14 .. t-8), as before
    df_demand['baseline_pred'] = grp.transform(lambda x: x.shift(7).rolling(7).mean())

    df_demand['day_of_week'] = df_demand['date'].dt.day_of_week
    df_demand['month'] = df_demand['date'].dt.month
    df_demand['is_weekend'] = df_demand['day_of_week'].isin([5, 6]).astype(int)
    df_demand['facility_code'] = df_demand['facility_id'].astype('category')
    df_demand['group_code'] = df_demand['blood_group'].astype('category')

    df_clean = df_demand.dropna().reset_index(drop=True)

    # Chronological split: last `horizon_days` held out, with a gap so no
    # training target overlaps the features of the test window.
    max_date = df_clean['date'].max()
    split_date = max_date - pd.Timedelta(days=horizon_days)

    features = [f'demand_lag_{H}', f'demand_lag_{H + 7}', f'demand_lag_{H + 14}',
                'demand_roll_mean_7', 'demand_roll_mean_14', 'demand_roll_mean_28', 'demand_roll_mean_56',
                'day_of_week', 'month', 'is_weekend', 'facility_code', 'group_code']
    target = 'units_requested'

    train_df = df_clean[df_clean['date'] < split_date - pd.Timedelta(days=H)]
    val_df = df_clean[df_clean['date'] >= split_date].copy()

    def make_model():
        # Tweedie objective suits sparse, zero-heavy count demand (most facility/group/days are 0)
        return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=31,
                                 min_child_samples=50, objective='tweedie', subsample=0.8,
                                 subsample_freq=1, colsample_bytree=0.8, random_state=42, verbose=-1)

    model = make_model()
    model.fit(train_df[features], train_df[target])
    val_df['lgb_pred'] = model.predict(val_df[features]).clip(0)

    # Metrics
    baseline_mae = mean_absolute_error(val_df[target], val_df['baseline_pred'])
    lgb_mae = mean_absolute_error(val_df[target], val_df['lgb_pred'])

    def wape(actual, pred):
        denom = np.sum(actual)
        return float(np.sum(np.abs(actual - pred)) / denom) if denom > 0 else 0.0

    baseline_wape = wape(val_df[target].values, val_df['baseline_pred'].values)
    lgb_wape = wape(val_df[target].values, val_df['lgb_pred'].values)

    # Weekly view (facility x blood group x week): the level managers plan at
    val_df['week'] = (val_df['date'] - split_date).dt.days // 7
    wk = val_df.groupby(['facility_id', 'blood_group', 'week'])[[target, 'baseline_pred', 'lgb_pred']].sum()
    weekly_baseline_mae = mean_absolute_error(wk[target], wk['baseline_pred'])
    weekly_lgb_mae = mean_absolute_error(wk[target], wk['lgb_pred'])
    weekly_baseline_wape = wape(wk[target].values, wk['baseline_pred'].values)
    weekly_lgb_wape = wape(wk[target].values, wk['lgb_pred'].values)

    # Standard residual error for prediction intervals
    residuals = val_df[target] - val_df['lgb_pred']
    residual_std = float(residuals.std()) if not residuals.empty else 0.5

    metrics = {
        'baseline_mae': round(float(baseline_mae), 4),
        'baseline_wape': round(float(baseline_wape), 4),
        'lgb_mae': round(float(lgb_mae), 4),
        'lgb_wape': round(float(lgb_wape), 4),
        'weekly_baseline_mae': round(float(weekly_baseline_mae), 4),
        'weekly_lgb_mae': round(float(weekly_lgb_mae), 4),
        'weekly_baseline_wape': round(float(weekly_baseline_wape), 4),
        'weekly_lgb_wape': round(float(weekly_lgb_wape), 4),
        'residual_std': round(residual_std, 4),
        'test_window': f"{split_date.date()} to {max_date.date()}",
        'trained_until': str(max_date.date())
    }

    # Refit on all available history, then forecast the next `horizon_days` directly
    model = make_model()
    model.fit(df_clean[features], df_clean[target])

    projection_dates = pd.date_range(start=max_date + pd.Timedelta(days=1), periods=horizon_days)
    future = pd.MultiIndex.from_product(
        [projection_dates, facilities, blood_groups], names=['date', 'facility_id', 'blood_group']
    ).to_frame(index=False)
    future['units_requested'] = np.nan
    full = pd.concat([df_demand[['date', 'facility_id', 'blood_group', 'units_requested']], future], ignore_index=True)
    full = full.sort_values(['facility_id', 'blood_group', 'date']).reset_index(drop=True)
    fgrp = full.groupby(['facility_id', 'blood_group'])['units_requested']
    for lag in [H, H + 7, H + 14]:
        full[f'demand_lag_{lag}'] = fgrp.shift(lag)
    for w in [7, 14, 28, 56]:
        full[f'demand_roll_mean_{w}'] = fgrp.transform(lambda x, w=w: x.shift(H).rolling(w).mean())
    full['day_of_week'] = full['date'].dt.day_of_week
    full['month'] = full['date'].dt.month
    full['is_weekend'] = full['day_of_week'].isin([5, 6]).astype(int)
    full['facility_code'] = pd.Categorical(full['facility_id'], categories=df_demand['facility_code'].cat.categories)
    full['group_code'] = pd.Categorical(full['blood_group'], categories=df_demand['group_code'].cat.categories)

    fut = full[full['date'] > max_date].copy()
    fut['pred'] = model.predict(fut[features]).clip(0)
    generated_at = datetime.now().isoformat()

    forecast_records = []
    for r in fut.itertuples():
        pred = float(r.pred)
        forecast_records.append({
            'facility_id': r.facility_id,
            'blood_group': r.blood_group,
            'forecast_date': r.date.strftime('%Y-%m-%d'),
            'horizon_day': (r.date - max_date).days,
            'predicted_units': round(pred, 2),
            'lower_estimate': max(0.0, round(pred - 1.28 * residual_std, 2)),
            'upper_estimate': round(pred + 1.28 * residual_std, 2),
            'generated_at': generated_at
        })

    forecast_df = pd.DataFrame(forecast_records)
    return forecast_df, metrics

if __name__ == "__main__":
    df, m = train_and_forecast_demand()
    print("Forecasting finished successfully.")
    print("Metrics:", m)
    print("Forecast rows:", len(df))
    print(df.head())

