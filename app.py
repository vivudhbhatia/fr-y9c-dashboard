import streamlit as st
import requests
import pandas as pd
import json
from y9c_dashboard.parse_mdrm import load_mnemonic_mapping
import os
import plotly.express as px

# --------------------------
# Load MDRM mapping
# --------------------------
mnemonic_mapping = load_mnemonic_mapping()
reverse_mapping = {v.upper(): k for k, v in mnemonic_mapping.items()}

# --------------------------
# Supabase Config
# --------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# --------------------------
# Utility Functions
# --------------------------
def extract_field(data, field):
    try:
        return float(data.get(field, None))
    except:
        return None

def safe_parse_json(x):
    try:
        return json.loads(x) if isinstance(x, str) else (x if isinstance(x, dict) else {})
    except Exception as e:
        return {}

def infer_total_assets(x):
    try:
        return extract_field(x, "bhck2170") or extract_field(x, "bhck0337") or extract_field(x, "bhck0020")
    except:
        return None

def asset_bucket(val):
    if val is None or val == 0: return None
    if val >= 750_000_000: return ">=750 billion"
    elif val >= 500_000_000: return "500-750 billion"
    elif val >= 250_000_000: return "250-500 billion"
    elif val >= 100_000_000: return "100-250 billion"
    else: return "<100 billion"

@st.cache_data(ttl=600)
def get_periods():
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=report_period&distinct=report_period"
    r = requests.get(url, headers=HEADERS)
    try:
        data = r.json()
        return sorted({rec["report_period"] for rec in data if "report_period" in rec}, reverse=True)
    except Exception as e:
        st.error(f"❌ Error loading periods: {e}")
        return []

@st.cache_data(ttl=600)
def fetch_data(period):
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,report_period,data&report_period=eq.{period}&limit=100000"
    r = requests.get(url, headers=HEADERS)
    try:
        response_json = r.json()
        if not isinstance(response_json, list):
            st.error("❌ Unexpected response from Supabase.")
            return pd.DataFrame()
        df = pd.json_normalize(response_json)
        df["rssd_id"] = df["rssd_id"].astype(str)
        df["parsed"] = df["data"].apply(safe_parse_json)
        df["total_assets"] = df["parsed"].apply(lambda x: infer_total_assets(x) if isinstance(x, dict) else None)
        df["bank_name"] = df["parsed"].apply(lambda x: x.get("rssd9001", "Unknown"))
        return df
    except Exception as e:
        st.error(f"❌ Failed to fetch data: {e}")
        return pd.DataFrame()

# --------------------------
# Streamlit Layout
# --------------------------
st.set_page_config(page_title="FR Y-9C Dashboard", layout="wide")
st.title("📊 FR Y-9C Bank Dashboard")

if st.button("🔄 Reload Data"):
    st.cache_data.clear()
    st.experimental_rerun()

periods = get_periods()
if not periods:
    st.stop()

col_period, col_compare = st.sidebar.columns(2)
selected_period = col_period.selectbox("📅 Select Period", periods, key="main")
compare_period = col_compare.selectbox("📊 Compare To", ["None"] + periods, key="compare")

user_inputs = st.sidebar.multiselect("🔍 Add fields (search by name or mnemonic)", list(mnemonic_mapping.values()))
selected_mnemonics = [reverse_mapping[item.upper()] for item in user_inputs if item.upper() in reverse_mapping]

asset_filter = st.sidebar.selectbox("🏦 Asset Size Filter", ["All", ">=750 billion", "500-750 billion", "250-500 billion", "100-250 billion", "<100 billion"])
show_chart = st.sidebar.checkbox("📈 Show Asset Distribution")
export_csv = st.sidebar.checkbox("💾 Export CSV")

with st.spinner("⏳ Loading data..."):
    df = fetch_data(selected_period)

if df.empty:
    st.warning("⚠️ No data returned. Check your filters or data source.")
    st.stop()

df["asset_bucket"] = df["total_assets"].apply(asset_bucket)
df = df[df["total_assets"] > 0]
if asset_filter != "All":
    df = df[df["asset_bucket"] == asset_filter]

for code in selected_mnemonics:
    df[code] = df["parsed"].apply(lambda x: extract_field(x, code.lower()))
    missing = df[code].isnull().sum()
    if missing == len(df):
        st.warning(f"⚠️ All values missing for {code}.")
    elif missing > 0:
        st.info(f"ℹ️ {missing} values missing for {code}.")

# --- Summary Metrics
col1, col2 = st.columns(2)
col1.metric("Avg Total Assets", f"${df['total_assets'].mean():,.0f}")
col2.metric("Banks Reporting", df["rssd_id"].nunique())

# --- Display Data Table
display_cols = ["rssd_id", "bank_name", "total_assets"] + selected_mnemonics
display_df = df[display_cols].copy()
display_df.columns = ["RSSD ID", "Bank Name", "Total Assets"] + [mnemonic_mapping.get(m, m) for m in selected_mnemonics]

st.subheader(f"📋 Data for {selected_period}")
st.dataframe(display_df, use_container_width=True)

# --- Asset Size Chart
if show_chart:
    st.subheader("📊 Asset Distribution")
    fig = px.histogram(df, x="total_assets", nbins=40, title="Bank Total Assets")
    st.plotly_chart(fig, use_container_width=True)

# --- CSV Export
if export_csv:
    st.download_button(
        label="Download CSV",
        data=display_df.to_csv(index=False),
        file_name=f"y9c_{selected_period}.csv",
        mime="text/csv"
    )

# --- Period Comparison
if compare_period != "None" and compare_period != selected_period:
    st.subheader(f"🔁 Comparing {selected_period} vs {compare_period}")
    df2 = fetch_data(compare_period)
    df2["total_assets"] = df2["parsed"].apply(lambda x: infer_total_assets(x) if isinstance(x, dict) else None)
    df2 = df2[df2["total_assets"] > 0]

    merged = pd.merge(
        df[["rssd_id", "bank_name", "total_assets"]],
        df2[["rssd_id", "total_assets"]],
        on="rssd_id", how="inner",
        suffixes=(f"_{selected_period}", f"_{compare_period}")
    )

    merged["delta"] = merged[f"total_assets_{selected_period}"] - merged[f"total_assets_{compare_period}"]
    merged["% Change"] = (merged["delta"] / merged[f"total_assets_{compare_period}"]) * 100
    merged["Change"] = merged["delta"].apply(lambda x: "📈" if x > 0 else ("📉" if x < 0 else "➖"))

    st.dataframe(merged[[
        "rssd_id", "bank_name",
        f"total_assets_{selected_period}",
        f"total_assets_{compare_period}",
        "delta", "% Change", "Change"
    ]].sort_values(by="delta", ascending=False), use_container_width=True)
