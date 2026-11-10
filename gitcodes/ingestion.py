import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

from database import init_db, get_connection, log_audit
from forecasting import train_and_forecast_demand, find_data_file
from inventory_engine import simulate_inventory_and_risks
from recommendation_engine import generate_recommendations
from offline_guard import evaluate_system_health, run_offline_heuristic_fallback

def seed_facilities_table():
    """Populates the facilities table from facilities.csv."""
    fac_path = find_data_file('facilities.csv')
    fac_df = pd.read_csv(fac_path)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    for r in fac_df.itertuples():
        cursor.execute("""
            INSERT INTO facilities (
                facility_id, name, facility_type, county, lat, lon, keph_level,
                beds, grid_reliability, connectivity, supply_centre_id,
                makes_platelets, separates_components, has_blood_fridge_backup_power
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(facility_id) DO UPDATE SET
                name = excluded.name,
                county = excluded.county,
                grid_reliability = excluded.grid_reliability,
                connectivity = excluded.connectivity
        """, (
            r.facility_id, r.name, r.facility_type, r.county,
            r.lat, r.lon, str(r.keph_level) if pd.notna(r.keph_level) else None,
            int(r.beds) if pd.notna(r.beds) else 0,
            float(r.grid_reliability) if pd.notna(r.grid_reliability) else 0.8,
            str(r.connectivity),
            str(r.supply_centre_id) if pd.notna(r.supply_centre_id) else None,
            1 if r.makes_platelets is True or r.makes_platelets == 'True' else 0,
            1 if r.separates_components is True or r.separates_components == 'True' else 0,
            1 if r.has_blood_fridge_backup_power is True or r.has_blood_fridge_backup_power == 'True' else 0
        ))
        
    conn.commit()
    conn.close()
    print(f"✅ Seeded {len(fac_df)} facilities into SQLite database.")

def run_pipeline():
    print("=" * 70)
    print("🩸 Blood Inventory Intelligence & Early Warning Pipeline")
    print("=" * 70)
    
    # Step 1: Database Initialization & Facility Seeding
    print("\n[Stage 1/5] Initializing Database & Ingesting Facility Registry...")
    init_db()
    seed_facilities_table()
    
    # Step 2: Demand Forecasting Engine
    print("\n[Stage 2/5] Training Demand Forecasting Engine (LightGBM + Moving Average Baseline)...")
    forecast_df, metrics = train_and_forecast_demand(horizon_days=14)
    print(f"  • Trained up to: {metrics['trained_until']}")
    print(f"  • Baseline 7-day MA - MAE: {metrics['baseline_mae']:.4f}, WAPE: {metrics['baseline_wape']*100:.2f}%")
    print(f"  • LightGBM Model    - MAE: {metrics['lgb_mae']:.4f}, WAPE: {metrics['lgb_wape']*100:.2f}%")
    print(f"  • Generated {len(forecast_df)} forward projection points (14-day recursive horizon).")
    
    # Store forecasts into DB
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM demand_forecasts")
    for r in forecast_df.itertuples():
        cursor.execute("""
            INSERT INTO demand_forecasts (
                facility_id, blood_group, forecast_date, horizon_day,
                predicted_units, lower_estimate, upper_estimate, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.facility_id, r.blood_group, r.forecast_date, r.horizon_day,
            r.predicted_units, r.lower_estimate, r.upper_estimate, r.generated_at
        ))
    conn.commit()
    
    # Step 3: Forward Inventory Simulation with Dynamic Expiry Tracking
    print("\n[Stage 3/5] Simulating Inventory Stock-Out Risks (Accounting for Expiry & Components)...")
    risk_df, inv_df = simulate_inventory_and_risks(forecast_df, horizon_days=14)
    
    cursor.execute("DELETE FROM inventory_positions")
    for r in inv_df.itertuples():
        cursor.execute("""
            INSERT INTO inventory_positions (facility_id, component, blood_group, current_units, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (r.facility_id, r.component, r.blood_group, r.current_units, r.last_updated))
        
    cursor.execute("DELETE FROM stockout_risks")
    for r in risk_df.itertuples():
        cursor.execute("""
            INSERT INTO stockout_risks (
                facility_id, blood_group, component, current_stock,
                projected_days_to_stockout, earliest_stockout_date,
                risk_status, contributing_factors, simulated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.facility_id, r.blood_group, r.component, r.current_stock,
            r.projected_days_to_stockout, r.earliest_stockout_date,
            r.risk_status, r.contributing_factors, r.simulated_at
        ))
    conn.commit()
    
    crit_count = len(risk_df[risk_df['risk_status'] == 'Critical'])
    high_count = len(risk_df[risk_df['risk_status'] == 'High Risk'])
    mod_count = len(risk_df[risk_df['risk_status'] == 'Moderate Risk'])
    stable_count = len(risk_df[risk_df['risk_status'] == 'Stable'])
    print(f"  • Monitored positions: {len(risk_df)}")
    print(f"  • Critical (Stockout ≤3d or 0 stock): {crit_count}")
    print(f"  • High Risk (Stockout ≤7d):           {high_count}")
    print(f"  • Moderate Risk (Stockout ≤14d):       {mod_count}")
    print(f"  • Stable:                             {stable_count}")
    
    # Step 4: Decision Support & Route-Optimized Recommendations
    print("\n[Stage 4/5] Computing Route-Optimized Redistribution Recommendations...")
    recs_df = generate_recommendations(risk_df, max_recommendations=25)
    
    cursor.execute("DELETE FROM recommendations")
    for r in recs_df.itertuples():
        cursor.execute("""
            INSERT INTO recommendations (
                recommendation_id, target_facility_id, target_facility_name,
                source_facility_id, source_facility_name, blood_group, component,
                recommended_quantity, approved_quantity, road_km, typical_travel_hours,
                justification, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.recommendation_id, r.target_facility_id, r.target_facility_name,
            r.source_facility_id, r.source_facility_name, r.blood_group, r.component,
            r.recommended_quantity, r.approved_quantity, r.road_km, r.typical_travel_hours,
            r.justification, r.status, r.created_at, r.updated_at
        ))
    conn.commit()
    conn.close()
    print(f"  • Generated {len(recs_df)} actionable transfer recommendations.")
    if len(recs_df) > 0:
        sample = recs_df.iloc[0]
        print(f"  • Sample Recommendation [{sample['recommendation_id']}]:")
        print(f"    - Action: Transfer {sample['recommended_quantity']} units of {sample['component']} {sample['blood_group']}")
        print(f"    - From:   {sample['source_facility_name']} ({sample['source_facility_id']})")
        print(f"    - To:     {sample['target_facility_name']} ({sample['target_facility_id']})")
        print(f"    - Route:  {sample['road_km']} km (~{sample['typical_travel_hours']} hrs travel time)")
        print(f"    - Status: {sample['status']}")
        
    # Step 5: African Operating Safeguards & Health Evaluation
    print("\n[Stage 5/5] Evaluating African Operating Safeguards & Synchronization...")
    health = evaluate_system_health()
    print(f"  • Data Age:         {health['data_age_hours']:.1f} hours")
    print(f"  • Is Stale (>24h):  {health['is_stale']}")
    print(f"  • Operational Mode: {health['operational_mode']}")
    
    # Test Fallback Heuristic
    if health['is_stale'] or not health['is_ml_online']:
        fallback_df = run_offline_heuristic_fallback(inv_df)
        print(f"  • Fallback records generated: {len(fallback_df)}")
        
    print("\n" + "=" * 70)
    print("🚀 Pipeline complete! SQLite database ready for REST API & Frontend.")
    print("=" * 70)

if __name__ == "__main__":
    run_pipeline()
