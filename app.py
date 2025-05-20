import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime
import json
import time
import ast
import traceback

# Initialize Supabase Client with error handling
@st.cache_resource
def init_supabase():
    try:
        return create_client(st.secrets.SUPABASE_URL, st.secrets.SUPABASE_KEY)
    except Exception as e:
        st.error(f"Supabase initialization failed: {str(e)}")
        st.stop()

# Enhanced pagination with debug logging
# ... [Keep all imports and the init_supabase function unchanged] ...

# Optimized pagination with smaller batches and timeout handling
def fetch_paginated_data(table_name, batch_size=300):
    supabase = init_supabase()
    all_data = []
    page = 0
    retries = 3  # Number of retry attempts
    
    try:
        while True:
            try:
                # Get total count first
                count_query = supabase.table(table_name).select("count", count='exact')
                total_count = count_query.execute().count
                
                # Fetch batch
                response = supabase.table(table_name)\
                             .select("*")\
                             .range(page*batch_size, (page+1)*batch_size-1)\
                             .execute()
                
                all_data.extend(response.data)
                st.write(f"Fetched {len(response.data)}/{total_count} from {table_name}")
                
                if len(all_data) >= total_count:
                    break
                page += 1
                time.sleep(0.3)  # Increased delay
                
            except Exception as e:
                if retries > 0:
                    st.write(f"Retrying... ({retries} left)")
                    retries -= 1
                    time.sleep(1)
                    continue
                else:
                    raise

        return pd.DataFrame(all_data)
    
    except Exception as e:
        st.error(f"Error fetching {table_name}: {str(e)}")
        st.stop()

# Optimized data loader with early filtering
@st.cache_data(ttl=3600, show_spinner="Loading regulatory data...")
def load_data():
    try:
        st.write("🚀 Starting optimized data load...")
        
        # 1. First load essential mapping data
        st.write("⏳ Loading MDRM mappings...")
        mdrm_df = fetch_paginated_data('mdrm_mapping')
        mdrm_active = mdrm_df[mdrm_df['end_date'] == '9999-12-31']
        st.write(f"✅ Active mappings: {mdrm_active.shape[0]}")

        # 2. Load only recent y9c data
        st.write("⏳ Loading recent Y9C reports...")
        y9c_df = fetch_paginated_data('y9c_full')
        
        # 3. Early filtering of Y9C data
        y9c_df = y9c_df.dropna(subset=['data'])
        y9c_df = y9c_df[y9c_df['report_period'] >= '2020-01-01']  # Recent 3 years
        st.write(f"✅ Filtered Y9C records: {y9c_df.shape[0]}")

        # 4. Parallel JSON parsing
        st.write("🔨 Parsing JSON metrics...")
        with st.spinner("Processing financial metrics..."):
            y9c_df['metrics'] = y9c_df['data'].parallel_apply(
                lambda x: ast.literal_eval(x.strip('"').replace('\\"', '"'))  # Requires pandarallel
            metrics_df = pd.json_normalize(y9c_df['metrics'])
            y9c_df = pd.concat([y9c_df.drop(['data', 'metrics'], axis=1), metrics_df], axis=1)

        # 5. Optimized merging
        st.write("🔗 Merging datasets...")
        required_metrics = ['bhck2170', 'bhck2948', 'bhck3210']  # Essential metrics only
        y9c_filtered = y9c_df[['RSSD ID', 'Report Date'] + required_metrics]
        
        merged_df = pd.merge(
            y9c_filtered,
            mdrm_active,
            left_on='bhck2170',
            right_on='item_code',
            how='inner'
        )
        
        st.write(f"🎉 Final dataset: {merged_df.shape[0]} rows")
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
