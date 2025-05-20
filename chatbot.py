import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client, ClientOptions  # Modified import
import openai
import traceback

# Initialize connections
def init_supabase():
    try:
        return create_client(
            st.secrets.SUPABASE_URL,
            st.secrets.SUPABASE_KEY,
            options=ClientOptions(postgrest_client_timeout=30)  # Corrected options
        )
    except Exception as e:
        st.error(f"Supabase connection failed: {str(e)}")
        st.stop()

supabase = init_supabase()
openai.api_key = st.secrets.OPENAI_API_KEY


def fetch_financial_data():
    """Fetch banking data from Supabase with error handling"""
    try:
        response = supabase.table('y9c_full')\
                    .select('*')\
                    .order('report_period', desc=True)\
                    .limit(1000)\
                    .execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Data fetch error: {str(e)}")
        return pd.DataFrame()

def get_metric_mappings():
    """Get metric code-name mappings from mdrm_mapping"""
    try:
        response = supabase.table('mdrm_mapping')\
                    .select('item_code, item_name')\
                    .execute()
        return {item['item_code']: item['item_name'] for item in response.data}
    except:
        return {}

def get_data_context(df, mappings):
    """Generate structured data context"""
    if df.empty:
        return {}
    
    latest = df.iloc[0]
    metrics = {
        code: {
            'name': mappings.get(code, code),
            'current': latest.get(code, None),
            'history': f"{len(df)} data points since {df['report_period'].min()}"
        }
        for code in df.columns if code in mappings
    }
    
    return {
        'report_period': latest['report_period'],
        'metrics': metrics,
        'available_codes': list(metrics.keys())
    }

def generate_suggestions(context):
    """Generate analysis suggestions based on available metrics"""
    if not context.get('metrics'):
        return []
    
    base_metrics = ['bhck2170', 'bhck2948', 'bhck3210']  # Assets, Liabilities, Equity
    suggestions = []
    
    # Time-based analysis
    suggestions.extend([
        f"Analyze {context['metrics'][code]['name']} trend over time" 
        for code in base_metrics if code in context['metrics']
    ])
    
    # Comparative analysis
    suggestions.append(
        f"Compare {context['metrics']['bhck2170']['name']} vs " + 
        f"{context['metrics']['bhck2948']['name']} correlation"
    )
    
    # Ratios
    if 'bhck3210' in context['metrics']:
        suggestions.extend([
            f"Calculate {context['metrics']['bhck3210']['name']} to Assets ratio",
            f"Analyze Debt-to-Equity ratio trend"
        ])
    
    return suggestions[:6]  # Return top 6 suggestions

def generate_insight(query, context):
    """Get AI analysis constrained to available data"""
    prompt = f"""Analyze banking data with these available metrics:
    { {code: info['name'] for code, info in context['metrics'].items()} }
    
    User query: {query}
    
    Respond with:
    ANALYSIS: [text analysis using only available metrics]
    VISUALIZATION: [chart type or 'none']
    METRICS: [comma-separated metric codes from available: {context['available_codes']}]
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a banking analyst using only provided metrics."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Analysis failed: {str(e)}")
        return ""

def create_visualization(df, viz_type, metrics):
    """Create visualization from specified metrics"""
    if not metrics or df.empty:
        return None
    
    try:
        fig, ax = plt.subplots(figsize=(10, 4))
        
        if viz_type == 'line':
            df.plot(x='report_period', y=metrics, ax=ax, marker='o')
            ax.set_title(f"{', '.join(metrics)} Trend")
        elif viz_type == 'bar':
            df[metrics].mean().plot(kind='bar', ax=ax)
            ax.set_title("Average Values Comparison")
        elif viz_type == 'scatter' and len(metrics) >= 2:
            df.plot.scatter(x=metrics[0], y=metrics[1], ax=ax)
            ax.set_title(f"{metrics[0]} vs {metrics[1]}")
        else:
            return None
        
        plt.xticks(rotation=45)
        plt.tight_layout()
        return fig
    except:
        return None

# Streamlit UI
st.title("🏦 Regulatory Banking Analyst")
df = fetch_financial_data()
mappings = get_metric_mappings()
context = get_data_context(df, mappings)

if context:
    st.sidebar.header("Data Overview")
    st.sidebar.write(f"Latest Report: {context['report_period']}")
    st.sidebar.write(f"Available Metrics: {len(context['metrics'])}")
    
    with st.expander("📋 Metric Glossary"):
        for code, info in context['metrics'].items():
            st.write(f"**{code}**: {info['name']}")

    st.subheader("💡 Suggested Analyses")
    suggestions = generate_suggestions(context)
    
    cols = st.columns(2)
    for i, sugg in enumerate(suggestions):
        with cols[i % 2]:
            if st.button(sugg, key=f"sugg_{i}"):
                st.session_state.query = sugg
                
    query = st.text_input("Or enter your own analysis request:",
                         value=st.session_state.get('query', ''),
                         placeholder="E.g., Show capital adequacy trend")

    if query:
        response = generate_insight(query, context)
        
        analysis = viz_type = metrics = None
        for line in response.split('\n'):
            if line.startswith('ANALYSIS:'):
                analysis = line.replace('ANALYSIS:', '').strip()
            elif line.startswith('VISUALIZATION:'):
                viz_type = line.replace('VISUALIZATION:', '').strip().lower()
            elif line.startswith('METRICS:'):
                metrics = [m.strip() for m in line.replace('METRICS:', '').split(',')]
                metrics = [m for m in metrics if m in context['available_codes']]
        
        if analysis:
            st.subheader("Analysis")
            st.write(analysis)
            
        if viz_type and viz_type != 'none' and metrics:
            st.subheader("Visualization")
            fig = create_visualization(df, viz_type, metrics)
            if fig:
                st.pyplot(fig)
            else:
                st.warning("Could not generate requested visualization")

else:
    st.warning("No financial data available in connected database")

st.markdown("""
---
**Note:** All analyses generated based on regulatory data from Supabase tables:
- `y9c_full`: FR Y-9C report data
- `mdrm_mapping`: Metric definitions and mappings
""")
