from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import pandas as pd
import sqlite3

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_HTML = BASE_DIR / "frontend" / "index.html"

from database import get_connection, init_db, log_audit
from forecasting import train_and_forecast_demand
from inventory_engine import simulate_inventory_and_risks
from recommendation_engine import generate_recommendations
from offline_guard import evaluate_system_health, run_offline_heuristic_fallback
from llm_assistant import generate_grounded_dispatch_brief, generate_targeted_donor_appeal

app = FastAPI(
    title="Blood Inventory Intelligence & Early Warning System",
    description="Backend decision-support API for Terumo BCT Africa Hackathon 2026",
    version="1.0.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Request Models
class ApprovalRequest(BaseModel):
    user_id: str = Field(default="manager_01", description="ID or name of authorizing personnel")
    notes: Optional[str] = Field(default="Approved as recommended", description="Optional approval notes")

class ModifyRequest(BaseModel):
    user_id: str = Field(default="manager_01", description="ID or name of authorizing personnel")
    modified_quantity: int = Field(ge=1, description="Adjusted transfer quantity")
    notes: Optional[str] = Field(default="Quantity adjusted for local capacity", description="Reason for modification")

class RejectRequest(BaseModel):
    user_id: str = Field(default="manager_01", description="ID or name of authorizing personnel")
    reason: str = Field(default="Clinical priority override", description="Required justification for rejection")


@app.on_event("startup")
def startup_event():
    """Initializes SQLite schema and automatically seeds tables if empty."""
    init_db()
    conn = get_connection()
    count = conn.cursor().execute("SELECT count(*) FROM facilities").fetchone()[0]
    conn.close()
    if count == 0 and (BASE_DIR / "facilities.csv").exists():
        from ingestion import run_pipeline
        try:
            print("[Render Deployment Initialization] Empty database detected. Seeding from datasets...")
            run_pipeline()
        except Exception as e:
            print(f"[Render Deployment Initialization] Pipeline run notice: {e}")


@app.get("/", response_class=HTMLResponse)
def root_dashboard():
    """Serves the interactive web dashboard directly at the root URL."""
    if FRONTEND_HTML.exists():
        return FileResponse(str(FRONTEND_HTML))
    return HTMLResponse("<h2>Blood Inventory Intelligence API</h2><p><a href='/docs'>Swagger API Documentation</a></p>")


# ============================ 1. Facility Endpoints ============================

@app.get("/api/facilities")
def get_facilities(county: Optional[str] = None, facility_type: Optional[str] = None):
    """Retrieve all facilities with optional county and type filters."""
    conn = get_connection()
    query = "SELECT * FROM facilities WHERE 1=1"
    params = []
    
    if county:
        query += " AND county = ?"
        params.append(county)
    if facility_type:
        query += " AND facility_type = ?"
        params.append(facility_type)
        
    cursor = conn.cursor()
    rows = [dict(r) for r in cursor.execute(query, params).fetchall()]
    conn.close()
    return {"count": len(rows), "facilities": rows}


# ============================ 2. Inventory Endpoints ============================

@app.get("/api/inventory")
def get_inventory(facility_id: Optional[str] = None, blood_group: Optional[str] = None, component: Optional[str] = None):
    """Retrieve verified inventory positions across facilities."""
    conn = get_connection()
    query = "SELECT * FROM inventory_positions WHERE 1=1"
    params = []
    
    if facility_id:
        query += " AND facility_id = ?"
        params.append(facility_id)
    if blood_group:
        query += " AND blood_group = ?"
        params.append(blood_group)
    if component:
        query += " AND component = ?"
        params.append(component)
        
    cursor = conn.cursor()
    rows = [dict(r) for r in cursor.execute(query, params).fetchall()]
    conn.close()
    return {"count": len(rows), "inventory": rows}


@app.get("/api/inventory/{facility_id}")
def get_facility_inventory(facility_id: str):
    """Retrieve detailed inventory breakdown for a specific facility."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Facility metadata
    fac = cursor.execute("SELECT * FROM facilities WHERE facility_id = ?", (facility_id,)).fetchone()
    if not fac:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Facility {facility_id} not found")
        
    items = [dict(r) for r in cursor.execute(
        "SELECT * FROM inventory_positions WHERE facility_id = ?", (facility_id,)
    ).fetchall()]
    
    # Active risks for facility
    risks = [dict(r) for r in cursor.execute(
        "SELECT * FROM stockout_risks WHERE facility_id = ?", (facility_id,)
    ).fetchall()]
    
    conn.close()
    total_units = sum(item['current_units'] for item in items)
    
    return {
        "facility": dict(fac),
        "total_units": total_units,
        "inventory": items,
        "risks": risks
    }


# ============================ 3. Forecasting Endpoints ============================

@app.get("/api/forecasts")
def get_forecasts(facility_id: Optional[str] = None, blood_group: Optional[str] = None):
    """Retrieve latest generated demand forecasts."""
    conn = get_connection()
    query = "SELECT * FROM demand_forecasts WHERE 1=1"
    params = []
    
    if facility_id:
        query += " AND facility_id = ?"
        params.append(facility_id)
    if blood_group:
        query += " AND blood_group = ?"
        params.append(blood_group)
        
    query += " ORDER BY forecast_date ASC, horizon_day ASC"
    
    cursor = conn.cursor()
    rows = [dict(r) for r in cursor.execute(query, params).fetchall()]
    conn.close()
    return {"count": len(rows), "forecasts": rows}


@app.post("/api/forecasts/run")
def trigger_demand_forecasting(horizon_days: int = 14):
    """Re-train LightGBM model and generate recursive 14-day projection."""
    forecast_df, metrics = train_and_forecast_demand(horizon_days=horizon_days)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Replace demand_forecasts table contents with latest projection
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
    conn.close()
    
    return {
        "status": "success",
        "message": f"Generated {len(forecast_df)} forecast entries across 14 days",
        "metrics": metrics
    }


# ============================ 4. Stock-Out Risk Endpoints ============================

@app.get("/api/stockout-risks")
def get_stockout_risks(risk_status: Optional[str] = None, facility_id: Optional[str] = None):
    """Retrieve stock-out early warnings with explainability evidence."""
    conn = get_connection()
    query = "SELECT * FROM stockout_risks WHERE 1=1"
    params = []
    
    if risk_status:
        query += " AND risk_status = ?"
        params.append(risk_status)
    if facility_id:
        query += " AND facility_id = ?"
        params.append(facility_id)
        
    query += " ORDER BY CASE risk_status WHEN 'Critical' THEN 1 WHEN 'High Risk' THEN 2 WHEN 'Moderate Risk' THEN 3 ELSE 4 END, current_stock ASC"
    
    cursor = conn.cursor()
    rows = [dict(r) for r in cursor.execute(query, params).fetchall()]
    conn.close()
    return {"count": len(rows), "risks": rows}


@app.post("/api/stockout-risks/simulate")
def trigger_inventory_simulation():
    """Run forward simulation of stock depletion and unit expiry against forecasts."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch latest forecasts
    forecast_rows = [dict(r) for r in cursor.execute("SELECT * FROM demand_forecasts").fetchall()]
    if not forecast_rows:
        conn.close()
        raise HTTPException(status_code=400, detail="No forecasts found. Run /api/forecasts/run first.")
        
    f_df = pd.DataFrame(forecast_rows)
    risk_df, inv_df = simulate_inventory_and_risks(f_df)
    
    # Update inventory_positions
    for r in inv_df.itertuples():
        cursor.execute("""
            INSERT INTO inventory_positions (facility_id, component, blood_group, current_units, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(facility_id, component, blood_group) DO UPDATE SET
                current_units = excluded.current_units,
                last_updated = excluded.last_updated
        """, (r.facility_id, r.component, r.blood_group, r.current_units, r.last_updated))
        
    # Update stockout_risks
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
    conn.close()
    
    critical_count = len(risk_df[risk_df['risk_status'] == 'Critical'])
    high_count = len(risk_df[risk_df['risk_status'] == 'High Risk'])
    
    return {
        "status": "success",
        "total_evaluated": len(risk_df),
        "critical_risks": critical_count,
        "high_risks": high_count
    }


# ============================ 5. Recommendation Endpoints ============================

@app.get("/api/recommendations")
def get_recommendations(status: Optional[str] = None, target_facility_id: Optional[str] = None):
    """Retrieve proposed inter-facility transfer recommendations."""
    conn = get_connection()
    query = "SELECT * FROM recommendations WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = ?"
        params.append(status)
    if target_facility_id:
        query += " AND target_facility_id = ?"
        params.append(target_facility_id)
        
    cursor = conn.cursor()
    rows = [dict(r) for r in cursor.execute(query, params).fetchall()]
    conn.close()
    return {"count": len(rows), "recommendations": rows}


@app.post("/api/recommendations/{rec_id}/approve")
def approve_recommendation(rec_id: str, payload: ApprovalRequest = Body(...)):
    """Authorize a transfer recommendation (Accept)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    rec = cursor.execute("SELECT * FROM recommendations WHERE recommendation_id = ?", (rec_id,)).fetchone()
    if not rec:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Recommendation {rec_id} not found")
        
    prev_status = rec['status']
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE recommendations 
        SET status = 'Approved', updated_at = ?
        WHERE recommendation_id = ?
    """, (now, rec_id))
    conn.commit()
    conn.close()
    
    log_audit(
        recommendation_id=rec_id,
        action="approve",
        user_id=payload.user_id,
        prev_status=prev_status,
        new_status="Approved",
        prev_qty=rec['recommended_quantity'],
        new_qty=rec['recommended_quantity'],
        notes=payload.notes
    )
    
    return {"status": "success", "recommendation_id": rec_id, "action": "Approved", "user": payload.user_id}


@app.post("/api/recommendations/{rec_id}/modify")
def modify_recommendation(rec_id: str, payload: ModifyRequest = Body(...)):
    """Modify transfer quantity and approve (Modify)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    rec = cursor.execute("SELECT * FROM recommendations WHERE recommendation_id = ?", (rec_id,)).fetchone()
    if not rec:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Recommendation {rec_id} not found")
        
    prev_status = rec['status']
    prev_qty = rec['recommended_quantity']
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE recommendations 
        SET status = 'Modified', approved_quantity = ?, updated_at = ?
        WHERE recommendation_id = ?
    """, (payload.modified_quantity, now, rec_id))
    conn.commit()
    conn.close()
    
    log_audit(
        recommendation_id=rec_id,
        action="modify",
        user_id=payload.user_id,
        prev_status=prev_status,
        new_status="Modified",
        prev_qty=prev_qty,
        new_qty=payload.modified_quantity,
        notes=payload.notes
    )
    
    return {
        "status": "success", 
        "recommendation_id": rec_id, 
        "action": "Modified", 
        "original_quantity": prev_qty,
        "approved_quantity": payload.modified_quantity,
        "user": payload.user_id
    }


@app.post("/api/recommendations/{rec_id}/reject")
def reject_recommendation(rec_id: str, payload: RejectRequest = Body(...)):
    """Decline a proposed transfer recommendation with justification (Reject)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    rec = cursor.execute("SELECT * FROM recommendations WHERE recommendation_id = ?", (rec_id,)).fetchone()
    if not rec:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Recommendation {rec_id} not found")
        
    prev_status = rec['status']
    now = datetime.now().isoformat()
    
    cursor.execute("""
        UPDATE recommendations 
        SET status = 'Rejected', updated_at = ?
        WHERE recommendation_id = ?
    """, (now, rec_id))
    conn.commit()
    conn.close()
    
    log_audit(
        recommendation_id=rec_id,
        action="reject",
        user_id=payload.user_id,
        prev_status=prev_status,
        new_status="Rejected",
        prev_qty=rec['recommended_quantity'],
        new_qty=0,
        notes=payload.reason
    )
    
    return {"status": "success", "recommendation_id": rec_id, "action": "Rejected", "reason": payload.reason}


# ============================ 6. Audit Logs & System Status ============================

@app.get("/api/audit-logs")
def get_audit_logs():
    """Retrieve decision audit trail preserving human-in-the-loop decisions."""
    conn = get_connection()
    cursor = conn.cursor()
    rows = [dict(r) for r in cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC").fetchall()]
    conn.close()
    return {"count": len(rows), "audit_logs": rows}


# ============================ 7. Grounded LLM Assistant Endpoints ============================

@app.get("/api/llm/dispatch-brief/{rec_id}")
def get_dispatch_brief(rec_id: str):
    """
    Generates a grounded bilingual (English & Swahili) Courier Transport Manifest
    and cold-chain temperature protocol strictly using verified database fields.
    """
    try:
        brief = generate_grounded_dispatch_brief(rec_id)
        return {"status": "success", "manifest": brief}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/llm/draft-donor-appeal")
def get_donor_appeal(facility_id: str = Query(...), blood_group: str = Query(...)):
    """
    Drafts a targeted emergency SMS donor recruitment campaign grounded strictly in
    the current stockout risk position for the facility. Staff must review and approve.
    """
    try:
        sms = generate_targeted_donor_appeal(facility_id, blood_group)
        return {"status": "success", "donor_appeal": sms}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/system-status")
def get_system_status():
    """Evaluate telemetry age, connectivity state, and fallback heuristic mode."""
    return evaluate_system_health()


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "service": "Blood Inventory Intelligence API"}

