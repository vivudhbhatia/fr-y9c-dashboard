import streamlit as st
import requests
import pandas as pd
import json

# --- Load secrets ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# --- Helper to extract values from JSON ---
def extract_field(data, field):
    try:
        return float(data.get(field, None))
    except:
        return None

# --- Streamlit UI ---
st.set_page_config(page_title="FR Y-9C Dashboard", layout="wide")
st.title("📊 FR Y-9C Bank Dashboard")

# --- Select Period First (before fetching data) ---
st.sidebar.header("🔎 Filter")
selected_period = st.sidebar.text_input("Enter a Reporting Period", "20240331")

# --- Fetch filtered data from Supabase ---
@st.cache_data(ttl=300)
def fetch_data(period):
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,report_period,data&report_period=eq.{period}&limit=2000"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        records = r.json()
        if not records:
            st.warning("⚠️ No records returned from Supabase.")
            return pd.DataFrame()
        df = pd.json_normalize(records)
        df["rssd_id"] = df["rssd_id"].astype(str)
        df["report_period"] = df["report_period"].astype(str)
        return df
    except Exception as e:
        st.error(f"❌ Supabase query failed: {e}")
        return pd.DataFrame()

df = fetch_data(selected_period)
if df.empty:
    st.stop()

# --- Parse and extract key financials ---
df["parsed"] = df["data"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
df["total_assets"] = df["parsed"].apply(lambda x: extract_field(x, "bhck2170"))
df["net_income"] = df["parsed"].apply(lambda x: extract_field(x, "bhck4340"))
df["tier1_ratio"] = df["parsed"].apply(lambda x: extract_field(x, "bhck8274"))

# --- KPI Cards ---
col1, col2, col3 = st.columns(3)
col1.metric("📦 Avg Total Assets", f"${df['total_assets'].mean():,.0f}")
col2.metric("💰 Avg Net Income", f"${df['net_income'].mean():,.0f}")
col3.metric("🏛 Avg Tier 1 Ratio", f"{df['tier1_ratio'].mean():.2f}%")

# --- Table View ---
st.subheader(f"📋 Institutions Reporting - {selected_period}")
st.dataframe(
    df[["rssd_id", "total_assets", "net_income", "tier1_ratio"]]
    .sort_values(by="total_assets", ascending=False),
    use_container_width=True
)
