import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime
from io import BytesIO
import json
import time

# Initialize Supabase Client
@st.cache_resource
def init_supabase():
    return create_client(st.secrets.SUPABASE_URL, st.secrets.SUPABASE_KEY)

# Paginated data fetcher
def fetch_paginated_data(table_name, batch_size=1000):
    supabase = init_supabase()
    all_data = []
    page = 0
    
    while True:
        try:
            response = supabase.table(table_name)\
                         .select("*", count='exact')\
                         .range(page*batch_size, (page+1)*batch_size-1)\
                         .execute()
            all_data.extend(response.data)
            
            if len(all_data) >= response.count:
                break
            page += 1
            time.sleep(0.1)
        except Exception as e:
            st.error(f"Error fetching data: {str(e)}")
            break
    
    return pd.DataFrame(all_data)

# Data loader with proper closure
@st.cache_data(ttl=3600, show_spinner="Loading regulatory data...")
def load_data():
    try:
        # Fetch data
        y9c_df = fetch_paginated_data('y9c_full')
        mdrm_df = fetch_paginated_data('mdrm_mapping')

        # Process y9c data
        y9c_df = y9c_df.rename(columns={
            'rssd_id': 'RSSD ID',
            'report_period': 'Report Date'
        })
        
        # JSON parsing with error handling
        if not y9c_df.empty and 'data' in y9c_df.columns:
            y9c_df['metrics'] = y9c_df['data'].apply(
                lambda x: json.loads(x.replace('""', '"').strip('"')) if pd.notna(x) else {}
            )
            metrics_df = pd.json_normalize(y9c_df['metrics'])
            y9c_df = pd.concat([y9c_df.drop(['data', 'metrics'], axis=1), metrics_df], axis=1)
        else:
            st.warning("No data found in y9c_full table")
            return pd.DataFrame(), pd.DataFrame()

        # Create composite keys
        mdrm_df['composite_key'] = mdrm_df['mnemonic'].astype(str) + mdrm_df['item_code'].astype(str)
        y9c_df['composite_key'] = y9c_df['bhck2170'].astype(str)  # Example key

        # Merge dataframes with proper closure
        merged_df = pd.merge(
            y9c_df,
            mdrm_df,
            on='composite_key',
            how='left',
            suffixes=('', '_mdrm')
        )  # Closing parenthesis added here

        # Date handling
        merged_df['Report Date'] = pd.to_datetime(merged_df['Report Date'], errors='coerce')
        merged_df = merged_df.dropna(subset=['Report Date'])
        
        return merged_df, merged_df

    except Exception as e:
        st.error(f"Data Loading Error: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()

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
