import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime
from io import BytesIO

# Initialize Supabase Client
@st.cache_resource
def init_supabase():
    return create_client(st.secrets.SUPABASE_URL, st.secrets.SUPABASE_KEY)

# Enhanced data loader with composite key handling
@st.cache_data(ttl=3600, show_spinner="Loading regulatory data...")
def load_data():
    supabase = init_supabase()
    
    try:
        # Load data from both tables
        y9c_response = supabase.table('y9c_full').select('*').execute()
        mdrm_response = supabase.table('mdrm_mapping').select('*').execute()
        
        y9c_data = y9c_response.data
        mdrm_data = mdrm_response.data

        # Create DataFrames with composite keys
        y9c_df = pd.DataFrame(y9c_data)
        mdrm_df = pd.DataFrame(mdrm_data)

        # Create composite keys
        y9c_df['composite_key'] = y9c_df['mnemonic'] + y9c_df['item_code'].astype(str)
        mdrm_df['composite_key'] = mdrm_df['mnemonic'] + mdrm_df['item_code'].astype(str)

        # Merge datasets
        merged_df = pd.merge(
            y9c_df,
            mdrm_df,
            on='composite_key',
            how='left',
            suffixes=('', '_mdrm')
            
        # Convert dates and filter valid mappings
        merged_df['report_date'] = pd.to_datetime(merged_df['report_date'])
        merged_df['start_date'] = pd.to_datetime(merged_df['start_date'])
        merged_df['end_date'] = pd.to_datetime(merged_df['end_date'])
        
        valid_mappings = merged_df[
            (merged_df['report_date'] >= merged_df['start_date']) &
            (merged_df['report_date'] <= merged_df['end_date'])
        ]

        # Pivot for analysis
        pivot_df = valid_mappings.pivot_table(
            index=['rssd_id', 'report_date'],
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
        page_title="Regulatory Analytics Dashboard",
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
        
        # Date range
        min_date = analysis_df['report_date'].min().date() if not analysis_df.empty else datetime.today().date()
        max_date = analysis_df['report_date'].max().date() if not analysis_df.empty else datetime.today().date()
        date_range = st.date_input(
            "Reporting Period",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        # Institution selector
        institutions = st.multiselect(
            "Select Institutions",
            options=analysis_df['rssd_id'].unique() if not analysis_df.empty else [],
            default=analysis_df['rssd_id'].unique()[:3] if not analysis_df.empty else []
        )

        # Metric selection
        available_metrics = [col for col in analysis_df.columns 
                           if col not in ['rssd_id', 'report_date']]
        selected_metrics = st.multiselect(
            "Key Metrics",
            options=available_metrics,
            default=available_metrics[:3] if available_metrics else []
        )

    # Filter data
    filtered_df = analysis_df[
        (analysis_df['report_date'].between(*date_range)) &
        (analysis_df['rssd_id'].isin(institutions))
    ] if not analysis_df.empty else pd.DataFrame()

    # KPI Cards
    st.header("📈 Key Performance Indicators")
    if not filtered_df.empty:
        cols = st.columns(len(selected_metrics))
        latest_date = filtered_df['report_date'].max()
        latest_data = filtered_df[filtered_df['report_date'] == latest_date]
        
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

    # Visualization Tabs
    tab1, tab2, tab3 = st.tabs(["📅 Trends", "🏦 Peer Comparison", "📥 Data"])

    with tab1:
        st.subheader("Historical Trends")
        if not filtered_df.empty and selected_metrics:
            fig = px.line(
                filtered_df,
                x='report_date',
                y=selected_metrics,
                color='rssd_id',
                markers=True,
                title="Metric Trends Over Time"
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("Peer Comparison")
        if not filtered_df.empty:
            comp_date = st.selectbox(
                "Comparison Date",
                filtered_df['report_date'].unique()
            )
            peer_df = filtered_df[filtered_df['report_date'] == comp_date]
            fig = px.box(
                peer_df.melt(id_vars=['rssd_id'], value_vars=selected_metrics),
                x='variable',
                y='value',
                title="Peer Institution Distribution"
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Data Explorer")
        if not filtered_df.empty:
            st.dataframe(
                filtered_df,
                column_config={
                    "report_date": "Date",
                    "rssd_id": "Institution ID",
                },
                use_container_width=True
            )
            st.download_button(
                "📥 Export Data",
                filtered_df.to_csv(index=False).encode(),
                "regulatory_data.csv",
                "text/csv"
            )

if __name__ == "__main__":
    main()
