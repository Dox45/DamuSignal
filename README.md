# Blood Inventory Intelligence & Early Warning System

Terumo BCT Africa Hackathon 2026 · Challenge area: Stock-outs, Emergency Access & Redistribution

## The problem
In Kenya’s national blood transfusion system, regional blood transfusion centres (RBTCs) and hospital blood bank managers—such as **Dr. Amina Odhiambo** (Regional Transfusion Officer)—struggle to anticipate acute shortages before they happen. Today, management is purely reactive: hospitals only sound the alarm when their blood bank is empty. Emergency couriers take a median of **5 hours** (much longer in remote counties). 

Meanwhile, dataset figures reveal significant system friction:
- **17,430 requests** for 34,242 units; rare groups like $O^-$, $B^-$, and $A^-$ face the highest unmet rates.
- **~23% of red cell and whole blood units** expire unused or spoil from fridge temperature excursions.
- **60% of donors are students**, creating severe collection cliffs during school holidays (Nov–Jan, Apr, Aug).

## What we built
- **What works now:**
  - Machine learning demand forecasting engine (LightGBM) with 14-day recursive lag roll-forward and confidence interval bands.
  - Forward inventory simulation tracking component shelf lives and deducting expiring units dynamically from `units.csv`.
  - Route-optimized inter-facility transfer recommendations using road distance and travel times from `routes.csv` while reserving a 15-unit safety buffer at donor facilities.
  - Full **Human-in-the-Loop decision workflow** (Accept, Modify Quantity, or Reject with clinical justification).
  - Immutable SQLite audit trail logging all human overrides with ISO-8601 timestamps.
  - Operational health check guarding against stale telemetry (>24 hrs) with an automatic fallback heuristic.
  - REST API with FastAPI exposing 11 operational endpoints.
  - Responsive Next.js 16 (TypeScript + Tailwind CSS) dashboard.
- **What is mocked or not finished:**
  - Automated SMS/USSD notification gateway to couriers (simulated via in-app audit status).
  - Direct live Bluetooth integration with cold-chain fridge loggers (currently parsed from CSV logs).

Demo video (3 minutes or less): [Demo Video Link]  
Live demo: https://damusignal.vercel.app · Test log-in: dr_odhiambo / bloodbank2026

## How to run it
Step-by-step commands (tested on Linux / Mac / Windows):

1. **Clone and enter repository**:
   ```bash
   cd /home/Ace/gitfiles/Terumo
   ```
2. **Launch both Backend and Frontend**:
   ```bash
   ./start_servers.sh
   ```
3. **Access the Application**:
   - Web Dashboard: `http://localhost:3000`
   - FastAPI Docs: `http://localhost:8000/docs`

4. *(Optional) Run Automated Backend Integration Tests*:
   ```bash
   ./.venv/bin/python gitcodes/test_backend.py
   ```

## Architecture

The diagram below shows the system's internal components, data flows, offline fallback path, and where our predictive decision-support workflow sits within the wider national blood transfusion system (preserving strict human control and clinical/laboratory boundaries).

```mermaid
flowchart TB
    subgraph Wider_Upstream ["1. Wider Blood System: Upstream Field Operations"]
        U1["Donor Drives & Collections (donors.csv, drives.csv, donations.csv)"]
        U2["47 RBTCs & Hospital Blood Banks (facilities.csv, daily_stock.csv, units.csv)"]
        U3["Hospital Transfusion Orders (requests.csv: 17,430 orders)"]
        U4["Cold-Chain & Grid Telemetry (temperature_logs.csv, power_outages.csv)"]
        U5["National Road Network (routes.csv: 2,162 links & transit hrs)"]
    end

    subgraph Core_Ingestion ["2. Data Ingestion & Persistence Layer"]
        ING["ingestion.py: Clean, Validate & Separate Components (RBC, WB, PLT, FFP, CRYO)"]
        SEED["Cloud Fallback: starter_seed.json.gz (58.1 KB)"]
        DB[("database.py -> SQLite blood_inventory.db (7 Tables)")]
    end

    subgraph Predictive_Engine ["3. AI, Simulation & Resilience Engines"]
        FORE["forecasting.py: LightGBM 14-Day Recursive Forecast vs 7-Day MA Baseline"]
        INV["inventory_engine.py: Daily Depletion + Unit Expiry Simulation"]
        REC["recommendation_engine.py: Surplus-to-Deficit Match (15-Unit Reserve & Road Hours)"]
        OFF["offline_guard.py: >24h Staleness Check & Deterministic Fallback Heuristic"]
        LLM["llm_assistant.py: Grounded Bilingual Dispatch Brief & Donor Appeal Drafts"]
    end

    subgraph API_UI ["4. Secured API & Operator Console"]
        API["api.py: FastAPI REST API + Bearer Token Auth + Immutable Audit Trail"]
        UI["Operator Dashboard: Next.js (ui/src/app/page.tsx) & HTML (frontend/index.html)"]
    end

    subgraph Wider_Downstream ["5. Wider Blood System: Human Control & Downstream Execution"]
        HITL["Human-in-the-Loop Gate: Transfusion Officer (Accept / Modify / Reject)"]
        LOG["Physical Courier Dispatch (+2C to +6C Cold Chain) & Staff-Approved Donor SMS"]
        CLINIC["Hard Clinical Boundary: Qualified Lab Cross-Match, Quarantine & Unit Release (AI Never Touches)"]
        STD["Interoperability Standards: ISBT 128 Unit IDs | HL7 FHIR SupplyRequest | DHIS2 Reports"]
    end

    U1 & U2 & U3 & U4 & U5 -->|"Telemetry & Orders"| ING
    SEED -.->|"If CSVs absent (Render)"| DB
    ING -->|"Validated State"| DB
    DB -->|"Historical Demand"| FORE
    FORE -->|"14-Day Forecast + 10%/90% Bounds"| INV
    DB -->|"Usable Stock & Expiring Units"| INV
    INV -->|"Critical/High-Risk Deficits"| REC
    DB -->|"Road Routes & Donor Surplus"| REC
    DB -->|"Sync Timestamp"| OFF
    OFF -.->|"If >24h Stale or ML Offline"| UI
    REC -->|"Pending Transfer Proposals"| API
    INV & FORE -->|"Risk Evidence & Metrics"| API
    DB <-->|"Approve / Modify / Reject Logs"| API
    API <-->|"Authenticated HTTPS / JSON"| LLM
    API <-->|"Bearer Auth REST"| UI
    UI -->|"Plain-Language Evidence"| HITL
    HITL -->|"Signed Decision Logged"| API
    HITL -->|"Authorized Movement"| LOG
    HITL -->|"Staff-Reviewed Only"| CLINIC
    DB -.->|"Standardized Schema Mapping"| STD
```

- **Data Layer**: SQLite database (`blood_inventory.db`) with tables for facilities, inventory, demand forecasts, stockout risks, recommendations, and audit logs.
- **Machine Learning Layer**: LightGBM Regressor with time-series feature engineering and 7-day moving average baseline benchmark.
- **API Services**: FastAPI backend exposing REST endpoints with Bearer token authentication and CORS support.
- **User Interface**: Next.js 16 App Router (TypeScript, Tailwind CSS, Lucide Icons) and standalone HTML dashboard.
- **Standards Mapping**:
  - **ISBT 128**: Blood unit identifiers follow standard donation and sequence coding.
  - **HL7 FHIR**: Transfer requests map to `SupplyRequest` and `SupplyDelivery` resources.
  - **DHIS2**: Monthly stock summary aggregates align with national ministry indicators.

## AI and data
- **What the AI or data feature does**: Predicts daily blood demand by facility and blood group for a 14-day projection horizon using recursive time-series lag roll-forward.
- **Baseline we compared against**: 7-day Moving Average baseline.
- **Result**:
  - Baseline (7-day MA): MAE `0.4676`, WAPE `128.63%`
  - LightGBM Regressor: MAE `0.4917`, WAPE `135.27%` (captures non-linear seasonality and holiday cliffs; outputs 90% and 10% confidence bounds).
- **How a user sees the reason for a recommendation**: Plain-language factual explanations derived directly from database queries (e.g., initial stock, projected 7-day deficit, units expiring within window). No LLM hallucination.
- **Who approves it (Accept / Change / Reject)**: A qualified inventory manager or transfusion officer. Every recommendation defaults to `Pending Approval`.
- **What happens if the AI is wrong or offline**: If sync telemetry exceeds 24 hours or the predictive service drops, the system displays an amber warning and falls back to a deterministic local physical-count safety-stock heuristic ($< 4$ units = High Risk).

## Operational Simulation Backtest Results (Section 8)
Using chronological backtesting on the starter dataset across Kenya's 47 facilities:
- **Total Critical & High-Risk Positions Monitored**: 279
- **Actionable Transfers Proposed**: 25 route-optimized redistribution runs
- **Total Blood Units Redistributed**: 169 units
- **Projected Stockouts Avoided**: 23 acute shortage events prevented
- **Lead Time Gained Before Deficit**: +4.8 days average buffer gained
- **Average Transit Distance**: 155.1 km (~3.4 hours via road network)
- **Donor Safety Buffer**: ≥ 15 units preserved at all source facilities

## Data
- Starter dataset tables used: `facilities.csv`, `routes.csv`, `requests.csv`, `daily_stock.csv`, `units.csv`, `transfers.csv`, `donations.csv`, `donors.csv`, `drives.csv`, `power_outages.csv`, `temperature_logs.csv`.
- No real patient, donor, or facility data is included (fully synthetic dataset).

## African conditions
- **Low Connectivity & Power Outages**: Evaluates local data freshness, alerts on stale data (>24h), and caches views locally in `localStorage`.
- **Road Transit Friction**: Route optimization ranks donor candidates by real-world road hours and kilometers rather than straight-line distance.
- **Configurable Settings**: Rules, threshold days, and facility parameters are stored in SQLite rather than hardcoded.

## AI tools we used
- Antigravity AI: Used for code refactoring and test suite generation.

## Team
| Name | Role | Country | Presenting Friday (in person / online) |
|------|------|---------|-----------------------------------------|
| Chima Emmanuel | Lead Developer / ML Engineer | Nigeria | Online |
| Ayomide Agbaje | ML Engineer | Rwanda | Online |

## Known limits and next steps
- Add SMS dispatch integration for drivers via Africa's Talking.
- Incorporate temperature excursion severity weights into expiry projections.
- Pilot test with regional transfusion managers in Nairobi and Kisumu.

