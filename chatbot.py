# chatbot.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client, ClientOptions
import openai
import backoff
import json
import time

# Configuration
ESSENTIAL_COLS = ['bhck2170', 'bhck2948', 'bhck3210']
CACHE_TTL = 86400  # 24 hours cache
AI_MODEL = "gpt-4o"
MAX_PAGES = 10      # 10 pages × 500 rows = 5000 records
PAGE_SIZE = 500     # Free tier can handle ~500 rows/request

def init_supabase():
    """Initialize Supabase client for free tier"""
    return create_client(
        st.secrets.SUPABASE_URL,
        st.secrets.SUPABASE_KEY,
        options=ClientOptions(
            postgrest_client_timeout=60,
            schema='public',
            headers={
                'Content-Type': 'application/json',
                'Prefer': 'count=exact'
            }
        )
    )

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
@backoff.on_exception(backoff.expo, Exception, max_tries=5)
def fetch_financial_data():
    """Optimized data loader for free tier constraints"""
    try:
        supabase = init_supabase()
        processed_data = []
        
        # Get total count
        count_res = supabase.table('y9c_full').select('count', count='exact').execute()
        total_records = count_res.count or 0
        
        st_progress = st.progress(0)
        st_status = st.empty()

        for page in range(MAX_PAGES):
            try:
                st_status.text(f"Loading page {page+1}/{MAX_PAGES}...")
                response = supabase.table('y9c_full') \
                            .select('data,report_period') \
                            .order('report_period', desc=True) \
                            .range(page*PAGE_SIZE, (page+1)*PAGE_SIZE-1) \
                            .execute()

                # Process batch
                batch = []
                for row in response.data:
                    try:
                        data_str = row['data'].replace('""', '"').replace('\\"', '"')
                        parsed = json.loads(data_str)
                        batch.append({
                            'report_period': pd.to_datetime(row['report_period']),
                            **{col: float(parsed.get(col, 0)) for col in ESSENTIAL_COLS}
                        })
                    except Exception as e:
                        continue
                
                processed_data.extend(batch)
                progress = min((page+1)/MAX_PAGES, 1.0)
                st_progress.progress(progress)
                
                if len(response.data) < PAGE_SIZE:
                    break

                time.sleep(1)  # Rate limiting for free tier

            except Exception as e:
                st.error(f"⚠️ Page {page+1} error: {str(e)}")
                continue

        st_progress.empty()
        st_status.empty()
        return pd.DataFrame(processed_data).drop_duplicates().sort_values('report_period', ascending=False)
    
    except Exception as e:
        st.error(f"📊 Critical Data Error: {str(e)}")
        return pd.DataFrame()

def main():
    st.set_page_config(page_title="Banking Analytics", layout="wide")
    st.title("🏦 Free Tier Banking Dashboard")
    
    try:
        # Initialize clients
        supabase = init_supabase()
        openai.api_key = st.secrets.OPENAI_API_KEY
        
        # Load data
        df = fetch_financial_data()
        
        if df.empty:
            st.warning("⚠️ No data loaded - check connection or try later")
            return
        
        # Display basic stats
        with st.expander("📈 Quick Stats"):
            cols = st.columns(3)
            cols[0].metric("Total Records", len(df))
            cols[1].metric("Date Range", 
                          f"{df['report_period'].min().date()} to {df['report_period'].max().date()}")
            cols[2].metric("Latest Assets", f"${df['bhck2170'].iloc[0]:,.0f}")
        
        # Analysis UI
        query = st.text_input("Ask for analysis:", placeholder="Compare assets and liabilities...")
        
        if query:
            with st.spinner("Analyzing with GPT-4o..."):
                try:
                    # Generate AI response
                    response = openai.chat.completions.create(
                        model=AI_MODEL,
                        messages=[{
                            "role": "user",
                            "content": f"""Analyze banking data with latest numbers:
                            - Assets: ${df['bhck2170'].iloc[0]:,.0f}
                            - Liabilities: ${df['bhck2948'].iloc[0]:,.0f}
                            - Equity: ${df['bhck3210'].iloc[0]:,.0f}
                            Query: {query}"""
                        }],
                        max_tokens=500
                    )
                    
                    analysis = response.choices[0].message.content
                    st.write(analysis)
                    
                    # Simple visualization
                    fig, ax = plt.subplots()
                    df.set_index('report_period')[ESSENTIAL_COLS].plot(ax=ax)
                    st.pyplot(fig)
                    
                except Exception as e:
                    st.error(f"🤖 AI Error: {str(e)}")

    except Exception as e:
        st.error(f"🚨 Critical Error: {str(e)}")

if __name__ == "__main__":
    main()
