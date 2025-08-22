import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import date

# Google Sheets Auth
scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
try:
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Cigarette Tracker").sheet1
except:
    st.error("Failed to connect to Google Sheets. Check credentials.")
    st.stop()

# Data functions
def get_data():
    return pd.DataFrame(sheet.get_all_records())

def add_entry(entry):
    sheet.append_row(entry)

def update_entry(index, row):
    sheet.update(f"A{index+2}:E{index+2}", [row])

def delete_entry(index):
    sheet.delete_rows(index+2)

# Streamlit UI
st.title("Cigarette Tracker")
menu = ["Add Entry", "View/Edit"]
choice = st.sidebar.selectbox("Menu", menu)

if choice == "Add Entry":
    c_date = st.date_input("Date", date.today())
    brand = st.text_input("Brand")
    qty = st.number_input("Cigarettes", 1)
    price = st.number_input("Price per Pack", 0.0)
    if st.button("Add"):
        total = price * (qty / 20)
        add_entry([str(c_date), brand, qty, price, total])
        st.success("Entry added!")

else:
    df = get_data()
    st.dataframe(df)
    idx = st.number_input("Row to Edit/Delete", min_value=0, max_value=len(df)-1, step=1)
    action = st.radio("Action", ["Update", "Delete"])
    if action == "Update":
        c_date = st.text_input("Date", df.iloc[idx]['Date'])
        brand = st.text_input("Brand", df.iloc[idx]['Brand'])
        qty = st.number_input("Cigarettes", value=df.iloc[idx]['Quantity'])
        price = st.number_input("Price per Pack", value=df.iloc[idx]['Price'])
        if st.button("Update"):
            total = price * (qty / 20)
            update_entry(idx, [c_date, brand, qty, price, total])
            st.success("Updated!")
    elif action == "Delete" and st.button("Delete"):
        delete_entry(idx)
        st.success("Deleted!")
