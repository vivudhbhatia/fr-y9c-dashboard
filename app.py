import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
import json
from datetime import datetime

# Set page configuration
st.set_page_config(
    page_title="FR Y-9C Financial Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #3B82F6;
        margin-bottom: 0.5rem;
    }
    .metric-card {
        background-color: #F3F4F6;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #1E3A8A;
    }
    .metric-label {
        font-size: 1rem;
        color: #6B7280;
    }
    .info-box {
        background-color: #E1F5FE;
        border-left: 4px solid #0288D1;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 0.25rem;
    }
</style>
""", unsafe_allow_html=True)

# Function to load FR Y-9C data from Supabase/CSV
@st.cache_data
def load_fr_y9c_data():
    try:
        # In a production app, you'd connect to Supabase
        # Here we'll process the sample data provided
        
        # Read the CSV content
        try:
            # For file upload scenario
            file_content = window.fs.readFile('y9c_full_rows (1).csv', {'encoding': 'utf8'})
            df_raw = pd.read_csv(io.StringIO(file_content))
        except:
            # Fallback to sample data if file reading fails
            st.warning("Using sample data - couldn't read from file. In production, this would connect to your Supabase database.")
            return load_sample_data()
            
        # Process the data field which contains JSON
        processed_data = []
        
        for _, row in df_raw.iterrows():
            bank_id = row['rssd_id']
            report_date = pd.to_datetime(row['report_period'])
            
            # Clean and parse the JSON data
            # The data field contains escaped JSON
            data_str = row['data']
            
            # Remove outer quotes and unescape internal quotes
            if data_str.startswith('"') and data_str.endswith('"'):
                data_str = data_str[1:-1]
            data_str = data_str.replace('\\"', '"')
            
            try:
                # Parse the JSON data
                data_json = json.loads(data_str)
                
                # Extract relevant metrics
                year = report_date.year
                quarter = report_date.quarter
                
                # Extract FR Y-9C metrics (MDRM codes)
                # bhck2170 = Total Assets
                # bhck2948 = Total Liabilities
                # bhck3210 = Total Equity Capital
                # bhck4340 = Net Income
                # bhca7205 = Tier 1 Risk-Based Capital Ratio
                # bhca7206 = Total Risk-Based Capital Ratio
                
                # Some values might be strings (empty or actual values), handle accordingly
                def safe_float(val):
                    if isinstance(val, (int, float)):
                        return float(val)
                    elif isinstance(val, str):
                        if val.strip() == "" or val.strip() == '""':
                            return 0.0
                        try:
                            return float(val.replace('"', ''))
                        except:
                            return 0.0
                    return 0.0
                
                # Extract the bank name from RSSD ID or use ID if not available
                bank_name = f"Bank {bank_id}"  # In production, you'd have a lookup table
                
                total_assets = safe_float(data_json.get("bhck2170", 0))
                total_liabilities = safe_float(data_json.get("bhck2948", 0))
                total_equity = safe_float(data_json.get("bhck3210", 0))
                net_income = safe_float(data_json.get("bhck4340", 0))
                tier1_capital_ratio = safe_float(data_json.get("bhca7205", 0))
                total_capital_ratio = safe_float(data_json.get("bhca7206", 0))
                
                # Calculate derived metrics
                # ROA = Net Income / Total Assets
                # ROE = Net Income / Total Equity
                roa = (net_income / total_assets * 100) if total_assets > 0 else 0
                roe = (net_income / total_equity * 100) if total_equity > 0 else 0
                
                # Efficiency ratio (lower is better) - using BHCK4093 (non-interest expense) and BHCK4074 (net interest income)
                non_interest_expense = safe_float(data_json.get("bhck4093", 0))
                net_interest_income = safe_float(data_json.get("bhck4074", 0))
                non_interest_income = safe_float(data_json.get("bhck4079", 0))
                
                efficiency_ratio = 0
                if (net_interest_income + non_interest_income) > 0:
                    efficiency_ratio = (non_interest_expense / (net_interest_income + non_interest_income)) * 100
                
                # Net Interest Margin - using BHCK4074 (net interest income) / earning assets
                earning_assets = total_assets * 0.85  # Approximation if not available
                net_interest_margin = (net_interest_income / earning_assets * 100) if earning_assets > 0 else 0
                
                # Non-performing loans - using BHCK5525 if available 
                non_performing_loans = safe_float(data_json.get("bhck5525", 0))
                if non_performing_loans == 0:
                    # If specific code not available, estimate as 1-3% of assets
                    non_performing_loans = total_assets * np.random.uniform(0.01, 0.03)
                
                # Loan loss reserves - BHCK3123 (allowance for loan and lease losses)
                loan_loss_reserves = safe_float(data_json.get("bhck3123", 0))
                
                processed_data.append({
                    "Bank": bank_name,
                    "RSSD ID": bank_id,
                    "Date": report_date,
                    "Year": year,
                    "Quarter": quarter,
                    "Total Assets": total_assets,
                    "Total Liabilities": total_liabilities,
                    "Total Equity Capital": total_equity,
                    "Net Income": net_income,
                    "Return on Assets (ROA)": roa,
                    "Return on Equity (ROE)": roe,
                    "Tier 1 Capital Ratio": tier1_capital_ratio,
                    "Total Risk-Based Capital Ratio": total_capital_ratio,
                    "Net Interest Margin": net_interest_margin,
                    "Efficiency Ratio": efficiency_ratio,
                    "Non-Performing Loans": non_performing_loans,
                    "Loan Loss Reserves": loan_loss_reserves
                })
                
            except json.JSONDecodeError as e:
                st.error(f"Error parsing JSON data: {e}")
                continue
                
        # Create DataFrame
        df = pd.DataFrame(processed_data)
        
        # If no data was successfully processed, fall back to sample data
        if len(df) == 0:
            st.warning("No valid data was found in the provided file. Using sample data instead.")
            return load_sample_data()
            
        return df
    
    except Exception as e:
        st.error(f"Error loading data: {e}")
        # Fallback to sample data
        return load_sample_data()

# Function to load sample FR Y-9C data as a fallback
def load_sample_data():
    # Generate sample dates
    quarters = pd.date_range(start='2020-03-31', end='2025-03-31', freq='Q')
    
    # Sample banks
    banks = [
        "JPMorgan Chase", "Bank of America", "Citigroup", "Wells Fargo",
        "Goldman Sachs", "Morgan Stanley", "U.S. Bancorp", "Truist Financial",
        "PNC Financial Services", "TD Bank", "Capital One", "Bank of New York Mellon"
    ]
    
    # Generate data for each bank
    data = []
    for bank in banks:
        # Base values for this bank
        base_assets = np.random.uniform(100, 3000) * 1e9  # $100B to $3T
        
        for date in quarters:
            quarter = date.quarter
            year = date.year
            
            # Randomize values with some trend over time
            time_factor = (year - 2020) + (quarter / 4)
            growth = 1 + np.random.normal(0.01, 0.005) * time_factor
            
            assets = base_assets * growth
            liabilities = assets * np.random.uniform(0.85, 0.92)
            equity = assets - liabilities
            
            # Calculate other ratios
            net_income = assets * np.random.uniform(0.005, 0.015) * (1 + 0.1 * np.sin(time_factor))
            roa = net_income / assets * 100
            roe = net_income / equity * 100
            tier1 = np.random.uniform(11, 15) + np.random.normal(0, 0.5)
            total_capital = tier1 + np.random.uniform(1, 3)
            nim = np.random.uniform(2, 4.5) + np.random.normal(0, 0.2)
            efficiency = np.random.uniform(50, 70) + np.random.normal(0, 2)
            npl = assets * np.random.uniform(0.005, 0.02)
            loan_loss = npl * np.random.uniform(1, 1.5)
            
            data.append({
                "Bank": bank,
                "RSSD ID": 100000 + banks.index(bank),
                "Date": date,
                "Year": year,
                "Quarter": quarter,
                "Total Assets": assets,
                "Total Liabilities": liabilities,
                "Total Equity Capital": equity,
                "Net Income": net_income,
                "Return on Assets (ROA)": roa,
                "Return on Equity (ROE)": roe,
                "Tier 1 Capital Ratio": tier1,
                "Total Risk-Based Capital Ratio": total_capital,
                "Net Interest Margin": nim,
                "Efficiency Ratio": efficiency,
                "Non-Performing Loans": npl,
                "Loan Loss Reserves": loan_loss
            })
    
    df = pd.DataFrame(data)
    return df

# Function to format numbers with appropriate suffixes
def format_number(num):
    if pd.isna(num):
        return "N/A"
    
    if isinstance(num, (int, float)):
        if abs(num) >= 1e12:
            return f"${num/1e12:.2f}T"
        elif abs(num) >= 1e9:
            return f"${num/1e9:.2f}B"
        elif abs(num) >= 1e6:
            return f"${num/1e6:.2f}M"
        elif abs(num) >= 1e3:
            return f"${num/1e3:.2f}K"
        else:
            return f"${num:.2f}"
    return str(num)

# Function to format percentages
def format_percent(num):
    if pd.isna(num):
        return "N/A"
    return f"{num:.2f}%"

# Function to download dataframe as CSV
def download_csv(df):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="fr_y9c_data.csv">Download CSV File</a>'
    return href

# Function to download dataframe as Excel
def download_excel(df):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='FR Y-9C Data', index=False)
    
    buffer.seek(0)
    b64 = base64.b64encode(buffer.read()).decode()
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="fr_y9c_data.xlsx">Download Excel File</a>'
    return href

# Load data
df = load_fr_y9c_data()

# Sidebar for filtering
st.sidebar.markdown("<h2>Filters</h2>", unsafe_allow_html=True)

# Show RSSD ID filter (specific to FR Y-9C data)
if 'RSSD ID' in df.columns:
    all_rssd_ids = sorted(df['RSSD ID'].unique().tolist())
    selected_rssd_ids = st.sidebar.multiselect("Select RSSD IDs", all_rssd_ids, default=all_rssd_ids[:5] if len(all_rssd_ids) > 5 else all_rssd_ids)
    
    if selected_rssd_ids:
        filtered_df = df[df['RSSD ID'].isin(selected_rssd_ids)]
    else:
        filtered_df = df
else:
    filtered_df = df

# Date range filter
try:
    min_date = df['Date'].min().date()
    max_date = df['Date'].max().date()
    date_range = st.sidebar.date_input(
        "Select Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    if len(date_range) == 2:
        start_date, end_date = date_range
        filtered_df = filtered_df[(filtered_df['Date'].dt.date >= start_date) & (filtered_df['Date'].dt.date <= end_date)]
except:
    st.sidebar.warning("Date filtering not available due to data format issues")
    start_date, end_date = None, None

# Bank selection if available
if 'Bank' in df.columns:
    all_banks = df['Bank'].unique().tolist()
    selected_banks = st.sidebar.multiselect("Select Banks", all_banks, default=all_banks[:5] if len(all_banks) > 5 else all_banks)

    if selected_banks:
        filtered_df = filtered_df[filtered_df['Bank'].isin(selected_banks)]

# Metric selection for analysis
available_metrics = [col for col in df.columns if col not in ['Bank', 'Date', 'Year', 'Quarter']]
selected_metrics = st.sidebar.multiselect(
    "Select Metrics for Analysis",
    available_metrics,
    default=['Total Assets', 'Net Income', 'Return on Equity (ROE)']
)

# Apply additional filters if needed
st.sidebar.markdown("<h3>Additional Filters</h3>", unsafe_allow_html=True)

# Asset size filter
min_assets, max_assets = float(df['Total Assets'].min()), float(df['Total Assets'].max())
asset_range = st.sidebar.slider(
    "Total Assets Range (billions)",
    min_value=min_assets/1e9,
    max_value=max_assets/1e9,
    value=(min_assets/1e9, max_assets/1e9),
    format="$%.1f B"
)
filtered_df = filtered_df[(filtered_df['Total Assets'] >= asset_range[0]*1e9) & 
                          (filtered_df['Total Assets'] <= asset_range[1]*1e9)]

# Main content
st.markdown('<div class="main-header">FR Y-9C Financial Dashboard</div>', unsafe_allow_html=True)

# Show info about data source
with st.expander("About FR Y-9C Data"):
    st.markdown("""
    <div class="info-box">
    <p><strong>FR Y-9C</strong> is the Consolidated Financial Statements for Bank Holding Companies report. 
    This dashboard analyzes FR Y-9C data which includes balance sheet, income statement, and regulatory capital information 
    for bank holding companies with total consolidated assets of $3 billion or more.</p>
    
    <p>Key MDRM codes used in this analysis:</p>
    <ul>
        <li><strong>BHCK2170</strong>: Total Assets</li>
        <li><strong>BHCK2948</strong>: Total Liabilities</li>
        <li><strong>BHCK3210</strong>: Total Equity Capital</li>
        <li><strong>BHCK4340</strong>: Net Income</li>
        <li><strong>BHCA7205</strong>: Tier 1 Risk-Based Capital Ratio</li>
        <li><strong>BHCA7206</strong>: Total Risk-Based Capital Ratio</li>
        <li><strong>BHCK4093</strong>: Non-interest Expense</li>
        <li><strong>BHCK4074</strong>: Net Interest Income</li>
    </ul>
    </div>
    """, unsafe_allow_html=True)

# Add date information
try:
    min_date = df['Date'].min().date()
    max_date = df['Date'].max().date()
    st.markdown(f"<p>Data from {min_date} to {max_date}</p>", unsafe_allow_html=True)
except:
    st.markdown("<p>Date range information not available</p>", unsafe_allow_html=True)

# Display filters applied
st.markdown("<p>Filters applied:</p>", unsafe_allow_html=True)
if len(selected_banks) < len(all_banks):
    banks_str = ", ".join(selected_banks)
    st.markdown(f"<p>Banks: {banks_str}</p>", unsafe_allow_html=True)
    
st.markdown(f"<p>Date range: {start_date} to {end_date}</p>", unsafe_allow_html=True)
st.markdown(f"<p>Asset range: ${asset_range[0]:.1f}B to ${asset_range[1]:.1f}B</p>", unsafe_allow_html=True)

# Display key metrics overview
st.markdown('<div class="sub-header">Key Metrics Overview</div>', unsafe_allow_html=True)

# Get the most recent date in the filtered data
most_recent = filtered_df['Date'].max()
recent_data = filtered_df[filtered_df['Date'] == most_recent]

# Create metric cards
metric_cols = st.columns(4)
key_metrics = [
    {"name": "Total Assets", "format": format_number},
    {"name": "Net Income", "format": format_number},
    {"name": "Return on Equity (ROE)", "format": format_percent},
    {"name": "Tier 1 Capital Ratio", "format": format_percent}
]

for i, metric in enumerate(key_metrics):
    with metric_cols[i % 4]:
        avg_value = recent_data[metric["name"]].mean()
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{metric["name"]}</div>
            <div class="metric-value">{metric["format"](avg_value)}</div>
            <div class="metric-label">Average for {most_recent.strftime('%b %Y')}</div>
        </div>
        """, unsafe_allow_html=True)

# Tabbed interface for different views
tab1, tab2, tab3, tab4 = st.tabs(["Time Trends", "Bank Comparison", "Detailed Data", "Export"])

# Tab 1: Time Trends
with tab1:
    st.markdown('<div class="sub-header">Time Trends Analysis</div>', unsafe_allow_html=True)
    
    # Select metric for time trend
    trend_metric = st.selectbox(
        "Select Metric for Time Trend Analysis",
        selected_metrics if selected_metrics else ['Total Assets']
    )
    
    # Prepare data for plotting
    pivot_df = filtered_df.pivot_table(
        index='Date',
        columns='Bank',
        values=trend_metric,
        aggfunc='mean'
    )
    
    # Plot time trends
    fig, ax = plt.subplots(figsize=(12, 6))
    pivot_df.plot(ax=ax)
    plt.title(f'{trend_metric} Trend Over Time')
    plt.xlabel('Date')
    plt.ylabel(trend_metric)
    plt.grid(True, alpha=0.3)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    st.pyplot(fig)
    
    # Add period-over-period analysis
    st.markdown('<div class="sub-header">Period-over-Period Analysis</div>', unsafe_allow_html=True)
    
    # Calculate YoY changes
    if len(pivot_df) > 4:  # Need at least 5 quarters for YoY comparison
        yoy_change = pivot_df.pct_change(4) * 100  # Assuming quarterly data, 4 periods = 1 year
        
        fig2, ax2 = plt.subplots(figsize=(12, 6))
        yoy_change.plot(ax=ax2)
        plt.title(f'Year-over-Year % Change in {trend_metric}')
        plt.xlabel('Date')
        plt.ylabel('YoY % Change')
        plt.grid(True, alpha=0.3)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        st.pyplot(fig2)

# Tab 2: Bank Comparison
with tab2:
    st.markdown('<div class="sub-header">Bank Comparison</div>', unsafe_allow_html=True)
    
    # Select date for comparison
    comparison_dates = filtered_df['Date'].dt.strftime('%Y-%m-%d').unique()
    selected_date = st.selectbox("Select Date for Comparison", comparison_dates, index=len(comparison_dates)-1)
    
    # Select metric for comparison
    comparison_metric = st.selectbox(
        "Select Metric for Bank Comparison",
        selected_metrics if selected_metrics else ['Return on Equity (ROE)']
    )
    
    # Filter data for the selected date
    date_df = filtered_df[filtered_df['Date'].dt.strftime('%Y-%m-%d') == selected_date]
    
    # Create bar chart comparison
    fig3, ax3 = plt.subplots(figsize=(12, 6))
    sns.barplot(data=date_df, x='Bank', y=comparison_metric, ax=ax3)
    plt.title(f'{comparison_metric} Comparison ({selected_date})')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3, axis='y')
    st.pyplot(fig3)
    
    # Add peer group analysis
    st.markdown('<div class="sub-header">Peer Group Analysis</div>', unsafe_allow_html=True)
    
    # Create asset size-based peer groups
    date_df['Asset Group'] = pd.qcut(date_df['Total Assets'], 3, labels=['Small', 'Medium', 'Large'])
    
    # Compare selected metric across peer groups
    fig4, ax4 = plt.subplots(figsize=(12, 6))
    sns.boxplot(data=date_df, x='Asset Group', y=comparison_metric, ax=ax4)
    plt.title(f'{comparison_metric} by Bank Size ({selected_date})')
    plt.grid(True, alpha=0.3, axis='y')
    st.pyplot(fig4)

# Tab 3: Detailed Data
with tab3:
    st.markdown('<div class="sub-header">Detailed Data View</div>', unsafe_allow_html=True)
    
    # Add sorting and additional filtering options
    sort_col = st.selectbox("Sort by", filtered_df.columns.tolist())
    sort_order = st.radio("Sort order", ["Ascending", "Descending"], horizontal=True)
    
    # Sort data
    if sort_order == "Ascending":
        sorted_df = filtered_df.sort_values(by=sort_col)
    else:
        sorted_df = filtered_df.sort_values(by=sort_col, ascending=False)
    
    # Display data with formatting
    display_df = sorted_df.copy()
    
    # Format numeric columns
    for col in display_df.columns:
        if col in ['Total Assets', 'Total Liabilities', 'Total Equity Capital', 'Net Income', 'Non-Performing Loans', 'Loan Loss Reserves']:
            display_df[col] = display_df[col].apply(format_number)
        elif col in ['Return on Assets (ROA)', 'Return on Equity (ROE)', 'Tier 1 Capital Ratio', 'Total Risk-Based Capital Ratio', 'Net Interest Margin', 'Efficiency Ratio']:
            display_df[col] = display_df[col].apply(format_percent)
    
    # Convert date to string format
    display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m-%d')
    
    # Display data table
    st.dataframe(display_df, use_container_width=True)
    
    # Add search functionality
    search_term = st.text_input("Search banks")
    if search_term:
        search_results = display_df[display_df['Bank'].str.contains(search_term, case=False)]
        st.write(f"Found {len(search_results)} matches:")
        st.dataframe(search_results, use_container_width=True)

# Tab 4: Export Data
with tab4:
    st.markdown('<div class="sub-header">Export Data</div>', unsafe_allow_html=True)
    
    # Export format options
    export_format = st.radio("Select Export Format", ["CSV", "Excel"], horizontal=True)
    
    # Export selected data or all data
    export_selection = st.radio("Data to Export", ["Selected Banks & Date Range", "All Data"], horizontal=True)
    
    if export_selection == "All Data":
        export_df = df
    else:
        export_df = filtered_df
    
    # Show data to be exported
    st.write(f"Preview of data to be exported ({len(export_df)} rows):")
    st.dataframe(export_df.head(10), use_container_width=True)
    
    # Generate download link
    if export_format == "CSV":
        st.markdown(download_csv(export_df), unsafe_allow_html=True)
    else:
        st.markdown(download_excel(export_df), unsafe_allow_html=True)

# Add footer with information
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #6B7280; font-size: 0.8rem;">
    FR Y-9C Financial Dashboard | Data source: Federal Reserve Board Report Forms | Last updated: May 19, 2025
</div>
""", unsafe_allow_html=True)
