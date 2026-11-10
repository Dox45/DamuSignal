import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.metrics import mean_absolute_error
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent

def find_data_file(filename: str) -> Path:
    candidates = [BASE_DIR / filename, Path(filename), Path("..") / filename]
    for c in candidates:
        if c.exists():
            return c
    return BASE_DIR / filename

def train_and_forecast_demand(horizon_days: int = 14) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """
    Trains LightGBM demand forecasting model with recursive roll-forward feature generation
    and compares against a 7-day moving average baseline.
    Returns:
        forecast_df: Projected daily demand per facility and blood group with confidence intervals.
        metrics: Evaluation results on chronological holdout set.
    """
    req_df = pd.read_csv(find_data_file('requests.csv'))
    bg_col = 'blood_group' if 'blood_group' in req_df.columns else [c for c in req_df.columns if 'group' in c or 'type' in c][0]
    
    # Exclude invalid/unknown blood groups for model training
    valid_bgs = ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']
    req_df = req_df[req_df[bg_col].isin(valid_bgs)].copy()
    
    req_df['requested_at'] = pd.to_datetime(req_df['requested_at'])
    req_df['date'] = pd.to_datetime(req_df['requested_at'].dt.date)
    
    daily_req = req_df.groupby(['date', 'facility_id', bg_col])['units_requested'].sum().reset_index()
    
    # Complete time grid
    idx = pd.date_range(daily_req['date'].min(), daily_req['date'].max())
    facilities = daily_req['facility_id'].unique()
    blood_groups = valid_bgs
    
    multi_idx = pd.MultiIndex.from_product([idx, facilities, blood_groups], names=['date', 'facility_id', 'blood_group'])
    df_grid = pd.DataFrame(index=multi_idx).reset_index()
    
    df_demand = pd.merge(
        df_grid, 
        daily_req.rename(columns={bg_col: 'blood_group'}), 
        on=['date', 'facility_id', 'blood_group'], 
        how='left'
    ).fillna({'units_requested': 0})
    
    df_demand = df_demand.sort_values(['facility_id', 'blood_group', 'date']).reset_index(drop=True)
    
    # Feature Engineering
    for lag in [7, 14, 21]:
        df_demand[f'demand_lag_{lag}'] = df_demand.groupby(['facility_id', 'blood_group'])['units_requested'].shift(lag)
        
    df_demand['demand_roll_mean_7'] = df_demand.groupby(['facility_id', 'blood_group'])['units_requested'].transform(
        lambda x: x.shift(7).rolling(7).mean()
    )
    
    df_demand['day_of_week'] = df_demand['date'].dt.day_of_week
    df_demand['month'] = df_demand['date'].dt.month
    df_demand['is_weekend'] = df_demand['day_of_week'].isin([5, 6]).astype(int)
    
    df_clean = df_demand.dropna().reset_index(drop=True)
    
    # Chronological Split
    max_date = df_clean['date'].max()
    split_date = max_date - pd.Timedelta(days=horizon_days)
    
    features = ['demand_lag_7', 'demand_lag_14', 'demand_lag_21', 'demand_roll_mean_7', 'day_of_week', 'month', 'is_weekend']
    target = 'units_requested'
    
    train_df = df_clean[df_clean['date'] < split_date]
    val_df = df_clean[df_clean['date'] >= split_date].copy()
    
    val_df['baseline_pred'] = val_df['demand_roll_mean_7']
    
    model = lgb.LGBMRegressor(n_estimators=100, random_state=42, verbose=-1)
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
    
    # Standard residual error for prediction intervals
    residuals = val_df[target] - val_df['lgb_pred']
    residual_std = float(residuals.std()) if not residuals.empty else 0.5
    
    metrics = {
        'baseline_mae': round(float(baseline_mae), 4),
        'baseline_wape': round(float(baseline_wape), 4),
        'lgb_mae': round(float(lgb_mae), 4),
        'lgb_wape': round(float(lgb_wape), 4),
        'residual_std': round(residual_std, 4),
        'trained_until': str(max_date.date())
    }
    
    # Recursive Forward Projection for the next 14 days
    projection_dates = pd.date_range(start=max_date + pd.Timedelta(days=1), periods=horizon_days)
    
    # Build dictionary of historical series per facility and blood group
    history_dict = {}
    for (f, bg), g in df_demand.groupby(['facility_id', 'blood_group']):
        history_dict[(f, bg)] = list(g.sort_values('date')['units_requested'].values)
        
    forecast_records = []
    
    for step_idx, p_date in enumerate(projection_dates):
        dow = p_date.day_of_week
        month = p_date.month
        is_wknd = 1 if dow in [5, 6] else 0
        
        step_features = []
        keys = []
        for f in facilities:
            for bg in blood_groups:
                hist = history_dict.get((f, bg), [0.0] * 30)
                lag_7 = hist[-7] if len(hist) >= 7 else 0.0
                lag_14 = hist[-14] if len(hist) >= 14 else 0.0
                lag_21 = hist[-21] if len(hist) >= 21 else 0.0
                roll_mean_7 = float(np.mean(hist[-14:-7])) if len(hist) >= 14 else float(np.mean(hist[-7:]))
                
                step_features.append([lag_7, lag_14, lag_21, roll_mean_7, dow, month, is_wknd])
                keys.append((f, bg))
                
        preds = model.predict(pd.DataFrame(step_features, columns=features)).clip(0)
        
        for (f, bg), pred in zip(keys, preds):
            pred_val = round(float(pred), 2)
            lower_val = max(0.0, round(float(pred - 1.28 * residual_std), 2))
            upper_val = round(float(pred + 1.28 * residual_std), 2)
            
            # Roll forward into history for subsequent lags
            history_dict[(f, bg)].append(pred_val)
            
            forecast_records.append({
                'facility_id': f,
                'blood_group': bg,
                'forecast_date': p_date.strftime('%Y-%m-%d'),
                'horizon_day': step_idx + 1,
                'predicted_units': pred_val,
                'lower_estimate': lower_val,
                'upper_estimate': upper_val,
                'generated_at': datetime.now().isoformat()
            })
            
    forecast_df = pd.DataFrame(forecast_records)
    return forecast_df, metrics

if __name__ == "__main__":
    df, m = train_and_forecast_demand()
    print("Forecasting finished successfully.")
    print("Metrics:", m)
    print("Forecast rows:", len(df))
    print(df.head())

