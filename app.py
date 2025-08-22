import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, APIError

# --- Google Sheets Setup ---
def get_client():
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Authentication failed: {e}")
        return None

def get_sheet(sheet_url):
    client = get_client()
    if not client:
        return None
    try:
        return client.open_by_url(sheet_url).sheet1
    except SpreadsheetNotFound:
        st.error("Could not find spreadsheet. Check URL or sharing permissions.")
    except APIError as e:
        st.error(f"Google Sheets API error: {e}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
    return None

# --- CRUD FUNCTIONS ---
def read_all(sheet):
    try:
        return sheet.get_all_records()
    except Exception as e:
        st.error(f"Failed to read data: {e}")
        return []

def create_row(sheet, row_values):
    try:
        sheet.append_row(row_values)
        st.success("Row added successfully.")
    except Exception as e:
        st.error(f"Failed to add row: {e}")

def update_row(sheet, row_index, new_values):
    try:
        sheet.delete_row(row_index)   # remove old row
        sheet.insert_row(new_values, row_index)  # insert new row
        st.success("Row updated successfully.")
    except Exception as e:
        st.error(f"Failed to update row: {e}")

def delete_row(sheet, row_index):
    try:
        sheet.delete_row(row_index)
        st.success("Row deleted successfully.")
    except Exception as e:
        st.error(f"Failed to delete row: {e}")

# --- Streamlit Interface ---
st.title("Google Sheets CRUD App")

SHEET_URL = st.text_input("Enter Google Sheet URL", "")
if SHEET_URL:
    sheet = get_sheet(SHEET_URL)
    if sheet:
        st.subheader("Current Data")
        data = read_all(sheet)
        st.write(data if data else "No data found.")

        # --- Create ---
        st.subheader("Add New Row")
        new_row = st.text_input("Enter comma-separated values")
        if st.button("Add Row"):
            if new_row:
                create_row(sheet, [x.strip() for x in new_row.split(",")])
            else:
                st.warning("Please enter values.")

        # --- Update ---
        st.subheader("Update Existing Row")
        row_to_update = st.number_input("Row index to update (1 = first row after header)", min_value=2, step=1)
        update_values = st.text_input("Enter new comma-separated values")
        if st.button("Update Row"):
            if update_values:
                update_row(sheet, int(row_to_update), [x.strip() for x in update_values.split(",")])
            else:
                st.warning("Please enter values.")

        # --- Delete ---
        st.subheader("Delete Row")
        row_to_delete = st.number_input("Row index to delete (1 = first row after header)", min_value=2, step=1)
        if st.button("Delete Row"):
            delete_row(sheet, int(row_to_delete))
