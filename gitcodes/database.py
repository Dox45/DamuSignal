import sqlite3
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "blood_inventory.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create all required tables if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS facilities (
        facility_id TEXT PRIMARY KEY,
        name TEXT,
        facility_type TEXT,
        county TEXT,
        lat REAL,
        lon REAL,
        keph_level TEXT,
        beds INTEGER,
        grid_reliability REAL,
        connectivity TEXT,
        supply_centre_id TEXT,
        makes_platelets INTEGER,
        separates_components INTEGER,
        has_blood_fridge_backup_power INTEGER
    );

    CREATE TABLE IF NOT EXISTS inventory_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id TEXT,
        component TEXT,
        blood_group TEXT,
        current_units INTEGER,
        last_updated TEXT,
        UNIQUE(facility_id, component, blood_group)
    );

    CREATE TABLE IF NOT EXISTS demand_forecasts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id TEXT,
        blood_group TEXT,
        forecast_date TEXT,
        horizon_day INTEGER,
        predicted_units REAL,
        lower_estimate REAL,
        upper_estimate REAL,
        generated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS stockout_risks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        facility_id TEXT,
        blood_group TEXT,
        component TEXT,
        current_stock INTEGER,
        projected_days_to_stockout INTEGER,
        earliest_stockout_date TEXT,
        risk_status TEXT,
        contributing_factors TEXT,
        simulated_at TEXT,
        UNIQUE(facility_id, blood_group, component)
    );

    CREATE TABLE IF NOT EXISTS recommendations (
        recommendation_id TEXT PRIMARY KEY,
        target_facility_id TEXT,
        target_facility_name TEXT,
        source_facility_id TEXT,
        source_facility_name TEXT,
        blood_group TEXT,
        component TEXT,
        recommended_quantity INTEGER,
        approved_quantity INTEGER,
        road_km REAL,
        typical_travel_hours REAL,
        justification TEXT,
        status TEXT DEFAULT 'Pending Approval',
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id TEXT,
        action TEXT,
        user_id TEXT,
        previous_status TEXT,
        new_status TEXT,
        previous_quantity INTEGER,
        new_quantity INTEGER,
        timestamp TEXT,
        notes TEXT
    );

    CREATE TABLE IF NOT EXISTS system_status (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        last_sync_timestamp TEXT,
        is_stale INTEGER,
        is_ml_online INTEGER,
        updated_at TEXT
    );
    """)

    conn.commit()
    conn.close()

def log_audit(recommendation_id: str, action: str, user_id: str,
              prev_status: str, new_status: str,
              prev_qty: Optional[int], new_qty: Optional[int], notes: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_logs (
            recommendation_id, action, user_id, previous_status, new_status,
            previous_quantity, new_quantity, timestamp, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        recommendation_id, action, user_id, prev_status, new_status,
        prev_qty, new_qty, datetime.now().isoformat(), notes
    ))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")

