# app.py
import streamlit as st
import requests
import pandas as pd
import json
from datetime import datetime
import os
import plotly.express as px
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

# ─── LOAD MDRM ───
try:
    from y9c_dashboard.parse_mdrm import load_mnemonic_mapping
    mnemonic_mapping = load_mnemonic_mapping()
    reverse_mapping = {v.strip().lower(): k for k, v in mnemonic_mapping.items()}
except Exception as e:
    st.error(f"❌ Failed to load MDRM mapping: {e}")
    mnemonic_mapping = {}
    reverse_mapping = {}

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
        if not isinstance(data, list):
            return []
        return sorted({rec["report_period"] for rec in data if "report_period" in rec}, reverse=True)
    except:
        return []

@st.cache_data(ttl=600)
def fetch_data(period):
    if not period:
        return pd.DataFrame()
    safe_period = quote(f'"{period}"')
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,report_period,data&report_period=eq.{safe_period}&limit=100000"
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

# ─── USER INPUT ───
if st.button("🔄 Reload Data"):
    st.cache_data.clear()
    st.rerun()

periods = get_periods()
period_selector = st.selectbox("Select Reporting Period (optional)", ["All"] + periods)
if period_selector == "All":
    all_data = [fetch_data(p) for p in periods]
    all_data = [df for df in all_data if not df.empty]
    if not all_data:
        st.warning("⚠️ No data available across periods.")
        st.stop()
    full_df = pd.concat(all_data, ignore_index=True)
else:
    full_df = fetch_data(period_selector)

if full_df.empty:
    st.warning("⚠️ No data returned for the selected period.")
    st.stop()

buckets = sorted(full_df["asset_bucket"].dropna().unique())
selected_bucket = st.selectbox("Select Asset Bucket (optional)", ["All"] + buckets)
if selected_bucket != "All":
    full_df = full_df[full_df["asset_bucket"] == selected_bucket]

# ─── LANDING PAGE ───
st.subheader("🏦 Bank Summary")
st.dataframe(full_df[["rssd_id", "bank_name", "total_assets"]].sort_values("total_assets", ascending=False))

# ─── COMPARISON CHART ───
st.subheader("📈 Compare Banks on Selected Mnemonic")

mnemonic_keys = list(mnemonic_mapping.keys())
selected_mnemonic = st.selectbox("Select Mnemonic to Compare", mnemonic_keys)

if selected_mnemonic:
    full_df["value"] = full_df["parsed"].apply(lambda x: extract_field(x, selected_mnemonic))
    chart_df = full_df.dropna(subset=["value"])
    if not chart_df.empty:
        fig = px.bar(
            chart_df.sort_values("value", ascending=False).head(20),
            x="bank_name",
            y="value",
            title=f"Top 20 Banks by Value for {selected_mnemonic} ({mnemonic_mapping.get(selected_mnemonic, '')})",
            labels={"value": "Reported Value", "bank_name": "Bank"}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ℹ️ No data available for the selected mnemonic in this asset bucket.")
