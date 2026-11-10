import os
import pandas as pd
import numpy as np

from pathlib import Path

# check csv files
files_to_check = [
    "facilities.csv", "routes.csv", "donors.csv", "drives.csv", 
    "donations.csv", "units.csv", "transfers.csv", "requests.csv", 
    "power_outages.csv", "temperature_logs.csv", "daily_stock.csv"
]

project_root = Path(__file__).resolve().parent.parent

base_dir = '.'
if os.path.exists('out'):
    base_dir = 'out'
elif not os.path.exists('facilities.csv') and (project_root / 'facilities.csv').exists():
    base_dir = str(project_root)

print(f"Analyzing datasets from directory: {base_dir}\n")

dataframes = {}
for f in files_to_check:
    path = os.path.join(base_dir, f)
    if os.path.exists(path):
        df = pd.read_csv(path)
        dataframes[f.replace('.csv', '')] = df
        print(f"=== {f} ===")
        print(f"Shape: {df.shape}")
        missing = df.isnull().sum()
        missing_pct = 100 * missing / len(df)
        missing_df = pd.DataFrame({'Missing Values': missing, 'Percentage (%)': missing_pct})
        print(missing_df[missing_df['Missing Values'] > 0])
        print("\n")
    else:
        print(f"{f} not found in {base_dir}")

# Correlation and Collinearity in 'facilities' or numeric datasets if applicable
if 'facilities' in dataframes:
    fac_df = dataframes['facilities']
    numeric_cols = fac_df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) > 1:
        print("=== Correlation Matrix for Facilities Numeric Fields ===")
        print(fac_df[numeric_cols].corr())
        print("\n")