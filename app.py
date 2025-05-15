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
if not periods:
    st.stop()

selected_period = st.selectbox("Select Reporting Period", periods)
df = fetch_data(selected_period)
if df.empty:
    st.warning("⚠️ No data returned for the selected period.")
    st.stop()

# ─── FILTERS ───
buckets = sorted(df["asset_bucket"].dropna().unique())
selected_bucket = st.selectbox("Select Asset Bucket", buckets)
banks_in_bucket = df[df["asset_bucket"] == selected_bucket].copy()

bank_options = banks_in_bucket["bank_name"].unique()
selected_banks = st.multiselect("Select Banks in Asset Bucket", bank_options, default=bank_options[:3])

mnemonic_label = st.selectbox("Select Metric (Item Name)", sorted(mnemonic_mapping.values()))
mnemonic_key = reverse_mapping.get(mnemonic_label.strip().lower())

# Fallback if metric not found
if not mnemonic_key:
    mnemonic_key = "bhck2170"
    st.warning("⚠️ Falling back to BHCK2170 (Total Assets) due to unknown selection.")

comparison_df = banks_in_bucket[banks_in_bucket["bank_name"].isin(selected_banks)].copy()
comparison_df["metric_value"] = comparison_df["parsed"].apply(lambda x: extract_field(x, mnemonic_key))

if comparison_df["metric_value"].isnull().all():
    st.warning("⚠️ No metric values found for the selected banks and mnemonic.")
    st.dataframe(comparison_df[["bank_name", "parsed"]].head(5))
    st.stop()

fig = px.bar(
    comparison_df,
    x="bank_name",
    y="metric_value",
    title=f"Comparison of '{mnemonic_label}' in {selected_bucket} bucket",
    labels={"metric_value": mnemonic_label, "bank_name": "Bank"}
)
st.plotly_chart(fig, use_container_width=True)

# ─── MDRM LOOKUP ───
st.markdown("---")
st.subheader("📘 MDRM Dictionary Lookup")
search_term = st.text_input("Search MDRM Mnemonic or Description")
if search_term:
    filtered = {
        k: v for k, v in mnemonic_mapping.items()
        if search_term.lower() in k.lower() or search_term.lower() in v.lower()
    }
    if filtered:
        for k, v in filtered.items():
            st.markdown(f"**{k}** → {v}")
    else:
        st.info("No matches found.")
