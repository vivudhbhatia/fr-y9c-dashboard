import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
from datetime import datetime
import json
import time
import ast
import traceback
import backoff  # Added for advanced retry logic



# Initialize Supabase Client with timeout
@st.cache_resource
def init_supabase() -> Client:
    try:
        # Verify secrets exist first
        if not hasattr(st.secrets, 'SUPABASE_URL'):
            raise ValueError("Missing SUPABASE_URL in secrets")
        if not hasattr(st.secrets, 'SUPABASE_KEY'):
            raise ValueError("Missing SUPABASE_KEY in secrets")
            
        # Create client with validated secrets
        return create_client(
            supabase_url=st.secrets.SUPABASE_URL,
            supabase_key=st.secrets.SUPABASE_KEY
        )
    except Exception as e:
        st.error(f"Supabase initialization failed: {str(e)}")
        st.stop()

# Advanced pagination with exponential backoff
@backoff.on_exception(backoff.expo, Exception, max_tries=5)
def fetch_batch(table_name, page, batch_size):
    supabase = init_supabase()
    return supabase.table(table_name)\
                .select("*")\
                .range(page*batch_size, (page+1)*batch_size-1)\
                .execute()

def fetch_paginated_data(table_name, batch_size=100):
    all_data = []
    page = 0
    
    try:
        # First get total count
        count = init_supabase().table(table_name)\
                   .select("count", count='exact')\
                   .execute().count
        
        with st.spinner(f"Loading {table_name} (0/{count})..."):
            while len(all_data) < count:
                response = fetch_batch(table_name, page, batch_size)
                all_data.extend(response.data)
                page += 1
                time.sleep(0.5)  # Conservative delay
                
                # Update progress
                st.write(f"📦 {table_name}: {len(all_data)}/{count} records")
                
        return pd.DataFrame(all_data)
    
    except Exception as e:
        st.error(f"Error fetching {table_name}: {str(e)}")
        st.stop()

# Optimized data loader
@st.cache_data(ttl=3600, show_spinner="Loading regulatory data...")
def load_data():
    try:
        st.write("🚀 Starting optimized data load...")
        
        # 1. Load MDRM mappings first with server-side filtering
        st.write("⏳ Loading active MDRM mappings...")
        mdrm_df = fetch_paginated_data('mdrm_mapping')
        mdrm_active = mdrm_df[mdrm_df['end_date'] == '9999-12-31']
        st.write(f"✅ Active mappings: {mdrm_active.shape[0]}")
        
        # 2. Load Y9C data with server-side filtering
        st.write("⏳ Loading Y9C reports (last 5 years)...")
        y9c_df = fetch_paginated_data('y9c_full')
        
        # 3. Server-side filtering (using client-side fallback)
        y9c_df = y9c_df[y9c_df['report_period'] >= '2018-01-01']  # 5 year window
        st.write(f"✅ Filtered Y9C records: {y9c_df.shape[0]}")
        
        # ... [rest of data processing logic] ...

        return merged_df, merged_df

    except Exception as e:
        st.error(f"Critical error: {str(e)}")
        st.text(traceback.format_exc())
        st.stop()




# Formatting function
def format_metric(value, metric_name):
    try:
        if pd.isna(value):
            return "N/A"
        if any(kw in metric_name.lower() for kw in ['ratio', '%', 'rate']):
            return f"{value:.2f}%"
        if abs(value) >= 1e9:
            return f"${value/1e9:.2f}B"
        if abs(value) >= 1e6:
            return f"${value/1e6:.2f}M"
        return f"${value:,.2f}"
    except:
        return "N/A"

# Main app
def main():
    st.set_page_config(
        page_title="FR Y-9C Regulatory Dashboard",
        layout="wide",
        page_icon="📊"
    )

    st.title("FR Y-9C Regulatory Dashboard")
    st.caption("Dynamic reporting powered by Supabase data")

    # Load data
    raw_df, analysis_df = load_data()

    # Date handling
    if not analysis_df.empty:
        dates = analysis_df['Report Date'].dt.date.unique()
        date_options = sorted(dates, reverse=True)
    else:
        date_options = []

    # Sidebar controls
    with st.sidebar:
        st.header("🔍 Filters")
        
        selected_dates = st.multiselect(
            "Reporting Period",
            options=date_options,
            default=date_options[:1] if date_options else []
        )

        institutions = st.multiselect(
            "Select Institutions",
            options=analysis_df['RSSD ID'].unique() if not analysis_df.empty else [],
            default=analysis_df['RSSD ID'].unique()[:3] if not analysis_df.empty else []
        )

        available_metrics = [col for col in analysis_df.columns 
                           if col not in ['RSSD ID', 'Report Date', 'composite_key']]
        selected_metrics = st.multiselect(
            "Key Metrics",
            options=available_metrics,
            default=available_metrics[:3] if available_metrics else []
        )

    # Filter data
    filtered_df = analysis_df[
        (analysis_df['Report Date'].dt.date.isin(selected_dates)) &
        (analysis_df['RSSD ID'].isin(institutions))
    ] if not analysis_df.empty else pd.DataFrame()

    # Display metrics
    st.header("📈 Key Performance Indicators")
    if not filtered_df.empty:
        cols = st.columns(len(selected_metrics))
        latest_date = filtered_df['Report Date'].max()
        latest_data = filtered_df[filtered_df['Report Date'] == latest_date]
        
        for idx, metric in enumerate(selected_metrics):
            with cols[idx]:
                value = latest_data[metric].mean()
                st.metric(
                    label=metric,
                    value=format_metric(value, metric),
                    help=raw_df[raw_df['item_name'] == metric]['description'].iloc[0] 
                         if not raw_df.empty else ""
                )
    else:
        st.warning("No data available for selected filters")

if __name__ == "__main__":
    main()
