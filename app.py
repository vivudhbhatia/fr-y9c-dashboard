# ... [previous imports and supabase initialization remain unchanged] ...

# Robust data loader with detailed error reporting
@st.cache_data(ttl=3600, show_spinner="Loading regulatory data...")
def load_data():
    try:
        st.write("Starting data load...")
        
        # Fetch data
        y9c_df = fetch_paginated_data('y9c_full')
        mdrm_df = fetch_paginated_data('mdrm_mapping')
        st.write(f"Raw y9c data: {y9c_df.shape} rows")  # Fixed: Removed extra )
        st.write(f"Raw mdrm data: {mdrm_df.shape} rows")  # Fixed: Removed extra )

        # JSON parsing with detailed error handling
        if not y9c_df.empty and 'data' in y9c_df.columns:
            def safe_json_parse(x):
                try:
                    if not isinstance(x, str):
                        return {}
                    cleaned = x.strip('"').replace('\\"', '"')
                    return ast.literal_eval(cleaned)
                except Exception as e:
                    st.write(f"Failed to parse JSON: {x}")
                    st.write(f"Error: {str(e)}")
                    return {}
            
            y9c_df['metrics'] = y9c_df['data'].apply(safe_json_parse)
            metrics_df = pd.json_normalize(y9c_df['metrics'])
            st.write(f"Parsed metrics: {metrics_df.shape} columns")  # Fixed: Removed extra )
            
            y9c_df = pd.concat([y9c_df.drop(['data', 'metrics'], axis=1), metrics_df], axis=1)
            st.write(f"Merged y9c data: {y9c_df.shape} rows")  # Fixed: Removed extra )

        # ... [rest of the data processing code remains unchanged] ...

        # Merge dataframes
        merged_df = pd.merge(
            y9c_df,
            mdrm_df[mdrm_df['end_date'] == '9999-12-31'],
            on='composite_key',
            how='inner',
            suffixes=('', '_mdrm')
        )
        st.write(f"Merged dataset: {merged_df.shape} rows")  # Fixed: Removed extra )

        # Date handling
        merged_df['Report Date'] = pd.to_datetime(merged_df['report_period'], errors='coerce')
        merged_df = merged_df.dropna(subset=['Report Date'])
        st.write(f"After date filtering: {merged_df.shape} rows")  # Fixed: Removed extra )
        
        return merged_df, merged_df

      except Exception as e:
        st.error(f"Critical error in load_data: {str(e)}")
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
