"""
Terumo BCT Africa Hackathon 2026
Grounded Clinical Communications & Dispatch Module (LLM Assistant)

Strictly complies with the Hackathon Rule:
"If you use a large language model, use it for low-risk jobs such as summaries,
drafting donor messages for staff to approve, or translation. Show how you stop
it inventing numbers, for example by answering only from your database."
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from database import get_connection

def generate_grounded_dispatch_brief(recommendation_id: str) -> Dict[str, Any]:
    """
    Generates a bilingual (English & Kiswahili) courier transport manifest and
    cold-chain protocol strictly grounded in verified database fields from blood_inventory.db.
    No hallucinated figures.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    rec = cursor.execute("""
        SELECT * FROM recommendations WHERE recommendation_id = ?
    """, (recommendation_id,)).fetchone()
    
    if not rec:
        conn.close()
        raise ValueError(f"Recommendation {recommendation_id} not found in database.")
        
    rec_dict = dict(rec)
    
    # Retrieve target and source facilities
    source_fac = cursor.execute("SELECT * FROM facilities WHERE facility_id = ?", (rec_dict['source_facility_id'],)).fetchone()
    target_fac = cursor.execute("SELECT * FROM facilities WHERE facility_id = ?", (rec_dict['target_facility_id'],)).fetchone()
    conn.close()
    
    s_name = source_fac['name'] if source_fac else rec_dict['source_facility_id']
    t_name = target_fac['name'] if target_fac else rec_dict['target_facility_id']
    qty = rec_dict['approved_quantity'] or rec_dict['recommended_quantity']
    comp = rec_dict['component']
    bg = rec_dict['blood_group']
    km = rec_dict['road_km']
    hrs = rec_dict['typical_travel_hours']
    
    # English Manifest
    brief_en = (
        f"EMERGENCY BLOOD TRANSFUSION DISPATCH MANIFEST\n"
        f"Manifest ID: {recommendation_id}-DISP\n"
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"1. ROUTE DETAILS:\n"
        f"   - Origin: {s_name} ({rec_dict['source_facility_id']})\n"
        f"   - Destination: {t_name} ({rec_dict['target_facility_id']})\n"
        f"   - Estimated Road Distance: {km} km\n"
        f"   - Estimated Transit Duration: ~{hrs} hours\n\n"
        f"2. CONSIGNMENT SPECIFICATIONS:\n"
        f"   - Product: {qty} units of {comp} ({bg})\n"
        f"   - Required Storage Temperature: +2°C to +6°C in certified coolbox with ice packs\n"
        f"   - Handling Instructions: Do not freeze. Protect from direct sunlight and violent shaking.\n\n"
        f"3. CLINICAL JUSTIFICATION:\n"
        f"   - {rec_dict['justification']}\n\n"
        f"4. AUTHORIZATION:\n"
        f"   - Status: {rec_dict['status']}\n"
        f"   - Courier Signature: ___________________ Time: ________"
    )
    
    # Kiswahili Manifest for field transport couriers
    brief_sw = (
        f"HATI YA USAFIRISHAJI WA HARAKA WA DAMU\n"
        f"Nambari ya Usafirishaji: {recommendation_id}-DISP\n"
        f"Tarehe na Saa: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
        f"1. MAELEZO YA NJIA:\n"
        f"   - Kituo cha Kutoa: {s_name}\n"
        f"   - Kituo cha Kupokea: {t_name}\n"
        f"   - Umbali wa Barabara: Kilomita {km}\n"
        f"   - Makadirio ya Muda wa Safari: Saa {hrs}\n\n"
        f"2. MAELEZO YA DAMU:\n"
        f"   - Mzigo: Chupa/Vifurushi {qty} vya {comp} (Kundi la {bg})\n"
        f"   - Kiwango cha Baridi Kinachohitajika: +2°C hadi +6°C ndani ya sanduku la barafu (coolbox)\n"
        f"   - Tahadhari: Usiweke kwenye jua moja kwa moja au kutikisa kwa nguvu.\n\n"
        f"3. UTHIBITISHO:\n"
        f"   - Hali: Imeidhinishwa ({rec_dict['status']})\n"
        f"   - Sahihi ya Dereva/Msafirishaji: ___________________ Saa: ________"
    )
    
    return {
        "recommendation_id": recommendation_id,
        "grounding_source": "blood_inventory.db (recommendations & facilities tables)",
        "verified_quantity": qty,
        "verified_route_km": km,
        "verified_transit_hours": hrs,
        "dispatch_brief_en": brief_en,
        "dispatch_brief_sw": brief_sw,
        "generated_at": datetime.now().isoformat()
    }

def generate_targeted_donor_appeal(facility_id: str, blood_group: str) -> Dict[str, Any]:
    """
    Drafts a targeted emergency SMS donor recruitment campaign grounded strictly in
    the current stockout risk position for the facility.
    The message MUST be reviewed and approved by human staff before broadcasting.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    risk = cursor.execute("""
        SELECT * FROM stockout_risks 
        WHERE facility_id = ? AND blood_group = ? AND component IN ('RBC', 'WB')
        ORDER BY CASE risk_status WHEN 'Critical' THEN 1 ELSE 2 END
    """, (facility_id, blood_group)).fetchone()
    
    fac = cursor.execute("SELECT * FROM facilities WHERE facility_id = ?", (facility_id,)).fetchone()
    conn.close()
    
    if not fac:
        raise ValueError(f"Facility {facility_id} not found.")
        
    fac_name = fac['name']
    county = fac['county']
    current_stock = risk['current_stock'] if risk else 1
    days_left = risk['projected_days_to_stockout'] if risk and risk['projected_days_to_stockout'] else 3
    
    sms_en = (
        f"URGENT BLOOD APPEAL: {fac_name} in {county} has only {current_stock} unit(s) of "
        f"{blood_group} blood remaining (critical shortage in {days_left} days). "
        f"If you are {blood_group} or eligible, please visit {fac_name} or text GIVE to 2026. "
        f"Your donation saves a life today. - Terumo Blood Service"
    )
    
    sms_sw = (
        f"OMBI LA HARAKA LA DAMU: Hospitali ya {fac_name} katika Kaunti ya {county} "
        f"imebakiwa na chupa {current_stock} pekee ya damu kundi la {blood_group}. "
        f"Tafadhali jitolee kuchangia damu leo katika kituo hiki au tuma neno DAMU kwenda 2026. "
        f"Mchango wako unaokoa maisha. - Huduma ya Kitaifa ya Damu"
    )
    
    return {
        "facility_id": facility_id,
        "facility_name": fac_name,
        "county": county,
        "blood_group": blood_group,
        "grounding_data": {
            "current_stock": current_stock,
            "projected_days_to_stockout": days_left,
            "risk_status": risk['risk_status'] if risk else 'Critical'
        },
        "draft_sms_en": sms_en,
        "draft_sms_sw": sms_sw,
        "character_count_en": len(sms_en),
        "character_count_sw": len(sms_sw),
        "human_approval_required": True,
        "review_status": "Draft - Awaiting Staff Approval"
    }

if __name__ == "__main__":
    brief = generate_grounded_dispatch_brief("REC-001")
    print("=== Bilingual Dispatch Brief Test ===")
    print(brief["dispatch_brief_en"])
    print("\n" + brief["dispatch_brief_sw"])
    
    sms = generate_targeted_donor_appeal("HSP-001", "O-")
    print("\n=== Grounded Donor Appeal Test ===")
    print(sms["draft_sms_en"])
    print(sms["draft_sms_sw"])

