# app.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client, ClientOptions
import openai
import backoff
from datetime import datetime

# Configuration
ESSENTIAL_COLS = ['report_period', 'bhck2170', 'bhck2948', 'bhck3210']
MAX_ROWS = 5000
PAGE_SIZE = 500
CACHE_TTL = 3600  # 1 hour cache

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def init_supabase():
    """Initialize Supabase client with connection pooling"""
    try:
        return create_client(
            st.secrets.SUPABASE_URL,
            st.secrets.SUPABASE_KEY,
            options=ClientOptions(
                postgrest_client_timeout=60,
                schema='public',
                headers={'Content-Type': 'application/json'}
            )
        )
    except Exception as e:
        st.error(f"🔥 Connection Failed: {str(e)}")
        st.stop()

supabase = init_supabase()
openai.api_key = st.secrets.OPENAI_API_KEY

@st.cache_data(ttl=CACHE_TTL, show_spinner="Loading financial data...")
@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def fetch_financial_data():
    """Optimized data fetch with pagination and column selection"""
    try:
        all_data = []
        page = 0
        
        while len(all_data) < MAX_ROWS:
            response = supabase.table('y9c_full') \
                .select(','.join(ESSENTIAL_COLS)) \
                .order('report_period', desc=True) \
                .range(page*PAGE_SIZE, (page+1)*PAGE_SIZE-1) \
                .execute()
            
            if not response.data:
                break
                
            all_data.extend(response.data)
            page += 1

        df = pd.DataFrame(all_data)
        df['report_period'] = pd.to_datetime(df['report_period'])
        return df.drop_duplicates('report_period').sort_values('report_period', ascending=False)
    except Exception as e:
        st.error(f"📊 Data Error: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL)
def get_metric_mappings():
    """Fetch metric metadata with error handling"""
    try:
        response = supabase.table('mdrm_mapping') \
            .select('item_code, item_name') \
            .execute()
        return {item['item_code']: item['item_name'] for item in response.data}
    except Exception as e:
        st.error(f"📖 Metadata Error: {str(e)}")
        return {}

def create_analysis_prompt(query, context):
    """Structured prompt for financial analysis"""
    metric_list = '\n'.join(
        [f"- {code}: {info['name']}" 
         for code, info in context['metrics'].items()]
    )
    
    return f"""Analyze banking data with these metrics:
{metric_list}

User query: {query}

Respond EXACTLY in this format:
ANALYSIS: [text analysis using only available metrics]
VISUALIZATION: [line|bar|scatter|none]
METRICS: [comma-separated codes from: {context['available_codes']}]
"""

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_ai_insight(query, context):
    """Get AI analysis with validation"""
    if not context.get('metrics'):
        return ""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a senior banking analyst. Use only the provided metrics."},
                {"role": "user", "content": create_analysis_prompt(query, context)}
            ],
            temperature=0.3,
            max_tokens=500,
            timeout=30
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"🤖 AI Error: {str(e)}")
        return ""

def create_visualization(df, viz_type, metrics):
    """Robust visualization generator"""
    try:
        fig, ax = plt.subplots(figsize=(10, 4))
        df = df.sort_values('report_period')
        
        if viz_type == 'line':
            df.plot(x='report_period', y=metrics, ax=ax, marker='o')
            ax.set_title(f"{' vs '.join(metrics)} Trend")
        elif viz_type == 'bar':
            df[metrics].mean().plot(kind='bar', ax=ax)
            ax.set_title("Average Values Comparison")
        elif viz_type == 'scatter' and len(metrics) >= 2:
            df.plot.scatter(x=metrics[0], y=metrics[1], ax=ax)
            ax.set_title(f"{metrics[0]} vs {metrics[1]} Correlation")
        else:
            return None
        
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"📈 Visualization Error: {str(e)}")
        return None

def main():
    st.set_page_config(page_title="Banking Dashboard", layout="wide")
    st.title("🏦 Regulatory Banking Analytics")
    
    # Data loading
    df = fetch_financial_data()
    mappings = get_metric_mappings()
    
    if df.empty:
        st.warning("⚠️ No financial data available")
        return
    
    # Create analysis context
    context = {
        'report_period': df['report_period'].max().strftime('%Y-%m-%d'),
        'metrics': {},
        'available_codes': [c for c in ESSENTIAL_COLS if c != 'report_period']
    }
    
    for code in context['available_codes']:
        context['metrics'][code] = {
            'name': mappings.get(code, code),
            'current': df[code].iloc[0],
            'history': {
                'min': df[code].min(),
                'max': df[code].max(),
                'mean': df[code].mean()
            }
        }

    # Sidebar controls
    with st.sidebar:
        st.header("Data Overview")
        st.metric("Latest Report", context['report_period'])
        st.metric("Data Points", len(df))
        
        with st.expander("📋 Metric Glossary"):
            for code, info in context['metrics'].items():
                st.write(f"**{code}**")
                st.caption(info['name'])
                st.write(f"Current: {info['current']:,.0f}")
                st.write(f"Historical Range: {info['history']['min']:,.0f} - {info['history']['max']:,.0f}")

    # Main interface
    query = st.text_input(
        "📝 Enter analysis request:",
        placeholder="E.g., Analyze capital adequacy trends",
        help="Try: Compare assets vs liabilities, Show equity growth rate"
    )
    
    if query:
        with st.spinner("🔍 Analyzing..."):
            response = generate_ai_insight(query, context)
        
        if response:
            # Parse AI response
            analysis = viz_type = metrics = None
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith('ANALYSIS:'):
                    analysis = line.replace('ANALYSIS:', '').strip()
                elif line.startswith('VISUALIZATION:'):
                    viz_type = line.replace('VISUALIZATION:', '').strip().lower()
                elif line.startswith('METRICS:'):
                    metrics = [m.strip() for m in line.replace('METRICS:', '').split(',')]
                    metrics = [m for m in metrics if m in context['available_codes']]
            
            # Display results
            if analysis:
                st.subheader("Analysis")
                st.write(analysis)
                
            if viz_type and viz_type != 'none' and metrics:
                st.subheader("Visualization")
                fig = create_visualization(df, viz_type, metrics)
                if fig:
                    st.pyplot(fig)
                else:
                    st.warning("⚠️ Could not generate requested visualization")

if __name__ == "__main__":
    main()
