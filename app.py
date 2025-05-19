import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime
from io import BytesIO

# Initialize Supabase Client with error handling
@st.cache_resource
def init_supabase():
    try:
        client = create_client(
            st.secrets.SUPABASE_URL,
            st.secrets.SUPABASE_KEY
        )
        return client
    except Exception as e:
        st.error(f"🔥 Database Connection Error: {str(e)}")
        return None

# Enhanced data loader with dynamic MDRM mapping
@st.cache_data(ttl=3600, show_spinner="Loading regulatory data...")
def load_data(reporting_form=None):
    supabase = init_supabase()
    if not supabase:
        return pd.DataFrame(), pd.DataFrame()

    try:
        # Build dynamic query with table join
        query = supabase.table('y9c_full') \
            .select('''
                rssd_id,
                report_date,
                item_value,
                mnemonic,
                item_code,
                mdrm_mapping(
                    item_name,
                    description,
                    start_date,
                    end_date,
                    reporting_form
                )
            ''') \
            .lte('report_date', 'mdrm_mapping(end_date)') \
            .gte('report_date', 'mdrm_mapping(start_date)')

        if reporting_form:
            query = query.eq('mdrm_mapping.reporting_form', reporting_form)

        response = query.execute()
        data = response.data

        # Process and validate data
        processed = []
        for row in data:
            try:
                processed.append({
                    'rssd_id': row['rssd_id'],
                    'report_date': pd.to_datetime(row['report_date']),
                    'item_value': float(row['item_value']),
                    'item_name': row['mdrm_mapping']['item_name'],
                    'description': row['mdrm_mapping']['description'],
                    'reporting_form': row['mdrm_mapping']['reporting_form']
                })
            except (KeyError, ValueError) as e:
                st.warning(f"Skipping invalid row: {str(e)}")
                continue

        if not processed:
            return pd.DataFrame(), pd.DataFrame()

        df = pd.DataFrame(processed)
        
        # Pivot to wide format for analysis
        pivot_df = df.pivot_table(
            index=['rssd_id', 'report_date'],
            columns='item_name',
            values='item_value',
            aggfunc='first'
        ).reset_index()

        return df, pivot_df

    except Exception as e:
        st.error(f"🚨 Data Loading Failed: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()

# Smart formatting based on metric type
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

# Main application
def main():
    # Configure page
    st.set_page_config(
        page_title="Regulatory Analytics Dashboard",
        layout="wide",
        page_icon="📊",
        initial_sidebar_state="expanded"
    )

    # Custom styling
    st.markdown("""
    <style>
        .metric-label {
            font-size: 1rem !important;
            color: #666 !important;
        }
        .stSelectbox [data-baseweb=select] {
            min-width: 240px;
        }
    </style>
    """, unsafe_allow_html=True)

    st.title("FR Y-9C Regulatory Analytics Dashboard")
    st.caption("Dynamic dashboard powered by Supabase regulatory data")

    # Load data
    raw_df, analysis_df = load_data()

    # Sidebar controls
    with st.sidebar:
        st.header("🔍 Filters")
        
        # Date range
        min_date = analysis_df['report_date'].min().date()
        max_date = analysis_df['report_date'].max().date()
        date_range = st.date_input(
            "Reporting Period",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date
        )

        # Institution selector
        institutions = st.multiselect(
            "Select Institutions",
            options=analysis_df['rssd_id'].unique(),
            default=analysis_df['rssd_id'].unique()[:3]
        )

        # Metric selection
        available_metrics = [col for col in analysis_df.columns 
                           if col not in ['rssd_id', 'report_date']]
        selected_metrics = st.multiselect(
            "Key Metrics",
            options=available_metrics,
            default=available_metrics[:3]
        )

        # Reporting form filter
        reporting_forms = st.multiselect(
            "Reporting Forms",
            options=raw_df['reporting_form'].unique(),
            default=['FFIEC 101']
        )

    # Filter data based on selections
    filtered_df = analysis_df[
        (analysis_df['report_date'].between(*date_range)) &
        (analysis_df['rssd_id'].isin(institutions))
    ]
    
    # Filter by reporting forms using raw data
    if reporting_forms:
        form_filtered_items = raw_df[
            raw_df['reporting_form'].isin(reporting_forms)
        ]['item_name'].unique()
        filtered_df = filtered_df[['rssd_id', 'report_date'] + 
                              list(form_filtered_items)]

    # KPI Cards
    st.header("📈 Key Performance Indicators")
    if not filtered_df.empty:
        latest_date = filtered_df['report_date'].max()
        latest_data = filtered_df[filtered_df['report_date'] == latest_date]
        
        cols = st.columns(len(selected_metrics))
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

    # Main visualization tabs
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
                title="Metric Trends Over Time",
                labels={'value': 'Amount', 'report_date': 'Date'}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Select metrics to view trends")

    with tab2:
        st.subheader("Peer Group Analysis")
        if not filtered_df.empty:
            comp_date = st.selectbox(
                "Comparison Date",
                filtered_df['report_date'].unique()
            )
            
            peer_df = filtered_df[filtered_df['report_date'] == comp_date]
            if not peer_df.empty:
                fig = px.box(
                    peer_df.melt(id_vars=['rssd_id'], 
                                value_vars=selected_metrics),
                    x='variable',
                    y='value',
                    title="Peer Institution Distribution"
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available for comparison")

    with tab3:
        st.subheader("Data Explorer")
        if not filtered_df.empty:
            # Show raw data with formatting
            st.data_editor(
                filtered_df,
                column_config={
                    "report_date": "Date",
                    "rssd_id": "Institution ID",
                },
                use_container_width=True,
                hide_index=True
            )

            # Export functionality
            st.download_button(
                label="📥 Export to CSV",
                data=filtered_df.to_csv(index=False).encode(),
                file_name="regulatory_data.csv",
                mime="text/csv"
            )
        else:
            st.info("No data to display")

if __name__ == "__main__":
    main()
