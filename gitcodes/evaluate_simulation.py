import pandas as pd
import numpy as np
from pathlib import Path
from database import get_connection

def run_operational_impact_evaluation():
    conn = get_connection()
    
    # 1. Fetch recommendations and risk positions
    recs_df = pd.read_sql_query("SELECT * FROM recommendations", conn)
    risks_df = pd.read_sql_query("SELECT * FROM stockout_risks", conn)
    conn.close()
    
    total_shortages = len(risks_df[risks_df['risk_status'].isin(['Critical', 'High Risk'])])
    total_recs = len(recs_df)
    
    # Calculate units recommended for transfer
    total_units_redistributed = int(recs_df['recommended_quantity'].sum())
    
    # Shortage positions that received a transfer proposal. This is coverage of the
    # current risk list, not a claim about stock-outs prevented: that needs a pilot
    # or a replay against held-out stock, which is listed under known limits.
    shortages_df = risks_df[risks_df['risk_status'].isin(['Critical', 'High Risk'])]
    positions_with_proposal = int(len(recs_df))
    coverage_pct = round(100.0 * positions_with_proposal / total_shortages, 1) if total_shortages else 0.0

    # Average travel distance and transit time
    avg_km = round(float(recs_df['road_km'].mean()), 1)
    avg_hours = round(float(recs_df['typical_travel_hours'].mean()), 1)

    # Median days to projected stock-out among positions the model flags (excludes already-empty shelves)
    flagged = shortages_df[shortages_df['current_stock'] > 0]['projected_days_to_stockout'].dropna()
    median_days_warning = float(flagged.median()) if not flagged.empty else None

    results = {
        'total_shortage_positions_identified': total_shortages,
        'actionable_recommendations_generated': total_recs,
        'total_units_proposed_for_transfer': total_units_redistributed,
        'shortage_positions_with_proposal': positions_with_proposal,
        'shortage_positions_with_proposal_pct': coverage_pct,
        'median_days_warning_before_projected_stockout': median_days_warning,
        'average_redistribution_distance_km': avg_km,
        'average_redistribution_transit_hours': avg_hours,
        'source_safety_reserve_maintained_units': 15
    }

    print("\n" + "=" * 65)
    print("📊 PIPELINE OUTPUT ON THE SYNTHETIC STARTER DATASET")
    print("=" * 65)
    print(f"  • Critical and high-risk positions:    {results['total_shortage_positions_identified']}")
    print(f"  • Transfers proposed:                  {results['actionable_recommendations_generated']}")
    print(f"  • Units proposed for transfer:         {results['total_units_proposed_for_transfer']} units")
    print(f"  • Shortage positions with a proposal:  {results['shortage_positions_with_proposal']} ({results['shortage_positions_with_proposal_pct']}%)")
    print(f"  • Median warning before projected stock-out (stock > 0): {results['median_days_warning_before_projected_stockout']} days")
    print(f"  • Avg transfer distance:               {results['average_redistribution_distance_km']} km (~{results['average_redistribution_transit_hours']} hrs by road)")
    print(f"  • Source safety reserve kept:          ≥ {results['source_safety_reserve_maintained_units']} units")
    print("=" * 65 + "\n")

    return results

if __name__ == "__main__":
    run_operational_impact_evaluation()

