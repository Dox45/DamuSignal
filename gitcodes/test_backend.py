import sys
from pathlib import Path

# Add gitcodes to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from api import app
from database import get_connection

client = TestClient(app)

def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"
    print("✅ test_health passed")

def test_facilities_endpoint():
    res = client.get("/api/facilities")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 47
    assert len(data["facilities"]) == 47
    
    # Test filter by county
    res_nairobi = client.get("/api/facilities?county=Nairobi")
    assert res_nairobi.status_code == 200
    assert res_nairobi.json()["count"] >= 1
    print("✅ test_facilities_endpoint passed")

def test_inventory_endpoint():
    res = client.get("/api/inventory")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    
    # Test facility specific inventory
    res_fac = client.get("/api/inventory/HSP-001")
    assert res_fac.status_code == 200
    fac_data = res_fac.json()
    assert "facility" in fac_data
    assert fac_data["facility"]["facility_id"] == "HSP-001"
    assert "inventory" in fac_data
    assert "total_units" in fac_data
    print("✅ test_inventory_endpoint passed")

def test_forecasts_endpoint():
    res = client.get("/api/forecasts")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    sample = data["forecasts"][0]
    assert "predicted_units" in sample
    assert "lower_estimate" in sample
    assert "upper_estimate" in sample
    print("✅ test_forecasts_endpoint passed")

def test_stockout_risks_endpoint():
    res = client.get("/api/stockout-risks")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] > 0
    
    # Test filter by risk_status
    res_crit = client.get("/api/stockout-risks?risk_status=Critical")
    assert res_crit.status_code == 200
    crit_data = res_crit.json()
    for item in crit_data["risks"]:
        assert item["risk_status"] == "Critical"
        assert item["contributing_factors"] is not None
    print("✅ test_stockout_risks_endpoint passed")

def test_recommendation_workflow_and_audit():
    # 1. Fetch recommendations
    res = client.get("/api/recommendations")
    assert res.status_code == 200
    recs = res.json()["recommendations"]
    assert len(recs) >= 3
    
    rec_1 = recs[0]["recommendation_id"]
    rec_2 = recs[1]["recommendation_id"]
    rec_3 = recs[2]["recommendation_id"]
    
    # 2. Test Approve (Accept)
    res_app = client.post(f"/api/recommendations/{rec_1}/approve", json={
        "user_id": "dr_odhiambo",
        "notes": "Approved for emergency resupply via road transport."
    })
    assert res_app.status_code == 200
    assert res_app.json()["action"] == "Approved"
    
    # Verify DB update
    res_verify = client.get(f"/api/recommendations?status=Approved")
    approved_ids = [r["recommendation_id"] for r in res_verify.json()["recommendations"]]
    assert rec_1 in approved_ids
    
    # 3. Test Modify
    res_mod = client.post(f"/api/recommendations/{rec_2}/modify", json={
        "user_id": "nurse_kamau",
        "modified_quantity": 6,
        "notes": "Reduced to 6 units due to cooler box capacity constraint."
    })
    assert res_mod.status_code == 200
    assert res_mod.json()["action"] == "Modified"
    assert res_mod.json()["approved_quantity"] == 6
    
    # 4. Test Reject
    res_rej = client.post(f"/api/recommendations/{rec_3}/reject", json={
        "user_id": "director_mwangi",
        "reason": "Local elective surgery rescheduled; current supply sufficient."
    })
    assert res_rej.status_code == 200
    assert res_rej.json()["action"] == "Rejected"
    
    # 5. Verify Audit Logs
    res_audit = client.get("/api/audit-logs")
    assert res_audit.status_code == 200
    logs = res_audit.json()["audit_logs"]
    assert len(logs) >= 3
    
    actions = [l["action"] for l in logs[:3]]
    assert "approve" in actions
    assert "modify" in actions
    assert "reject" in actions
    print("✅ test_recommendation_workflow_and_audit passed")

def test_system_status():
    res = client.get("/api/system-status")
    assert res.status_code == 200
    data = res.json()
    assert "current_system_time" in data
    assert "data_age_hours" in data
    assert "operational_mode" in data
    print("✅ test_system_status passed")

def test_simulation_trigger():
    res = client.post("/api/stockout-risks/simulate")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["total_evaluated"] > 0
    print("✅ test_simulation_trigger passed")

if __name__ == "__main__":
    print("\n--- Running Backend REST API & Database Test Suite ---")
    test_health()
    test_facilities_endpoint()
    test_inventory_endpoint()
    test_forecasts_endpoint()
    test_stockout_risks_endpoint()
    test_recommendation_workflow_and_audit()
    test_system_status()
    test_simulation_trigger()
    print("\n🎉 ALL 8 BACKEND AND API INTEGRATION TESTS PASSED!\n")

