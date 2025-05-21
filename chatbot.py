# chatbot.py (updated version)
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
CACHE_TTL = 86400
AI_MODEL = "gpt-4o"
MAX_PAGES = 10
PAGE_SIZE = 500

def init_supabase():
    """Initialize Supabase client with better error visibility"""
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
        st.error(f"🔌 Connection Error: {str(e)}")
        st.stop()

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def fetch_financial_data():
    """Enhanced data loader with better feedback"""
    try:
        supabase = init_supabase()
        processed_data = []
        
        # Initial loading message
        load_placeholder = st.empty()
        load_placeholder.markdown("🚀 Initializing data connection...")
        
        # Get total count
        try:
            count_res = supabase.table('y9c_full').select('count', count='exact').execute()
            total_records = count_res.count or 0
            load_placeholder.markdown(f"📦 Found {total_records} records to process...")
        except Exception as e:
            load_placeholder.error(f"🔢 Count Error: {str(e)}")
            return pd.DataFrame()

        progress_bar = st.progress(0)
        status_text = st.empty()

        for page in range(MAX_PAGES):
            try:
                status_text.markdown(f"📥 Downloading page {page+1}/{MAX_PAGES}...")
                response = supabase.table('y9c_full') \
                            .select('data,report_period') \
                            .order('report_period', desc=True) \
                            .range(page*PAGE_SIZE, (page+1)*PAGE_SIZE-1) \
                            .execute()

                # Show raw response status
                st.write(f"🔍 Page {page+1} response status: {response.status_code}")

                if not response.data:
                    status_text.markdown("🏁 Reached end of data")
                    break

                # Process batch
                batch = []
                for idx, row in enumerate(response.data):
                    try:
                        data_str = row['data'].replace('""', '"').replace('\\"', '"')
                        parsed = json.loads(data_str)
                        batch.append({
                            'report_period': pd.to_datetime(row['report_period']),
                            **{col: float(parsed.get(col, 0)) for col in ESSENTIAL_COLS}
                        })
                    except json.JSONDecodeError:
                        st.error(f"⚠️ JSON error in row {idx} of page {page+1}")
                        continue
                    except Exception as e:
                        st.error(f"⚠️ Processing error in row {idx}: {str(e)}")
                        continue
                
                processed_data.extend(batch)
                progress = min((page+1)/MAX_PAGES, 1.0)
                progress_bar.progress(progress)
                
                if len(response.data) < PAGE_SIZE:
                    status_text.markdown("🏁 Reached end of data")
                    break

                time.sleep(1)

            except Exception as e:
                st.error(f"🚨 Page {page+1} error: {str(e)}")
                break

        progress_bar.empty()
        status_text.empty()
        load_placeholder.empty()
        
        if not processed_data:
            st.error("❌ No data loaded - check database connection")
            return pd.DataFrame()
        
        df = pd.DataFrame(processed_data).drop_duplicates()
        st.write(f"✅ Successfully loaded {len(df)} records")
        return df.sort_values('report_period', ascending=False)
    
    except Exception as e:
        st.error(f"🚨 Critical Data Error: {str(e)}")
        return pd.DataFrame()

def main():
    st.set_page_config(page_title="Banking Analytics", layout="wide")
    st.title("🏦 Banking Analytics Dashboard")
    
    try:
        # Initialize clients
        supabase = init_supabase()
        openai.api_key = st.secrets.OPENAI_API_KEY
        
        # Load data with visible feedback
        df = fetch_financial_data()
        
        # Always show data status
        with st.expander("🔍 Data Status"):
            if df.empty:
                st.error("No data available")
            else:
                st.write(f"📅 Date Range: {df['report_period'].min().date()} to {df['report_period'].max().date()}")
                st.write(f"📊 Total Records: {len(df)}")
                st.write("Sample Data:", df.head(3))
        
        # Main analysis UI
        if not df.empty:
            with st.expander("📈 Quick Analysis"):
                st.line_chart(df.set_index('report_period')[ESSENTIAL_COLS])
            
            query = st.text_input("Ask for detailed analysis:", placeholder="Compare assets vs liabilities...")
            
            if query:
                with st.spinner("Analyzing..."):
                    try:
                        response = openai.chat.completions.create(
                            model=AI_MODEL,
                            messages=[{
                                "role": "user",
                                "content": f"""Analyze banking metrics:
                                {df.describe().to_markdown()}
                                User Question: {query}"""
                            }],
                            temperature=0.3,
                            max_tokens=500
                        )
                        st.write("📝 Analysis Results:")
                        st.write(response.choices[0].message.content)
                    except Exception as e:
                        st.error(f"🤖 AI Error: {str(e)}")

    except Exception as e:
        st.error(f"🚨 Application Error: {str(e)}")

if __name__ == "__main__":
    main()
