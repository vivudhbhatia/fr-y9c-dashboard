# app.py
import streamlit as st
import requests
import pandas as pd
import json
import os
from urllib.parse import quote

# ─── CONFIGURATION ───
st.set_page_config(page_title="FR Y-9C Dashboard", layout="wide")
st.title("📊 FR Y-9C Bank Dashboard")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase environment variables are not set.")
    st.stop()

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# ─── HELPER FUNCTIONS ───
def extract_field(data, field):
    try:
        return float(data.get(field, None))
    except Exception:
        return None

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
    return extract_field(x, "bhck2170") or extract_field(x, "bhck0337") or extract_field(x, "bhck0020")

def asset_bucket(val):
    if val is None or val == 0:
        return None
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

@st.cache_data(ttl=600)
def fetch_all_data():
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,report_period,data&limit=100000"
    r = requests.get(url, headers=HEADERS)
    try:
        response_json = r.json()
    except:
        return pd.DataFrame()
    if not isinstance(response_json, list):
        return pd.DataFrame()

    df = pd.json_normalize(response_json)
    if "rssd_id" not in df.columns:
        return pd.DataFrame()

    df["rssd_id"] = df["rssd_id"].astype(str)
    df["parsed"] = df["data"].apply(safe_parse_json)
    df["total_assets"] = df["parsed"].apply(lambda x: infer_total_assets(x) if isinstance(x, dict) else None)
    df["bank_name"] = df["parsed"].apply(lambda x: x.get("rssd9001", "Unknown"))
    df["asset_bucket"] = df["total_assets"].apply(asset_bucket)
    return df

# ─── MAIN ───
if st.button("🔄 Reload Data"):
    st.cache_data.clear()
    st.rerun()

full_df = fetch_all_data()

if full_df.empty:
    st.warning("⚠️ No data returned.")
    st.stop()

# ─── FILTERS ───
st.subheader("🔎 Optional Filters")

periods = sorted(full_df["report_period"].dropna().unique(), reverse=True)
selected_period = st.selectbox("Select Reporting Period", [None] + periods)

bank_names = sorted(full_df["bank_name"].dropna().unique())
selected_bank = st.selectbox("Select Bank Name", [None] + bank_names)

asset_buckets = sorted(full_df["asset_bucket"].dropna().unique())
selected_bucket = st.selectbox("Select Asset Bucket", [None] + asset_buckets)

# ─── APPLY FILTERS ───
filtered_df = full_df.copy()

if selected_period:
    filtered_df = filtered_df[filtered_df["report_period"] == selected_period]

if selected_bank:
    filtered_df = filtered_df[filtered_df["bank_name"] == selected_bank]

if selected_bucket:
    filtered_df = filtered_df[filtered_df["asset_bucket"] == selected_bucket]

# ─── RESULTS ───
st.subheader("🏦 Bank Summary")
st.dataframe(filtered_df[["rssd_id", "bank_name", "total_assets", "report_period"]].sort_values("total_assets", ascending=False))
