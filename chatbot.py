# app.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client, ClientOptions
import openai
import backoff
from datetime import datetime

# Constants
ESSENTIAL_COLUMNS = ['report_period', 'bhck2170', 'bhck2948', 'bhck3210']
MAX_ROWS = 3000
PAGE_SIZE = 500
CACHE_TTL = 3600  # 1 hour

# Initialize connections with retry logic
@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def init_supabase():
    try:
        client = create_client(
            st.secrets.SUPABASE_URL,
            st.secrets.SUPABASE_KEY,
            options=ClientOptions(
                postgrest_client_timeout=60,
                schema='public'
            )
        )
        # Test connection
        client.table('y9c_full').select('count', count='exact').execute()
        return client
    except Exception as e:
        st.error(f"🔥 Connection Failed: {str(e)}")
        st.stop()

supabase = init_supabase()
openai.api_key = st.secrets.OPENAI_API_KEY

@st.cache_data(ttl=CACHE_TTL, show_spinner="Loading financial data...")
@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def fetch_financial_data():
    """Fetch banking data with pagination and optimized query"""
    try:
        all_data = []
        page = 0
        
        with st.spinner("📊 Fetching data..."):
            while True:
                response = supabase.table('y9c_full') \
                    .select(','.join(ESSENTIAL_COLUMNS)) \
                    .order('report_period', desc=True) \
                    .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1) \
                    .execute()

                if not response.data or page * PAGE_SIZE >= MAX_ROWS:
                    break
                    
                all_data.extend(response.data)
                page += 1

        df = pd.DataFrame(all_data).drop_duplicates('report_period')
        df['report_period'] = pd.to_datetime(df['report_period'])
        return df.sort_values('report_period', ascending=False)
    except Exception as e:
        st.error(f"❌ Data Error: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL)
def get_metric_mappings():
    """Fetch metric mappings with caching"""
    try:
        response = supabase.table('mdrm_mapping') \
            .select('item_code, item_name') \
            .execute()
        return {item['item_code']: item['item_name'] for item in response.data}
    except Exception as e:
        st.error(f"📖 Mapping Error: {str(e)}")
        return {}

def create_data_context(df, mappings):
    """Generate analysis context with data summary"""
    if df.empty:
        return {}
    
    context = {
        'report_period': df['report_period'].max().strftime('%Y-%m-%d'),
        'metrics': {},
        'available_codes': [c for c in ESSENTIAL_COLUMNS if c != 'report_period'],
        'date_range': f"{df['report_period'].min().strftime('%Y-%m-%d')} to "
                     f"{df['report_period'].max().strftime('%Y-%m-%d')}"
    }
    
    for code in context['available_codes']:
        context['metrics'][code] = {
            'name': mappings.get(code, code),
            'current': df[code].iloc[0] if not df.empty else None,
            'history': {
                'min': df[code].min(),
                'max': df[code].max(),
                'mean': df[code].mean()
            }
        }
    
    return context

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_ai_insight(query, context):
    """Get AI analysis with strict output formatting"""
    if not context.get('metrics'):
        return ""
    
    metric_list = '\n'.join(
        [f"- {code}: {info['name']}" 
         for code, info in context['metrics'].items()]
    )
    
    prompt = f"""Analyze banking data with these metrics:
{metric_list}

User query: {query}

Respond EXACTLY in this format:
ANALYSIS: [comprehensive analysis using numbers from context]
VISUALIZATION: [line|bar|scatter|none]
METRICS: [comma-separated codes from: {context['available_codes']}]
"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a financial analyst. Use only the provided metrics."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500,
            timeout=30
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"🤖 AI Error: {str(e)}")
        return ""

def create_chart(df, chart_type, metrics):
    """Generate matplotlib visualization"""
    try:
        fig, ax = plt.subplots(figsize=(10, 4))
        df = df.sort_values('report_period')
        
        if chart_type == 'line':
            df.plot(x='report_period', y=metrics, ax=ax, marker='o')
            ax.set_title(f"{' vs '.join(metrics)} Trend")
        elif chart_type == 'bar':
            df[metrics].mean().plot(kind='bar', ax=ax)
            ax.set_title("Average Values Comparison")
        elif chart_type == 'scatter' and len(metrics) >= 2:
            df.plot.scatter(x=metrics[0], y=metrics[1], ax=ax)
            ax.set_title(f"{metrics[0]} vs {metrics[1]} Correlation")
        else:
            return None
        
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"📈 Chart Error: {str(e)}")
        return None

# Streamlit UI Configuration
st.set_page_config(
    page_title="Banking Analytics",
    page_icon="🏦",
    layout="wide"
)

# Main App Interface
def main():
    st.title("🏦 Regulatory Banking Dashboard")
    
    # Data Loading
    df = fetch_financial_data()
    mappings = get_metric_mappings()
    context = create_data_context(df, mappings)
    
    if not context:
        st.warning("⚠️ No data available")
        return
    
    # Sidebar Controls
    with st.sidebar:
        st.header("Data Overview")
        st.metric("Latest Report", context['report_period'])
        st.metric("Data Points", len(df))
        st.metric("Date Range", context['date_range'])
        
        with st.expander("🔍 Metric Details"):
            for code in context['available_codes']:
                st.write(f"**{code}**")
                st.caption(f"{context['metrics'][code]['name']}")
                st.write(f"Current: {context['metrics'][code]['current']:,.0f}")
                st.write(f"Historical Range: {context['metrics'][code]['history']['min']:,.0f} - {context['metrics'][code]['history']['max']:,.0f}")

    # Main Analysis Interface
    query = st.text_input(
        "📝 Enter analysis request:",
        placeholder="E.g., Analyze capital adequacy trends over time",
        help="Example queries: Compare assets vs liabilities, Show equity growth rate"
    )
    
    if query:
        with st.spinner("🔍 Analyzing..."):
            response = generate_ai_insight(query, context)
        
        if response:
            # Parse AI Response
            analysis = visualization = metrics = None
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith('ANALYSIS:'):
                    analysis = line.replace('ANALYSIS:', '').strip()
                elif line.startswith('VISUALIZATION:'):
                    visualization = line.replace('VISUALIZATION:', '').strip().lower()
                elif line.startswith('METRICS:'):
                    metrics = [m.strip() for m in line.replace('METRICS:', '').split(',')]
                    metrics = [m for m in metrics if m in context['available_codes']]
            
            # Display Results
            if analysis:
                st.subheader("Analysis Results")
                st.write(analysis)
                
            if visualization and visualization != 'none' and metrics:
                st.subheader("Data Visualization")
                fig = create_chart(df, visualization, metrics)
                if fig:
                    st.pyplot(fig)
                else:
                    st.warning("⚠️ Could not generate requested visualization")

if __name__ == "__main__":
    main()
