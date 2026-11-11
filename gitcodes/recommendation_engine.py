import gzip
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from database import get_connection

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

def find_data_file(filename: str) -> Path:
    candidates = [BASE_DIR / filename, Path(filename), Path("..") / filename]
    for c in candidates:
        if c.exists():
            return c
    return BASE_DIR / filename

def generate_recommendations(risk_summary_df: pd.DataFrame, max_recommendations: int = 30) -> pd.DataFrame:
    """
    Generates intelligent inter-facility blood transfer recommendations.
    Uses routes.csv (or embedded routes.json.gz) to find the closest surplus facility by road travel time.
    Maintains a safety reserve at source facilities and formats actionable recommendations
    with justification for human-in-the-loop approval.
    """
    fac_path = find_data_file('facilities.csv')
    if fac_path.exists():
        fac_df = pd.read_csv(fac_path)
        facility_names = dict(zip(fac_df['facility_id'], fac_df['name']))
    else:
        conn = get_connection()
        rows = conn.cursor().execute("SELECT facility_id, name FROM facilities").fetchall()
        conn.close()
        facility_names = {r['facility_id']: r['name'] for r in rows}

    routes_path = find_data_file('routes.csv')
    routes_fixture = FIXTURES_DIR / "routes.json.gz"
    if routes_path.exists():
        routes_df = pd.read_csv(routes_path)
    elif routes_fixture.exists():
        with gzip.open(routes_fixture, 'rt', encoding='utf-8') as f:
            routes_df = pd.DataFrame(json.load(f))
    else:
        routes_df = pd.DataFrame(columns=['from_facility_id', 'to_facility_id', 'road_km', 'typical_travel_hours'])
    # Fast route lookup: (from_id, to_id) -> (road_km, typical_travel_hours)
    route_map = {}
    for r in routes_df.itertuples():
        route_map[(r.from_facility_id, r.to_facility_id)] = (r.road_km, r.typical_travel_hours)
        
    # Shortages: Critical or High Risk
    shortages = risk_summary_df[risk_summary_df['risk_status'].isin(['Critical', 'High Risk'])].copy()
    # Sort shortages by urgency (Critical first, then lowest stock)
    shortages['urgency_rank'] = shortages['risk_status'].map({'Critical': 1, 'High Risk': 2})
    shortages = shortages.sort_values(['urgency_rank', 'current_stock', 'projected_days_to_stockout'])
    
    # Surpluses: Stable inventory with healthy reserve (> 15 units)
    surpluses = risk_summary_df[
        (risk_summary_df['risk_status'] == 'Stable') & 
        (risk_summary_df['current_stock'] > 15)
    ].copy()
    
    # Track reserved units during recommendation pass to avoid over-promising
    available_surplus = {}
    for s in surpluses.itertuples():
        available_surplus[(s.facility_id, s.blood_group, s.component)] = s.current_stock
        
    recommendations = []
    rec_counter = 1
    
    for short in shortages.itertuples():
        t_fid = short.facility_id
        t_name = facility_names.get(t_fid, t_fid)
        bg = short.blood_group
        comp = short.component
        needed_qty = max(2, min(10, 8 - short.current_stock))
        
        # Candidate donor facilities with matching blood group and component
        candidates = []
        for (s_fid, s_bg, s_comp), s_avail in available_surplus.items():
            if s_fid != t_fid and s_bg == bg and s_comp == comp and s_avail > 15:
                # Look up transit time
                road_info = route_map.get((s_fid, t_fid), (None, None))
                if road_info[1] is None:
                    # Try reverse route if bidirectional
                    road_info = route_map.get((t_fid, s_fid), (150.0, 4.0))
                    
                km, hours = road_info
                candidates.append({
                    'source_facility_id': s_fid,
                    'source_facility_name': facility_names.get(s_fid, s_fid),
                    'available': s_avail,
                    'road_km': km if km is not None else 100.0,
                    'travel_hours': hours if hours is not None else 3.0
                })
                
        if not candidates:
            continue
            
        # Rank by shortest travel time
        candidates.sort(key=lambda x: x['travel_hours'])
        best_donor = candidates[0]
        
        s_fid = best_donor['source_facility_id']
        s_name = best_donor['source_facility_name']
        max_transfer = int(best_donor['available'] - 15) # Leave 15 units safety buffer
        transfer_qty = min(needed_qty, max_transfer)
        
        if transfer_qty <= 0:
            continue
            
        # Deduct from available surplus pool
        available_surplus[(s_fid, bg, comp)] -= transfer_qty
        
        days_str = f"within {short.projected_days_to_stockout} days" if short.projected_days_to_stockout else "currently"
        justification = (
            f"Target facility {t_name} ({t_fid}) is at {short.risk_status} risk ({short.current_stock} units {comp} {bg}, "
            f"stock-out {days_str}). Nearest eligible source {s_name} ({s_fid}) has {best_donor['available']} units "
            f"and is {best_donor['travel_hours']:.1f} hrs transit away ({best_donor['road_km']:.0f} km)."
        )
        
        recommendations.append({
            'recommendation_id': f"REC-{rec_counter:03d}",
            'target_facility_id': t_fid,
            'target_facility_name': t_name,
            'source_facility_id': s_fid,
            'source_facility_name': s_name,
            'blood_group': bg,
            'component': comp,
            'recommended_quantity': transfer_qty,
            'approved_quantity': transfer_qty,
            'road_km': round(best_donor['road_km'], 1),
            'typical_travel_hours': round(best_donor['travel_hours'], 1),
            'justification': justification,
            'status': 'Pending Approval',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        })
        
        rec_counter += 1
        if len(recommendations) >= max_recommendations:
            break
            
    recs_df = pd.DataFrame(recommendations)
    return recs_df

if __name__ == "__main__":
    from forecasting import train_and_forecast_demand
    from inventory_engine import simulate_inventory_and_risks
    
    f_df, _ = train_and_forecast_demand()
    r_df, _ = simulate_inventory_and_risks(f_df)
    recs = generate_recommendations(r_df)
    print(f"Generated {len(recs)} recommendations.")
    print(recs.head(3))

