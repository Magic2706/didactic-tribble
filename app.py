import streamlit as st
import pandas as pd
from google.oauth2.service_account import Credentials
import gspread
from datetime import date
import plotly.express as px

st.set_page_config(page_title="Cigarette Tracker", layout="centered")
st.title("🚬 Smoking Habit & Cost Tracker")

# -----------------------------
# 1. Authenticate & Open Sheet
# -----------------------------
sheet = None
try:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(secret, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open("Cigarette Tracker").sheet1
except Exception as e:
    st.error("🔒 Could not access Google Sheets. Check your credentials and sheet sharing.")
    st.stop()

# -----------------------------
# 2. CRUD Helper Functions
# -----------------------------
@st.cache_data(ttl=300)
def get_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def add_entry(entry):
    sheet.append_row(entry)

def update_entry(idx, updated):
    sheet.delete_row(idx + 2)
    sheet.insert_row(updated, idx + 2)

def delete_entry(idx):
    sheet.delete_row(idx + 2)

# -----------------------------
# 3. Sidebar Menu
# -----------------------------
menu = ["Add Entry", "View/Edit Entries", "Analytics"]
choice = st.sidebar.selectbox("Navigate", menu)

# -----------------------------
# 4. UI: Add Entry
# -----------------------------
if choice == "Add Entry":
    st.header("Log Your Cigarette Usage")
    c_date = st.date_input("Date", date.today())
    brand = st.text_input("Brand")
    quantity = st.number_input("Quantity (sticks)", min_value=1, step=1)
    price = st.number_input("Price per Pack", min_value=0.0, format="%.2f")
    notes = st.text_area("Notes (optional)")

    if st.button("Save Entry"):
        total_cost = price * (quantity / 20)
        entry = [str(c_date), brand, quantity, price, total_cost, notes]
        add_entry(entry)
        st.success("Entry added!")
        st.experimental_rerun()

# -----------------------------
# 5. UI: View / Edit
# -----------------------------
elif choice == "View/Edit Entries":
    st.header("View or Modify Entries")
    df = get_data()
    if df.empty:
        st.info("No entries yet.")
    else:
        st.dataframe(df)
        idx = st.number_input("Select Row Index", min_value=0, max_value=len(df) - 1, step=1)
        row = df.iloc[idx]

        with st.form("edit_form"):
            new_date = st.date_input("Date", pd.to_datetime(row["Date"]).date())
            new_brand = st.text_input("Brand", row["Brand"])
            new_qty = st.number_input("Quantity", min_value=1, value=int(row["Quantity"]))
            new_price = st.number_input("Price per Pack", value=float(row["Price_per_pack"]), format="%.2f")
            new_notes = st.text_area("Notes", row.get("Notes", ""))
            submitted = st.form_submit_button("Update")

            if submitted:
                total = new_price * (new_qty / 20)
                updated = [str(new_date), new_brand, new_qty, new_price, total, new_notes]
                update_entry(idx, updated)
                st.success("Entry updated successfully!")
                st.experimental_rerun()
        
        if st.button("Delete Entry"):
            delete_entry(idx)
            st.warning("Entry deleted.")
            st.experimental_rerun()

# -----------------------------
# 6. UI: Analytics
# -----------------------------
else:
    st.header("Analytics: Trends & Patterns")
    df = get_data()
    if df.empty:
        st.info("Add some entries first to view analytics.")
    else:
        df["Date"] = pd.to_datetime(df["Date"])
        daily_cigs = df.groupby("Date")["Quantity"].sum().reset_index()
        fig1 = px.bar(daily_cigs, x="Date", y="Quantity", title="Cigarettes Smoked Per Day")
        st.plotly_chart(fig1, use_container_width=True)

        spend = df.groupby("Date")["Total_cost"].sum().reset_index()
        fig2 = px.line(spend, x="Date", y="Total_cost", title="Daily Spending")
        st.plotly_chart(fig2, use_container_width=True)

        brands = df.groupby("Brand")["Quantity"].sum().reset_index()
        fig3 = px.pie(brands, names="Brand", values="Quantity", title="Brand Distribution")
        st.plotly_chart(fig3, use_container_width=True)
