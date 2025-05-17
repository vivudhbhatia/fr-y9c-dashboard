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
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,data&limit=100000"
    r = requests.get(url, headers=HEADERS)
    try:
        response_json = r.json()
    except:
        return pd.DataFrame()
    if not isinstance(response_json, list):
        return pd.DataFrame()

    df = pd.json_normalize(response_json)
    df["rssd_id"] = df["rssd_id"].astype(str)
    df["parsed"] = df["data"].apply(safe_parse_json)
    df["bank_name"] = df["parsed"].apply(lambda x: x.get("rssd9017", "Unknown"))
    df["report_period"] = df["parsed"].apply(lambda x: x.get("rssd9999"))
    df["total_assets"] = df["parsed"].apply(lambda x: infer_total_assets(x) if isinstance(x, dict) else None)
    df["asset_bucket"] = df["total_assets"].apply(asset_bucket)
    return df

@st.cache_data(ttl=600)
def get_all_report_periods():
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=data&limit=9999"
    r = requests.get(url, headers=HEADERS)

    if not r.ok:
        st.error(f"❌ Supabase error: {r.status_code} – {r.text}")
        return []

    try:
        data = r.json()
        parsed = [safe_parse_json(row["data"]) for row in data if isinstance(row, dict) and "data" in row]
        return sorted({str(x.get("rssd9999")) for x in parsed if x.get("rssd9999")}, reverse=True)
    except Exception as e:
        st.error(f"❌ Failed to parse periods: {e}")
        return []

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

raw_periods = get_all_report_periods()
selected_period = st.selectbox("Select Reporting Period", [None] + raw_periods)

bank_query = st.text_input("Search Bank (Legal Name or RSSD ID)")

asset_buckets = sorted(full_df["asset_bucket"].dropna().unique())
selected_bucket = st.selectbox("Select Asset Bucket", [None] + asset_buckets)

# ─── APPLY FILTERS ───
filtered_df = full_df.copy()

if selected_period:
    filtered_df = filtered_df[filtered_df["report_period"] == selected_period]

if bank_query:
    q = bank_query.lower().strip()
    filtered_df = filtered_df[
        filtered_df["bank_name"].str.lower().str.contains(q) |
        filtered_df["rssd_id"].str.contains(q)
    ]

if selected_bucket:
    filtered_df = filtered_df[filtered_df["asset_bucket"] == selected_bucket]

# ─── CLEANED DISPLAY ───
st.subheader("🏦 Bank Summary")

filtered_df["total_assets"] = pd.to_numeric(filtered_df["total_assets"], errors="coerce")
display_df = filtered_df.dropna(subset=["total_assets"]).copy()
display_df["Total Assets ($)"] = display_df["total_assets"].apply(lambda x: f"${x:,.0f}")

st.dataframe(
    display_df[["rssd_id", "bank_name", "Total Assets ($)", "report_period"]],
    use_container_width=True
)
