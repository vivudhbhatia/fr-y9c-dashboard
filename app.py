# dashboard.py
import streamlit as st
import pandas as pd
import requests
import os

# ─── ENV CONFIG ───
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ─── HELPERS ───
def fetch_full_data():
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,report_period,data"
    r = requests.get(url, headers=HEADERS)
    df = pd.DataFrame(r.json())
    df["parsed"] = df["data"].apply(lambda x: x if isinstance(x, dict) else {})
    df["total_assets"] = df["parsed"].apply(lambda x: float(x.get("bhck2170", 0)))
    df["bank_name"] = df["parsed"].apply(lambda x: x.get("rssd9017", "Unknown"))
    df["asset_bucket"] = df["total_assets"].apply(bucketize_assets)
    return df

def bucketize_assets(val):
    if val >= 750_000_000:
        return ">=750 billion"
    elif val >= 500_000_000:
        return "500-750 billion"
    elif val >= 250_000_000:
        return "250-500 billion"
    elif val >= 100_000_000:
        return "100-250 billion"
    else:
        return "<100 billion"

def extract_available_periods(df):
    return sorted(df["report_period"].dropna().unique(), reverse=True)

def extract_available_criteria(df):
    example_record = df["parsed"].iloc[0]
    return sorted([k.upper() for k in example_record.keys() if k.startswith("bhck") or k.startswith("rcon")])

# ─── PAGE SETUP ───
st.set_page_config(page_title="FR Y-9C Dashboard", layout="wide")
st.title("📊 FR Y-9C Peer Performance Dashboard")

# ─── DATA LOAD ───
full_df = fetch_full_data()
reporting_periods = extract_available_periods(full_df)
criteria_options = extract_available_criteria(full_df)
asset_buckets = sorted(full_df["asset_bucket"].dropna().unique())

# ─── FILTERS ───
with st.container():
    st.subheader("🔎 Optional Filters")
    col1, col2, col3 = st.columns(3)

    with col1:
        selected_period = st.selectbox("Select Reporting Period", reporting_periods)
    with col2:
        selected_criteria = st.selectbox("Select Criteria (MDRM)", criteria_options)
    with col3:
        selected_bucket = st.selectbox("Select Asset Bucket (Peer Group)", asset_buckets)

    st.button("🔵 Generate Report")
