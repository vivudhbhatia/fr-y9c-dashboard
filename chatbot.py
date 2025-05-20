import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from supabase import create_client, ClientOptions
import openai
import backoff
from datetime import datetime

# Constants
ESSENTIAL_COLS = ['report_period', 'bhck2170', 'bhck2948', 'bhck3210']
MAX_ROWS = 2000
PAGE_SIZE = 300

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def init_supabase():
    return create_client(
        st.secrets.SUPABASE_URL,
        st.secrets.SUPABASE_KEY,
        options=ClientOptions(
            postgrest_client_timeout=45,
            schema='public'
        )
    )

supabase = init_supabase()
openai.api_key = st.secrets.OPENAI_API_KEY

@st.cache_data(ttl=3600, show_spinner=False)
@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def fetch_data():
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
    return df.drop_duplicates('report_period')

def main():
    st.set_page_config(page_title="Banking Dashboard", layout="wide")
    st.title("🏦 Regulatory Analytics")
    
    try:
        df = fetch_data()
        if df.empty:
            st.warning("No data available")
            return
            
        # Rest of your UI code
        
    except Exception as e:
        st.error(f"Application error: {str(e)}")
        st.stop()

if __name__ == "__main__":
    main()
