import pandas as pd
from datetime import datetime

def load_mnemonic_mapping():
    df = pd.read_csv("y9c_dashboard/MDRM/MDRM_CSV.csv", encoding="latin1")

    # Normalize column names (remove whitespace)
    df.columns = df.columns.str.strip()

    # Ensure datetime parsing for end dates
    df["End Date"] = pd.to_datetime(df["End Date"], errors="coerce")
    df["Start Date"] = pd.to_datetime(df["Start Date"], errors="coerce")

    # Keep only FR Y-9C entries
    df = df[df["Reporting Form"].str.contains("FR Y-9C", na=False)]

    # Filter to only items still active
    df = df[df["End Date"] >= datetime.today()]

    # Sort to get the most recent start date for each mnemonic+code combo
    df["key"] = df["Mnemonic"].str.upper() + df["Item Code"].astype(str)
    df = df.sort_values(by="Start Date", ascending=False)

    # Drop duplicates to retain most recent description
    latest = df.drop_duplicates(subset="key", keep="first")

    # Build the dictionary
    mapping = {row["key"]: row["Item Name"].strip() for _, row in latest.iterrows()}
    return mapping
