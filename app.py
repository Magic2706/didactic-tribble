import streamlit as st
from google.oauth2.service_account import Credentials
import gspread
import pandas as pd
from datetime import date
import plotly.express as px

# ---------------------------
# Authenticate first (GLOBAL)
# ---------------------------

from google.oauth2.service_account import Credentials


scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
client = gspread.authorize(creds)
sheet = client.open("Cigarette Tracker").sheet1
# ---------------------------
# Helper functions
# ---------------------------
def get_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def add_entry(entry):
    sheet.append_row(entry)

def update_entry(row_index, updated_row):
    sheet.delete_row(row_index+2)
    sheet.insert_row(updated_row, row_index+2)

def delete_entry(row_index):
    sheet.delete_row(row_index+2)

# ---------------------------
# Streamlit UI
# ---------------------------
st.title("🚬 Smoking Habit & Expense Tracker")

menu = ["Add Entry", "View / Edit Entries", "Analytics"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Add Entry":
    st.subheader("Log today's cigarette consumption")
    c_date = st.date_input("Date", date.today())
    brand = st.text_input("Cigarette Brand")
    quantity = st.number_input("Quantity (sticks)", min_value=1, step=1)
    price_per_pack = st.number_input("Price per pack", min_value=0.0, step=0.1)
    notes = st.text_area("Notes", "")

    if st.button("Add Record"):
        total_cost = price_per_pack * (quantity / 20)  # Assuming 20 per pack
        entry = [str(c_date), brand, quantity, price_per_pack, total_cost, notes]
        add_entry(entry)
        st.success("Entry added successfully!")


elif choice == "View / Edit Entries":
    st.subheader("View or modify your records")
    df = get_data()
    st.dataframe(df)

    if not df.empty:
        selected_index = st.number_input("Row index to edit/delete", min_value=0, max_value=len(df)-1, step=1)
        selected_row = df.iloc[selected_index]

        st.write("### Update Record")
        new_date = st.date_input("Date", pd.to_datetime(selected_row['Date']).date())
        new_brand = st.text_input("Brand", selected_row['Brand'])
        new_quantity = st.number_input("Quantity", min_value=1, value=int(selected_row['Quantity']))
        new_price = st.number_input("Price per pack", min_value=0.0, value=float(selected_row['Price_per_pack']))
        new_notes = st.text_area("Notes", selected_row.get('Notes', ''))

        if st.button("Update Record"):
            total_cost = new_price * (new_quantity / 20)
            updated_row = [str(new_date), new_brand, new_quantity, new_price, total_cost, new_notes]
            update_entry(selected_index, updated_row)
            st.success("Record updated successfully!")

        if st.button("Delete Record"):
            delete_entry(selected_index)
            st.warning("Record deleted successfully!")

elif choice == "Analytics":
    st.subheader("Smoking & Spending Trends")
    df = get_data()

    if df.empty:
        st.info("No data available yet.")
    else:
        df['Date'] = pd.to_datetime(df['Date'])
      
        # Cigarettes per day
        daily_cigs = df.groupby('Date')['Quantity'].sum().reset_index()
        fig1 = px.bar(daily_cigs, x='Date', y='Quantity', title="Cigarettes Smoked Per Day")
        st.plotly_chart(fig1)

        # Spending trend
        daily_spend = df.groupby('Date')['Total_cost'].sum().reset_index()
        fig2 = px.line(daily_spend, x='Date', y='Total_cost', title="Daily Spending on Cigarettes")
        st.plotly_chart(fig2)

        # Brand distribution
        brand_dist = df.groupby('Brand')['Quantity'].sum().reset_index()
        fig3 = px.pie(brand_dist, names='Brand', values='Quantity', title="Brand Distribution")
        st.plotly_chart(fig3)
