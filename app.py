import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime
from io import BytesIO
import json

# Initialize Supabase Client
@st.cache_resource
def init_supabase():
    return create_client(st.secrets.SUPABASE_URL, st.secrets.SUPABASE_KEY)

# Enhanced data loader with proper column handling
@st.cache_data(ttl=3600, show_spinner="Loading regulatory data...")
def load_data():
    supabase = init_supabase()
    
    try:
        # Load data from both tables
        y9c_response = supabase.table('y9c_full').select('*').execute()
        mdrm_response = supabase.table('mdrm_mapping').select('*').execute()
        
        y9c_data = y9c_response.data
        mdrm_data = mdrm_response.data

        # Create DataFrames with proper column names
        y9c_df = pd.DataFrame(y9c_data)
        mdrm_df = pd.DataFrame(mdrm_data)

        # Process y9c data
        y9c_df = y9c_df.rename(columns={
            'rssd_id': 'RSSD ID',
            'report_period': 'Report Date'
        })
        
        # Extract metrics from JSON data
        def parse_json_data(row):
            try:
                data_str = row['data'].replace('""', '"').strip('"')
                return json.loads(data_str)
            except Exception as e:
                st.error(f"Error parsing JSON: {str(e)}")
                return {}
            
        y9c_df['metrics'] = y9c_df.apply(parse_json_data, axis=1)
        metrics_df = pd.json_normalize(y9c_df['metrics'])
        y9c_df = pd.concat([y9c_df.drop(['data', 'metrics'], axis=1), metrics_df], axis=1)

        # Create composite keys
        y9c_df['composite_key'] = y9c_df['bhck2170'].astype(str)  # Using total assets as key example
        mdrm_df['composite_key'] = mdrm_df['mnemonic'] + mdrm_df['item_code'].astype(str)

        # Merge datasets
        merged_df = pd.merge(
            y9c_df,
            mdrm_df,
            on='composite_key',
            how='left',
            suffixes=('', '_mdrm'))
            
        # Convert dates and filter valid mappings
        merged_df['Report Date'] = pd.to_datetime(merged_df['Report Date'])
        merged_df['start_date'] = pd.to_datetime(merged_df['start_date'])
        merged_df['end_date'] = pd.to_datetime(merged_df['end_date'])
        
        valid_mappings = merged_df[
            (merged_df['Report Date'] >= merged_df['start_date']) &
            (merged_df['Report Date'] <= merged_df['end_date'])
        ]

        # Pivot for analysis
        pivot_df = valid_mappings.pivot_table(
            index=['RSSD ID', 'Report Date'],
            columns='item_name',
            values='item_value',
            aggfunc='first'
        ).reset_index()

        return valid_mappings, pivot_df

    except Exception as e:
        st.error(f"Data Loading Error: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()

# Smart formatting function
def format_metric(value, metric_name):
    if pd.isna(value):
        return "N/A"
        
    if any(kw in metric_name.lower() for kw in ['ratio', '%', 'rate']):
        return f"{value:.2f}%"
    if abs(value) >= 1e9:
        return f"${value/1e9:.2f}B"
    if abs(value) >= 1e6:
        return f"${value/1e6:.2f}M"
    return f"${value:,.2f}"

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

    # Sidebar controls
    with st.sidebar:
        st.header("🔍 Filters")
        
        # Get distinct reporting periods
        if not analysis_df.empty:
            dates = analysis_df['Report Date'].dt.date.unique()
            date_options = sorted(dates, reverse=True)
        else:
            date_options = []

        # Date selection
        selected_dates = st.multiselect(
            "Reporting Period",
            options=date_options,
            default=date_options[:1] if date_options else []
        )

        # Institution selector
        institutions = st.multiselect(
            "Select Institutions",
            options=analysis_df['RSSD ID'].unique() if not analysis_df.empty else [],
            default=analysis_df['RSSD ID'].unique()[:3] if not analysis_df.empty else []
        )

        # Metric selection
        available_metrics = [col for col in analysis_df.columns 
                           if col not in ['RSSD ID', 'Report Date']]
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

    # KPI Cards
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
                    help=raw_df[raw_df['item_name'] == metric]
                         ['description'].iloc[0] if not raw_df.empty else ""
                )
    else:
        st.warning("No data available for selected filters")

    # Rest of the visualization tabs remains the same...

if __name__ == "__main__":
    main()
