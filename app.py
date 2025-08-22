import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, APIError
from datetime import date

# Page configuration
st.set_page_config(page_title="🚬 Smoking & Spend Tracker", layout="wide")

# ---------- Constants ----------
DEFAULT_COLUMNS = [
    "Date", "Brand", "Quantity", "UnitsPerPack",
    "PricePerPack", "TotalCost", "PaymentMethod",
    "AmountPaid", "Outstanding", "Vendor", "Notes"
]

# ---------- Google Sheets Integration ----------
def get_gsheets_client():
    """Authenticate and return a gspread client."""
    try:
        info = st.secrets["gcp_service_account"]
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Authentication failed. Ensure service account credentials are set in Secrets. Details: {e}")
        return None

def open_spreadsheet(sheet_url_or_title: str):
    """Open a Google Sheet by URL or title."""
    client = get_gsheets_client()
    if not client:
        return None
    try:
        if sheet_url_or_title.startswith("http"):
            return client.open_by_url(sheet_url_or_title).sheet1
        return client.open(sheet_url_or_title).sheet1
    except SpreadsheetNotFound:
        st.error("Spreadsheet not found. Verify URL/title and Editor access for the service account.")
    except APIError as e:
        st.error(f"Google Sheets API error (quota/permissions). Details: {e}")
    except Exception as e:
        st.error(f"Unexpected error opening spreadsheet. Details: {e}")
    return None

def ensure_headers(ws):
    """Ensure the spreadsheet has the correct headers."""
    try:
        values = ws.get_all_values()
        if not values:
            ws.append_row(DEFAULT_COLUMNS)
        elif values[0] != DEFAULT_COLUMNS:
            st.warning("Spreadsheet headers differ from expected schema. Using existing headers.")
    except Exception as e:
        st.error(f"Failed to verify/create headers. Details: {e}")
        st.stop()

@st.cache_data(ttl=240)
def load_data(sheet_url_or_title: str):
    """Load and cache data from Google Sheet as a DataFrame."""
    ws = open_spreadsheet(sheet_url_or_title)
    if not ws:
        return pd.DataFrame(columns=DEFAULT_COLUMNS)
    
    try:
        df = pd.DataFrame(ws.get_all_records())
        if df.empty:
            return pd.DataFrame(columns=DEFAULT_COLUMNS)
        
        # Ensure all expected columns exist
        for col in DEFAULT_COLUMNS:
            if col not in df.columns:
                df[col] = None
        
        # Type conversions
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        numeric_cols = ["Quantity", "UnitsPerPack", "PricePerPack", "TotalCost", "AmountPaid", "Outstanding"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        return df[DEFAULT_COLUMNS]
    except Exception as e:
        st.error(f"Failed to load data from Google Sheet. Details: {e}")
        return pd.DataFrame(columns=DEFAULT_COLUMNS)

def append_data(ws, row):
    """Append a new row to the spreadsheet."""
    try:
        ws.append_row(row)
        load_data.clear()
        st.toast("✅ Entry added", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to add entry. Details: {e}")

def update_data(ws, idx_1based, row):
    """Update a row in the spreadsheet."""
    try:
        ws.delete_rows(idx_1based)
        ws.insert_row(row, idx_1based)
        load_data.clear()
        st.toast("✏️ Entry updated", icon="✏️")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to update entry. Details: {e}")

def delete_data(ws, idx_1based):
    """Delete a row from the spreadsheet."""
    try:
        ws.delete_rows(idx_1based)
        load_data.clear()
        st.toast("🗑️ Entry deleted", icon="🗑️")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to delete entry. Details: {e}")

def search_data(ws, keyword: str):
    """Search rows for a keyword and return matching rows with their indices."""
    try:
        data = ws.get_all_values()
        matches = [(i, row) for i, row in enumerate(data, start=1) if i > 1 and any(keyword.lower() in str(cell).lower() for cell in row)]
        return matches
    except Exception as e:
        st.error(f"Failed to search data. Details: {e}")
        return []

# ---------- UI Components ----------
def add_entry_tab(ws):
    """Render the 'Add Entry' tab."""
    st.subheader("Add New Log")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        date_input = st.date_input("Date", value=date.today())
        brand = st.text_input("Brand", placeholder="Marlboro, Classic, ...")
        quantity = st.number_input("Quantity (sticks)", min_value=1, step=1, value=1)
    
    with col2:
        units_per_pack = st.number_input("Units per pack", min_value=1, value=20, step=1)
        price_per_pack = st.number_input("Price per pack (₹)", min_value=0.0, step=0.5, format="%.2f")
        payment = st.selectbox("Payment Method", ["Cash", "Credit"])
    
    with col3:
        amount_paid = st.number_input("Amount paid now (₹)", min_value=0.0, step=0.5, format="%.2f")
        vendor = st.text_input("Vendor (optional)")
    
    notes = st.text_area("Notes (optional)")
    
    if units_per_pack > 0:
        packs_purchased = quantity / units_per_pack
        total_cost = packs_purchased * price_per_pack
        outstanding = max(total_cost - amount_paid, 0.0)
        
        st.divider()
        st.markdown("### 💰 Calculation Breakdown")
        col_calc1, col_calc2 = st.columns(2)
        with col_calc1:
            st.info(f"Packs: {quantity} ÷ {units_per_pack} = {packs_purchased:.3f} packs\n\n"
                    f"Total Cost: {packs_purchased:.3f} × ₹{price_per_pack:.2f} = ₹{total_cost:.2f}")
        with col_calc2:
            st.success(f"Outstanding: ₹{total_cost:.2f} - ₹{amount_paid:.2f} = ₹{outstanding:.2f}\n\n"
                       f"Cost per stick: ₹{total_cost/quantity:.2f}")
        
        if st.button("💾 Save Entry", type="primary", use_container_width=True):
            if brand.strip():
                row = [
                    str(date_input), brand.strip(), int(quantity), int(units_per_pack),
                    float(price_per_pack), float(total_cost), payment,
                    float(amount_paid), float(outstanding), vendor.strip(), notes.strip()
                ]
                append_data(ws, row)
            else:
                st.error("Brand name is required.")

def view_edit_delete_tab(ws, df):
    """Render the 'View / Edit / Delete' tab."""
    st.subheader("📊 Your Data")
    
    if not df.empty:
        display_df = df.copy()
        display_df["Date"] = pd.to_datetime(display_df["Date"]).dt.strftime("%Y-%m-%d")
        for col in ["PricePerPack", "TotalCost", "AmountPaid", "Outstanding"]:
            display_df[col] = display_df[col].apply(lambda x: f"₹{x:.2f}" if pd.notnull(x) else "₹0.00")
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data found. Add entries to view.")
    
    st.divider()
    st.markdown("### 🔍 Search to Edit/Delete")
    keyword = st.text_input("Search keyword (case-insensitive)", key="search_keyword")
    
    if keyword:
        matches = search_data(ws, keyword)
        if not matches:
            st.info("No matching entries found.")
        else:
            labels = [
                f"Row {idx}: {row[0]} | {row[1]} | {row[2]} sticks | ₹{float(row[5]):.2f} | {row[9] or 'No vendor'}"
                if len(row) > 9 else f"Row {idx}: {' | '.join(str(cell) for cell in row[:6])}"
                for idx, row in matches
            ]
            selected = st.selectbox("Select entry", options=list(range(len(matches))), format_func=lambda i: labels[i])
            sel_idx_1based, sel_row = matches[selected]
            
            st.write("**Selected entry values:**")
            st.json({DEFAULT_COLUMNS[i]: sel_row[i] if i < len(sel_row) else "" for i in range(len(DEFAULT_COLUMNS))})
            
            col_edit, col_delete = st.columns(2)
            
            with col_edit:
                with st.expander("✏️ Edit Entry", expanded=True):
                    try:
                        date_value = pd.to_datetime(sel_row[0]).date() if sel_row[0] else date.today()
                    except:
                        date_value = date.today()
                    
                    e_date = st.date_input("Date", value=date_value, key=f"edit_date_{sel_idx_1based}")
                    e_brand = st.text_input("Brand", sel_row[1] if len(sel_row) > 1 else "", key=f"edit_brand_{sel_idx_1based}")
                    e_qty = st.number_input("Quantity (sticks)", min_value=1, value=int(float(sel_row[2] or 1)), step=1, key=f"edit_qty_{sel_idx_1based}")
                    e_units = st.number_input("Units per pack", min_value=1, value=int(float(sel_row[3] or 20)), step=1, key=f"edit_units_{sel_idx_1based}")
                    e_price = st.number_input("Price per pack (₹)", min_value=0.0, value=float(sel_row[4] or 0.0), step=0.5, format="%.2f", key=f"edit_price_{sel_idx_1based}")
                    e_payment = st.selectbox("Payment Method", ["Cash", "Credit"], index=0 if sel_row[6] == "Cash" else 1, key=f"edit_payment_{sel_idx_1based}")
                    e_paid = st.number_input("Amount paid (₹)", min_value=0.0, value=float(sel_row[7] or 0.0), step=0.5, format="%.2f", key=f"edit_paid_{sel_idx_1based}")
                    e_vendor = st.text_input("Vendor (optional)", sel_row[9] if len(sel_row) > 9 else "", key=f"edit_vendor_{sel_idx_1based}")
                    e_notes = st.text_area("Notes (optional)", sel_row[10] if len(sel_row) > 10 else "", key=f"edit_notes_{sel_idx_1based}")
                    
                    if e_units > 0:
                        e_packs = e_qty / e_units
                        e_total = e Prune empty cache
                        st.rerun()

# ---------- Main Application ----------
def main():
    st.title("🚬 Smoking Habit & Credit Spend Tracker")
    
    with st.sidebar:
        st.header("Google Sheet Connection")
        sheet_url_or_title = st.text_input(
            "Spreadsheet URL or title",
            value="https://docs.google.com/spreadsheets/d/1rcfWMw8XRYj9_3j3sAtyh1LIk1s-JiJDjhKweUisXJU/",
            placeholder="https://docs.google.com/spreadsheets/d/..."
        )
        st.caption("Ensure the sheet is shared with your service account email (Editor access).")
        if st.button("🔄 Refresh Data"):
            load_data.clear()
            st.rerun()
    
    if not sheet_url_or_title:
        st.info("Enter a Google Sheet URL or title to begin.")
        st.stop()
    
    ws = open_spreadsheet(sheet_url_or_title)
    if not ws:
        st.stop()
    
    ensure_headers(ws)
    df = load_data(sheet_url_or_title)
    
    tab_add, tab_view, tab_analytics = st.tabs(["➕ Add Entry", "📄 View / Edit / Delete", "📈 Analytics"])
    
    with tab_add:
        add_entry_tab(ws)
    
    with tab_view:
        view_edit_delete_tab(ws, df)
    
    with tab_analytics:
        analytics_tab(df)

if __name__ == "__main__":
    main()
