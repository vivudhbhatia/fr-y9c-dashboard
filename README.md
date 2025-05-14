# FR Y-9C Dashboard

This interactive Streamlit dashboard visualizes bank holding company data from the FR Y-9C report using Supabase as a backend.

### Features:
- Filter by reporting period, asset size, MDRM fields
- Visualize total asset distributions
- Compare data across periods
- Export filtered results to CSV

### Tech Stack:
- Streamlit (Frontend)
- Supabase (PostgreSQL Backend)
- Python (pandas, plotly, requests)

### Run Locally
```bash
pip install -r requirements.txt
streamlit run app.py
