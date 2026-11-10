import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent

def find_data_file(filename: str) -> Path:
    candidates = [BASE_DIR / filename, Path(filename), Path("..") / filename]
    for c in candidates:
        if c.exists():
            return c
    return BASE_DIR / filename

def simulate_inventory_and_risks(forecast_df: pd.DataFrame, horizon_days: int = 14) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Simulates inventory projection forward by combining:
    - Base inventory from daily_stock.csv at latest snapshot
    - Unit expirations dynamically tracked from units.csv
    - Forecasted demand from forecast_df
    Returns:
        risk_summary_df: Risk categorization, days to stockout, and explanatory evidence.
        inventory_positions_df: Latest verified inventory positions per facility, component, group.
    """
    stock_df = pd.read_csv(find_data_file('daily_stock.csv'))
    stock_df['date'] = pd.to_datetime(stock_df['date'])
    latest_date = stock_df['date'].max()
    
    # Filter to latest date snapshot
    latest_stock = stock_df[stock_df['date'] == latest_date].copy()
    
    inventory_positions_df = latest_stock.groupby(
        ['facility_id', 'component', 'blood_group']
    )['units_in_stock_end_of_day'].sum().reset_index().rename(
        columns={'units_in_stock_end_of_day': 'current_units'}
    )
    inventory_positions_df['last_updated'] = latest_date.strftime('%Y-%m-%d')
    
    # Expiry tracking from units.csv
    units_df = pd.read_csv(find_data_file('units.csv'))
    # Filter for usable units in stock at latest date
    active_units = units_df[
        (units_df['status'].isin(['in_stock', 'issued', 'quarantine'])) | 
        (units_df['status_date'] >= latest_date.strftime('%Y-%m-%d'))
    ].copy()
    active_units['expiry_date'] = pd.to_datetime(active_units['expiry_date'])
    
    projection_dates = pd.date_range(start=latest_date + pd.Timedelta(days=1), periods=horizon_days)
    min_proj = projection_dates.min()
    max_proj = projection_dates.max()

    # Pre-aggregate expiring units by (facility_id, component, blood_group, expiry_date_str)
    expiring_window = active_units[
        (active_units['expiry_date'] >= min_proj) &
        (active_units['expiry_date'] <= max_proj)
    ].copy()
    expiring_window['exp_date_str'] = expiring_window['expiry_date'].dt.strftime('%Y-%m-%d')
    exp_counts = expiring_window.groupby(
        ['current_facility_id', 'component', 'blood_group', 'exp_date_str']
    ).size().to_dict()

    # Map forecast demand per facility and blood group
    comp_demand_weights = {
        'RBC': 0.65,
        'WB': 0.20,
        'PLT': 0.10,
        'FFP': 0.05,
        'CRYO': 0.00
    }
    
    forecast_map = {}
    for row in forecast_df.itertuples():
        forecast_map[(row.facility_id, row.blood_group, row.forecast_date)] = row.predicted_units
        
    risk_records = []
    
    for row in inventory_positions_df.itertuples():
        fid = row.facility_id
        comp = row.component
        bg = row.blood_group
        current_stock = row.current_units
        
        weight = comp_demand_weights.get(comp, 0.2)
        stock = float(current_stock)
        days_to_stockout = None
        earliest_stockout_date = None
        total_demand_7d = 0.0
        expiring_7d = 0
        
        for i, p_date in enumerate(projection_dates):
            date_str = p_date.strftime('%Y-%m-%d')
            total_bg_demand = forecast_map.get((fid, bg, date_str), 0.0)
            comp_demand = total_bg_demand * weight
            comp_expiring = exp_counts.get((fid, comp, bg, date_str), 0)
            
            if i < 7:
                total_demand_7d += comp_demand
                expiring_7d += comp_expiring
                
            stock -= (comp_demand + comp_expiring)
            
            if stock <= 0 and days_to_stockout is None:
                days_to_stockout = i + 1
                earliest_stockout_date = date_str
                
        # Risk Classification
        if current_stock == 0:
            risk_status = "Critical"
        elif days_to_stockout is not None:
            if days_to_stockout <= 3:
                risk_status = "Critical"
            elif days_to_stockout <= 7:
                risk_status = "High Risk"
            elif days_to_stockout <= 14:
                risk_status = "Moderate Risk"
            else:
                risk_status = "Stable"
        else:
            risk_status = "Stable"
            
        # Fact-based explainability statement
        reasons = []
        if current_stock == 0:
            reasons.append(f"Immediate stock-out: 0 units currently available.")
        elif current_stock <= 2:
            reasons.append(f"Severely depleted opening stock ({current_stock} units).")
            
        if days_to_stockout:
            reasons.append(f"Projected deficit within {days_to_stockout} days (by {earliest_stockout_date}).")
            
        if total_demand_7d > current_stock:
            reasons.append(f"Expected 7-day demand ({total_demand_7d:.1f} units) outpaces stock.")
            
        if expiring_7d > 0:
            reasons.append(f"{expiring_7d} unit(s) expiring within 7 days.")
            
        if not reasons:
            reasons.append(f"Inventory position is stable with {current_stock} units in reserve.")
            
        risk_records.append({
            'facility_id': fid,
            'blood_group': bg,
            'component': comp,
            'current_stock': int(current_stock),
            'projected_days_to_stockout': days_to_stockout,
            'earliest_stockout_date': earliest_stockout_date,
            'risk_status': risk_status,
            'contributing_factors': " ".join(reasons),
            'simulated_at': datetime.now().isoformat()
        })
        
    risk_summary_df = pd.DataFrame(risk_records)
    return risk_summary_df, inventory_positions_df

if __name__ == "__main__":
    from forecasting import train_and_forecast_demand
    f_df, _ = train_and_forecast_demand()
    r_df, inv_df = simulate_inventory_and_risks(f_df)
    print("Simulation finished.")
    print("Risks shape:", r_df.shape)
    print(r_df[r_df['risk_status'] == 'Critical'].head())
