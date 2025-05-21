# chatbot.py
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client, ClientOptions
import openai
import json
import time

# Configuration
ESSENTIAL_COLS = ['bhck2170', 'bhck2948', 'bhck3210']
CACHE_TTL = 86400  # 24 hours cache
PAGE_SIZE = 200    # Reduced for free tier safety
MAX_PAGES = 5      # Max 1000 records

def init_supabase():
    """Initialize Supabase client with error handling"""
    try:
        return create_client(
            st.secrets.SUPABASE_URL,
            st.secrets.SUPABASE_KEY,
            options=ClientOptions(
                postgrest_client_timeout=30,
                schema='public'
            )
        )
    except Exception as e:
        st.error(f"🔌 Connection Error: {str(e)}")
        st.stop()

def load_financial_data():
    """Simplified data loader with better error handling"""
    try:
        supabase = init_supabase()
        processed_data = []
        
        st.info("🔍 Connecting to database...")
        progress_bar = st.progress(0)
        status_text = st.empty()

        for page in range(MAX_PAGES):
            try:
                status_text.text(f"📥 Loading page {page+1}/{MAX_PAGES}...")
                
                # Simple query without range for free tier compatibility
                response = supabase.table('y9c_full') \
                            .select('data,report_period') \
                            .order('report_period', desc=True) \
                            .limit(PAGE_SIZE) \
                            .execute()

                if not response.data:
                    break

                # Process data
                for row in response.data:
                    try:
                        clean_data = row['data'].replace('""', '"')
                        parsed = json.loads(clean_data)
                        processed_data.append({
                            'report_period': pd.to_datetime(row['report_period']),
                            'assets': float(parsed.get('bhck2170', 0)),
                            'liabilities': float(parsed.get('bhck2948', 0)),
                            'equity': float(parsed.get('bhck3210', 0))
                        })
                    except Exception as e:
                        continue
                
                progress = (page + 1) / MAX_PAGES
                progress_bar.progress(progress)
                time.sleep(1)  # Rate limiting

            except Exception as e:
                st.error(f"⚠️ Error loading page {page+1}: {str(e)}")
                break

        progress_bar.empty()
        status_text.empty()
        
        if not processed_data:
            st.error("❌ No data loaded - check database connection and data format")
            return pd.DataFrame()
        
        return pd.DataFrame(processed_data).drop_duplicates()
    
    except Exception as e:
        st.error(f"🚨 Critical Error: {str(e)}")
        return pd.DataFrame()

def main():
    st.set_page_config(page_title="Banking Analytics", layout="centered")
    st.title("🏦 Banking Analytics Dashboard")
    
    try:
        # Load data first
        df = load_financial_data()
        
        # Always show status
        with st.expander("🔍 Data Connection Status", expanded=True):
            if not df.empty:
                st.success(f"✅ Loaded {len(df)} records")
                st.write("Latest data preview:")
                st.dataframe(df.head(3))
                st.write(f"Date range: {df['report_period'].min().date()} to {df['report_period'].max().date()}")
            else:
                st.error("❌ No data available")
                st.write("Troubleshooting steps:")
                st.write("1. Check Supabase connection secrets")
                st.write("2. Verify 'y9c_full' table exists")
                st.write("3. Ensure 'data' column contains valid JSON")
                return
        
        # Main analysis UI
        st.subheader("📈 Quick Analysis")
        selected_metric = st.selectbox("Choose metric", ['assets', 'liabilities', 'equity'])
        
        if not df.empty:
            fig, ax = plt.subplots()
            df.set_index('report_period')[selected_metric].plot(ax=ax)
            st.pyplot(fig)
            
            with st.expander("Advanced Analysis"):
                query = st.text_input("Ask a question about the data:")
                if query:
                    try:
                        response = openai.chat.completions.create(
                            model="gpt-4o",
                            messages=[{
                                "role": "user",
                                "content": f"""Analyze these banking metrics:
                                - Latest Assets: ${df['assets'].iloc[0]:,.0f}
                                - Latest Liabilities: ${df['liabilities'].iloc[0]:,.0f}
                                - Latest Equity: ${df['equity'].iloc[0]:,.0f}
                                Question: {query}"""
                            }]
                        )
                        st.write(response.choices[0].message.content)
                    except Exception as e:
                        st.error(f"🤖 AI Error: {str(e)}")

    except Exception as e:
        st.error(f"🚨 Application Error: {str(e)}")

if __name__ == "__main__":
    main()
