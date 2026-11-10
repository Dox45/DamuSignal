from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Tuple
import pandas as pd
from database import get_connection

def evaluate_system_health(sync_timestamp_str: str = None, is_ml_online: bool = True) -> Dict[str, Any]:
    """
    Evaluates African Operating Safeguards:
    - Verifies telemetry freshness against a 24-hour staleness threshold.
    - Returns operational health status, warning flags, and whether fallback heuristics should engage.
    """
    now = datetime.now()
    
    if sync_timestamp_str is None:
        sync_time = now
    else:
        sync_time = pd.to_datetime(sync_timestamp_str)
        
    age_hours = (now - sync_time).total_seconds() / 3600.0
    stale_threshold_hours = 24.0
    is_stale = age_hours > stale_threshold_hours
    
    status = {
        'current_system_time': now.isoformat(),
        'last_sync_timestamp': sync_time.isoformat(),
        'data_age_hours': round(age_hours, 1),
        'is_stale': bool(is_stale),
        'is_ml_online': bool(is_ml_online),
        'operational_mode': 'Fallback Heuristic' if (is_stale or not is_ml_online) else 'Full Predictive AI',
        'health_warning': "Local data is STALE (>24 hrs). Relying on verified offline cache." if is_stale else None
    }
    
    # Persist status into SQLite
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO system_status (id, last_sync_timestamp, is_stale, is_ml_online, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_sync_timestamp = excluded.last_sync_timestamp,
                is_stale = excluded.is_stale,
                is_ml_online = excluded.is_ml_online,
                updated_at = excluded.updated_at
        """, (
            status['last_sync_timestamp'],
            1 if status['is_stale'] else 0,
            1 if status['is_ml_online'] else 0,
            now.isoformat()
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        status['db_error'] = str(e)
        
    return status

def run_offline_heuristic_fallback(inventory_df: pd.DataFrame) -> pd.DataFrame:
    """
    Deterministic safety-stock heuristic when cloud ML services are unavailable.
    Flags units based on verified local physical inventory thresholds.
    """
    records = []
    for row in inventory_df.itertuples():
        qty = row.current_units
        if qty == 0:
            risk = "Critical"
        elif qty <= 3:
            risk = "High Risk"
        elif qty <= 8:
            risk = "Moderate Risk"
        else:
            risk = "Stable"
            
        records.append({
            'facility_id': row.facility_id,
            'component': row.component,
            'blood_group': row.blood_group,
            'current_stock': qty,
            'projected_days_to_stockout': 1 if qty <= 2 else (3 if qty <= 5 else None),
            'earliest_stockout_date': "Estimated within 24-72 hrs",
            'risk_status': risk,
            'contributing_factors': f"Offline Heuristic: Current physical count is {qty} units (Threshold < 4).",
            'simulated_at': datetime.now().isoformat()
        })
    return pd.DataFrame(records)

