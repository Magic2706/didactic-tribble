import streamlit as st
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Cigarette Tracker", page_icon="🚬", layout="centered")

# ----------------------------
# Google Sheets Setup
# ----------------------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

sheet = None
try:
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=scope
    )
    client = gspread.authorize(creds)
    sheet = client.open("Cigarette Tracker").sheet1
except Exception as e:
    st.error(f"❌ Could not connect to Google Sheets: {e}")
    st.stop()

# ----------------------------
# Helper Functions
# ----------------------------
def get_data():
    """Fetch all records from the Google Sheet as a DataFrame."""
    if sheet is None:
        st.error("Google Sheet is not initialized.")
        return pd.DataFrame()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def add_entry(date, count):
    """Append a new entry to the Google Sheet."""
    if sheet is not None:
        sheet.append_row([date, count])

# ----------------------------
# Streamlit UI
# ----------------------------
st.title("🚬 Cigarette Tracker")
st.markdown("Log your daily cigarette count and track your progress.")

# Display existing data
df = get_data()
if not df.empty:
    st.subheader("Your Smoking Log")
    st.dataframe(df)
else:
    st.info("No data found yet. Add your first entry below!")

# Add new entry
st.subheader("Add New Entry")
with st.form("entry_form", clear_on_submit=True):
    date = st.date_input("Date")
    count = st.number_input("Number of cigarettes", min_value=0, step=1)
    submitted = st.form_submit_button("Add Entry")
    if submitted:
        add_entry(str(date), int(count))
        st.success("Entry added successfully! Refresh the page to see it.")

