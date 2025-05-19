# dashboard.py
import streamlit as st
import pandas as pd
import requests
import os
import json

# ─── ENV CONFIG ───
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase environment variables are not set. Please check SUPABASE_URL and SUPABASE_KEY.")
    st.stop()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ─── HELPERS ───
def safe_parse_json(x):
    try:
        if isinstance(x, str):
            return json.loads(json.loads(x)) if x.strip().startswith('"{"') else json.loads(x)
        elif isinstance(x, dict):
            return x
        return {}
    except Exception:
        return {}

def infer_total_assets(x):
    try:
        return float(x.get("bhck2170") or x.get("bhck0337") or x.get("bhck0020") or 0)
    except Exception:
        return 0

def fetch_full_data():
    rows = []
    page_size = 1000
    offset = 0

    while True:
        url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,data&offset={offset}&limit={page_size}"
        try:
            r = requests.get(url, headers=HEADERS)
            if not r.ok:
                st.error(f"❌ Supabase error: {r.status_code} – {r.text}")
                return pd.DataFrame()
            page = r.json()
            if not page:
                break
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        except Exception as e:
            st.error(f"❌ Supabase request failed: {e}")
            return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    df = pd.json_normalize(rows)
    df["rssd_id"] = df["rssd_id"].astype(str)
    df["parsed"] = df["data"].apply(safe_parse_json)
    df["bank_name"] = df["parsed"].apply(lambda x: x.get("rssd9017", "Unknown"))
    df["report_period"] = df["parsed"].apply(lambda x: str(x.get("rssd9999")))
    df["total_assets"] = df["parsed"].apply(lambda x: infer_total_assets(x))
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
    if df.empty or "parsed" not in df.columns:
        return []
    example_record = df["parsed"].iloc[0]
    return sorted([k.upper() for k in example_record.keys() if k.startswith("bhck") or k.startswith("rcon")])

# ─── PAGE SETUP ───
st.set_page_config(page_title="FR Y-9C Dashboard", layout="wide")
st.title("📊 FR Y-9C Peer Performance Dashboard")

# ─── DATA LOAD ───
full_df = fetch_full_data()
if full_df.empty:
    st.warning("⚠️ No data available to display.")
    st.stop()

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
