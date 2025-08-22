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
        sheet.delete_row(row_index)
        sheet.insert_row(new_values, row_index)
        st.success("Row updated successfully.")
    except Exception as e:
        st.error(f"Failed to update row: {e}")

def delete_row(sheet, row_index):
    try:
        sheet.delete_row(row_index)
        st.success("Row deleted successfully.")
    except Exception as e:
        st.error(f"Failed to delete row: {e}")

def find_rows(sheet, keyword):
    """Return list of (row_index, row_values) where keyword matches any cell."""
    try:
        data = sheet.get_all_values()
        matches = []
        for i, row in enumerate(data, start=1):  # 1-based index for gspread
            if any(keyword.lower() in str(cell).lower() for cell in row):
                matches.append((i, row))
        return matches
    except Exception as e:
        st.error(f"Failed to search rows: {e}")
        return []

# --- Streamlit Interface ---
st.title("Google Sheets CRUD App (Safe Mode)")

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
        keyword = st.text_input("Search keyword for row to update")
        if st.button("Search to Update"):
            matches = find_rows(sheet, keyword)
            if matches:
                st.write("Select a row to update:")
                for idx, row in matches:
                    if st.button(f"Update Row {idx}: {row}"):
                        new_values = st.text_input(f"Enter new values for Row {idx} (comma-separated)", key=f"update_{idx}")
                        if st.button(f"Confirm Update Row {idx}", key=f"confirm_update_{idx}"):
                            update_row(sheet, idx, [x.strip() for x in new_values.split(",")])
            else:
                st.warning("No matching rows found.")

        # --- Delete ---
        st.subheader("Delete Existing Row")
        keyword_del = st.text_input("Search keyword for row to delete")
        if st.button("Search to Delete"):
            matches = find_rows(sheet, keyword_del)
            if matches:
                st.write("Select a row to delete:")
                for idx, row in matches:
                    if st.button(f"Delete Row {idx}: {row}", key=f"delete_{idx}"):
                        delete_row(sheet, idx)
            else:
                st.warning("No matching rows found.")
