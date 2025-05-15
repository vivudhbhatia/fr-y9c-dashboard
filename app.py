# app.py
import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime
import os
import plotly.express as px

# ─── CONFIGURATION ───
st.set_page_config(page_title="FR Y-9C Dashboard", layout="wide")

# Ensure set_page_config is first
# Title and debug logs follow
st.title("📊 FR Y-9C Bank Dashboard")

# Supabase credentials
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
st.write("🔍 Supabase URL:", SUPABASE_URL)
st.write("🔐 Supabase Key Present:", bool(SUPABASE_KEY))
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase environment variables are not set.")
    st.stop()

# Load MDRM dictionary
try:
    from y9c_dashboard.parse_mdrm import load_mnemonic_mapping
    mnemonic_mapping = load_mnemonic_mapping()
    reverse_mapping = {v.upper(): k for k, v in mnemonic_mapping.items()}
except Exception as e:
    st.error(f"❌ Failed to load MDRM mapping: {e}")
    mnemonic_mapping = {}
    reverse_mapping = {}

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
        return json.loads(x) if isinstance(x, str) else (x if isinstance(x, dict) else {})
    except Exception as e:
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
def get_periods():
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=report_period&distinct=report_period"
    r = requests.get(url, headers=HEADERS)
    try:
        data = r.json()
        return sorted({rec["report_period"] for rec in data if "report_period" in rec}, reverse=True)
    except Exception as e:
        st.error(f"❌ Failed to load periods: {e}")
        return []

@st.cache_data(ttl=600)
def fetch_data(period):
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,report_period,data&report_period=eq.{period}&limit=100000"
    r = requests.get(url, headers=HEADERS)
    try:
        response_json = r.json()
        if not isinstance(response_json, list):
            st.error(f"❌ Supabase returned invalid JSON: {response_json}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Failed to decode JSON: {e}")
        return pd.DataFrame()

    df = pd.json_normalize(response_json)
    if "rssd_id" not in df.columns:
        st.error("❌ 'rssd_id' column missing in response.")
        return pd.DataFrame()

    df["rssd_id"] = df["rssd_id"].astype(str)
    df["parsed"] = df["data"].apply(safe_parse_json)
    df["total_assets"] = df["parsed"].apply(lambda x: infer_total_assets(x) if isinstance(x, dict) else None)
    df["bank_name"] = df["parsed"].apply(lambda x: x.get("rssd9001", "Unknown"))

    return df

# ─── USER INPUT ───
if st.button("🔄 Reload Data"):
    st.cache_data.clear()
    st.rerun()

periods = get_periods()
st.write("🗕️ Available Periods:", periods)
if not periods:
    st.stop()

selected_period = st.selectbox("Select Reporting Period", periods)

df = fetch_data(selected_period)
st.write("📦 Raw Data:", df.head())
if df.empty:
    st.warning("⚠️ No data returned for the selected period.")
    st.stop()

if "total_assets" not in df.columns:
    st.error("❌ 'total_assets' column missing from dataset.")
    st.stop()

if df["total_assets"].isnull().all():
    if "rerun_attempted" not in st.session_state:
        st.session_state["rerun_attempted"] = True
        st.cache_data.clear()
        st.rerun()
    else:
        st.warning("⚠️ No 'total_assets' data available after reload. Please check the Supabase field mapping.")
        st.stop()

# Success
df["asset_bucket"] = df["total_assets"].apply(asset_bucket)
# Ready for visualizations and filters
st.dataframe(df[["rssd_id", "bank_name", "total_assets", "asset_bucket"]].head())
