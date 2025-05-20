# chatbot.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client, ClientOptions
import openai
import backoff
import json
from datetime import datetime

# Configuration
ESSENTIAL_COLS = ['bhck2170', 'bhck2948', 'bhck3210']  # JSON keys to extract
CACHE_TTL = 3600  # 1 hour cache
AI_MODEL = "gpt-4o"  # Updated to GPT-4o model

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def init_supabase():
    """Initialize Supabase client with optimized settings"""
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

@st.cache_data(ttl=CACHE_TTL, show_spinner="📊 Loading financial data...")
@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def fetch_financial_data():
    """Fetch and process JSON data from Supabase"""
    try:
        response = supabase.table('y9c_full') \
                   .select('data,report_period') \
                   .order('report_period', desc=True) \
                   .limit(1000) \
                   .execute()

        processed_data = []
        for row in response.data:
            try:
                # Clean and parse JSON data
                json_data = row['data'].replace('""', '"').replace('\\"', '"')
                parsed = json.loads(json_data)
                
                # Extract essential metrics
                record = {
                    'report_period': pd.to_datetime(row['report_period']),
                }
                for col in ESSENTIAL_COLS:
                    record[col] = float(parsed.get(col, 0)) if parsed.get(col) not in [None, ""] else 0.0
                
                processed_data.append(record)
            except Exception as e:
                st.error(f"⚠️ Error processing row: {str(e)}")
                continue

        df = pd.DataFrame(processed_data)
        return df.sort_values('report_period', ascending=False).drop_duplicates()
    except Exception as e:
        st.error(f"📊 Data Processing Error: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=CACHE_TTL)
def get_metric_mappings():
    """Fetch metric metadata with error handling"""
    try:
        response = supabase.table('mdrm_mapping') \
                   .select('item_code,item_name') \
                   .execute()
        return {item['item_code']: item['item_name'] for item in response.data}
    except Exception as e:
        st.error(f"📖 Metadata Error: {str(e)}")
        return {}

def create_analysis_context(df, mappings):
    """Create structured analysis context"""
    if df.empty:
        return {}
    
    context = {
        'report_period': df['report_period'].max().strftime('%Y-%m-%d'),
        'metrics': {},
        'available_codes': ESSENTIAL_COLS
    }
    
    for col in ESSENTIAL_COLS:
        context['metrics'][col] = {
            'name': mappings.get(col, col),
            'current': df[col].iloc[0] if not df.empty else 0,
            'history': {
                'min': df[col].min(),
                'max': df[col].max(),
                'mean': df[col].mean()
            }
        }
    
    return context

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_ai_insight(query, context):
    """Generate insights using GPT-4o"""
    if not context or not context.get('metrics'):
        return ""
    
    prompt = f"""Analyze banking metrics with this context:
Latest Report Date: {context['report_period']}
Available Metrics:
{'\n'.join([f"- {code}: {info['name']} (Current: {info['current']:,.0f})" for code, info in context['metrics'].items()])}

User Query: {query}

Respond STRICTLY in this format:
ANALYSIS: [comprehensive analysis with numbers]
VISUALIZATION: [line|bar|scatter|none]
METRICS: [comma-separated metric codes]
"""
    
    try:
        response = openai.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "You are a senior banking analyst. Use only provided metrics and numbers."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500,
            timeout=30
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"🤖 AI Analysis Error: {str(e)}")
        return ""

def create_visualization(df, viz_type, metrics):
    """Create interactive visualizations"""
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
        
        plt.xticks(rotation=45)
        plt.grid(True)
        plt.tight_layout()
        return fig
    except Exception as e:
        st.error(f"📈 Visualization Error: {str(e)}")
        return None

def main():
    st.set_page_config(page_title="Banking Analytics", layout="wide")
    st.title("🏦 Regulatory Banking Dashboard")
    
    # Load data
    df = fetch_financial_data()
    mappings = get_metric_mappings()
    context = create_analysis_context(df, mappings)
    
    if df.empty:
        st.warning("⚠️ No financial data available")
        return
    
    # Sidebar controls
    with st.sidebar:
        st.header("Data Overview")
        st.metric("Latest Report", context['report_period'])
        st.metric("Data Points", len(df))
        
        with st.expander("📋 Metric Details"):
            for code in ESSENTIAL_COLS:
                info = context['metrics'][code]
                st.write(f"**{code}**: {info['name']}")
                cols = st.columns(2)
                cols[0].metric("Current", f"{info['current']:,.0f}")
                cols[1].metric("Historical Range", 
                              f"{info['history']['min']:,.0f} - {info['history']['max']:,.0f}")

    # Main interface
    query = st.text_input(
        "📝 Enter analysis request:",
        placeholder="E.g., Analyze assets vs liabilities trend",
        help="Try: Compare capital adequacy ratios, Show equity growth over time"
    )
    
    if query:
        with st.spinner("🔍 Analyzing with GPT-4o..."):
            response = generate_ai_insight(query, context)
        
        if response:
            # Parse response
            analysis = viz_type = metrics = None
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith('ANALYSIS:'):
                    analysis = line.replace('ANALYSIS:', '').strip()
                elif line.startswith('VISUALIZATION:'):
                    viz_type = line.replace('VISUALIZATION:', '').strip().lower()
                elif line.startswith('METRICS:'):
                    metrics = [m.strip() for m in line.replace('METRICS:', '').split(',')]
                    metrics = [m for m in metrics if m in ESSENTIAL_COLS]
            
            # Display results
            if analysis:
                st.subheader("AI Analysis")
                st.write(analysis)
                
            if viz_type and viz_type != 'none' and metrics:
                st.subheader("Data Visualization")
                fig = create_visualization(df, viz_type, metrics)
                if fig:
                    st.pyplot(fig)
                else:
                    st.warning("⚠️ Could not generate requested visualization")

if __name__ == "__main__":
    main()
