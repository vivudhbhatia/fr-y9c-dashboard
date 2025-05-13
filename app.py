import streamlit as st
import requests
import pandas as pd

# Load Supabase secrets from .streamlit/secrets.toml or Streamlit Cloud
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

@st.cache_data(ttl=300)
def fetch_data():
    url = f"{SUPABASE_URL}/rest/v1/y9c_full?select=rssd_id,report_period,data&limit=10000"
    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        st.error(f"❌ Error fetching data from Supabase: {r.text}")
        return pd.DataFrame()

    try:
        records = r.json()
        if not records:
            st.warning("⚠️ No records returned from Supabase.")
            return pd.DataFrame()
        df = pd.json_normalize(records)

        if "rssd_id" not in df.columns or "report_period" not in df.columns:
            st.error("❌ Missing expected columns 'rssd_id' or 'report_period'.")
            return pd.DataFrame()

        df["rssd_id"] = df["rssd_id"].astype(str)
        df["report_period"] = df["report_period"].astype(str)
        return df

    except Exception as e:
        st.error(f"❌ Error parsing Supabase response: {e}")
        return pd.DataFrame()

def extract_field(row, field):
    try:
        return float(row.get("data", {}).get(field, None))
    except:
        return None

# Streamlit App UI
st.set_page_config(page_title="FR Y-9C Dashboard", layout="wide")
st.title("📊 FR Y-9C Bank Dashboard")

df = fetch_data()
if df.empty:
    st.stop()

# Sidebar filter
st.sidebar.header("🔎 Filter")
report_periods = sorted(df["report_period"].unique(), reverse=True)
selected_period = st.sidebar.selectbox("Select a Reporting Period", report_periods)

filtered_df = df[df["report_period"] == selected_period].copy()

# Extract key financials
filtered_df["total_assets"] = filtered_df["data"].apply(lambda x: extract_field(x, "bhck2170"))
filtered_df["net_income"] = filtered_df["data"].apply(lambda x: extract_field(x, "bhck4340"))
filtered_df["tier1_ratio"] = filtered_df["data"].apply(lambda x: extract_field(x, "bhck8274"))

# KPI Summary Cards
col1, col2, col3 = st.columns(3)
col1.metric("📦 Avg Total Assets", f"${filtered_df['total_assets'].mean():,.0f}")
col2.metric("💰 Avg Net Income", f"${filtered_df['net_income'].mean():,.0f}")
col3.metric("🏛 Avg Tier 1 Ratio", f"{filtered_df['tier1_ratio'].mean():.2f}%")

# Full Table
st.subheader(f"📋 Institutions Reporting - {selected_period}")
st.dataframe(
    filtered_df[["rssd_id", "total_assets", "net_income", "tier1_ratio"]]
    .sort_values(by="total_assets", ascending=False),
    use_container_width=True
)
