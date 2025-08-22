import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, APIError
from datetime import date
from typing import List, Dict, Any

st.set_page_config(page_title="🚬 Smoking & Spend Tracker", layout="wide")

# ---------- App Constants ----------
DEFAULT_COLUMNS = [
    "Date", "Brand", "Quantity", "UnitsPerPack", "PricePerPack", "TotalCost",
    "PaymentMethod", "AmountPaid", "Outstanding", "Vendor", "Notes"
]
NUMERIC_COLS = [
    "Quantity", "UnitsPerPack", "PricePerPack", "TotalCost", "AmountPaid", "Outstanding"
]
CURRENCY_COLS = ["PricePerPack", "TotalCost", "AmountPaid", "Outstanding"]

# ---------- Helper Functions ----------
def _err(msg: str, e: Exception = None):
    """Displays a formatted error message in Streamlit."""
    st.error(msg + (f"\n\n**Details:** {e}" if e else ""))

# ---------- Google Sheets Integration ----------
def get_gspread_client() -> gspread.Client | None:
    """Authenticates with Google Sheets API using Streamlit Secrets."""
    try:
        creds_json = st.secrets["gcp_service_account"]
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        _err("Google Cloud authentication failed. Ensure your `gcp_service_account` secret is correctly configured in Streamlit settings.", e)
        return None

def open_worksheet(sheet_url_or_title: str) -> gspread.Worksheet | None:
    """Opens the first worksheet of a Google Spreadsheet by URL or title."""
    client = get_gspread_client()
    if not client:
        return None
    try:
        sh = client.open_by_url(sheet_url_or_title) if sheet_url_or_title.startswith("http") else client.open(sheet_url_or_title)
        return sh.sheet1
    except SpreadsheetNotFound:
        _err("Spreadsheet not found. Please check the URL/title and ensure the service account email has 'Editor' access.")
    except APIError as e:
        _err("Google Sheets API error. This might be due to rate limits, permissions, or an invalid request.", e)
    except Exception as e:
        _err("An unexpected error occurred while opening the spreadsheet.", e)
    return None

def ensure_headers(ws: gspread.Worksheet):
    """Creates the header row in the worksheet if it's empty."""
    try:
        if not ws.get_all_values():
            ws.append_row(DEFAULT_COLUMNS)
    except Exception as e:
        _err("Failed to create the header row.", e)
        st.stop()

@st.cache_data(ttl=300)
def load_df_from_sheet(sheet_url_or_title: str) -> pd.DataFrame:
    """Loads data from the Google Sheet into a Pandas DataFrame with caching."""
    ws = open_worksheet(sheet_url_or_title)
    if ws is None:
        return pd.DataFrame(columns=DEFAULT_COLUMNS)

    try:
        records = ws.get_all_records()
        df = pd.DataFrame(records)

        # Ensure all default columns exist, filling missing ones with None
        for col in DEFAULT_COLUMNS:
            if col not in df.columns:
                df[col] = None

        # Standardize data types
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            for col in NUMERIC_COLS:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        return df[DEFAULT_COLUMNS]
    except Exception as e:
        _err("Failed to read data from the Google Sheet.", e)
        return pd.DataFrame(columns=DEFAULT_COLUMNS)

def append_row_to_sheet(ws: gspread.Worksheet, row_data: List[Any]):
    """Appends a single row to the worksheet and clears the cache."""
    try:
        ws.append_row(row_data)
        load_df_from_sheet.clear()
        st.toast("✅ Entry added successfully!", icon="✅")
        st.rerun()
    except Exception as e:
        _err("Failed to add the new row to the sheet.", e)

def update_row_in_sheet(ws: gspread.Worksheet, row_index: int, row_data: List[Any]):
    """Replaces a row at a specific index and clears the cache."""
    try:
        ws.update(f'A{row_index}', [row_data]) # More efficient than delete/insert
        load_df_from_sheet.clear()
        st.toast("✏️ Entry updated successfully!", icon="✏️")
        st.rerun()
    except Exception as e:
        _err("Failed to update the row in the sheet.", e)

def delete_row_from_sheet(ws: gspread.Worksheet, row_index: int):
    """Deletes a row at a specific index and clears the cache."""
    try:
        ws.delete_rows(row_index)
        load_df_from_sheet.clear()
        st.toast("🗑️ Entry deleted successfully!", icon="🗑️")
        st.rerun()
    except Exception as e:
        _err("Failed to delete the row from the sheet.", e)

# ---------- Main App UI ----------
st.title("🚬 Smoking Habit & Credit Spend Tracker")

# --- Sidebar for Connection ---
with st.sidebar:
    st.header("🔗 Connect to Google Sheet")
    sheet_url = st.text_input(
        "Spreadsheet URL or Title",
        placeholder="https://docs.google.com/spreadsheets/d/...",
        help="Paste the full URL of your Google Sheet or its exact title."
    )
    st.caption("Ensure you've **shared** the sheet with your service account email, granting 'Editor' permissions.")
    if st.button("🔄 Refresh Data"):
        load_df_from_sheet.clear()
        st.rerun()

if not sheet_url:
    st.info("Please enter your Google Sheet URL or title in the sidebar to begin.")
    st.stop()

# --- Load Data and Initialize ---
ws = open_worksheet(sheet_url)
if ws is None:
    st.stop()

ensure_headers(ws)
df = load_df_from_sheet(sheet_url)

# --- UI Tabs ---
tab_add, tab_view, tab_analytics = st.tabs(["➕ Add Entry", "📄 View & Edit", "📈 Analytics"])

# --- Tab: Add Entry ---
with tab_add:
    st.header("Add a New Log")
    with st.form("add_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            in_date = st.date_input("Date", value=date.today())
            brand = st.text_input("Brand", placeholder="e.g., Marlboro")
            quantity = st.number_input("Quantity (sticks)", min_value=1, step=1, value=10)
        with col2:
            units_per_pack = st.number_input("Units per pack", min_value=1, value=20, step=1)
            price_per_pack = st.number_input("Price per pack (₹)", min_value=0.0, step=0.50, format="%.2f")
            payment = st.selectbox("Payment Method", ["Credit", "Cash"])
        with col3:
            amount_paid = st.number_input("Amount paid now (₹)", min_value=0.0, step=1.0, format="%.2f")
            vendor = st.text_input("Vendor (optional)")

        notes = st.text_area("Notes (optional)")

        # --- Dynamic Calculation Display ---
        if units_per_pack > 0 and price_per_pack > 0:
            packs_purchased = quantity / units_per_pack
            total_cost = packs_purchased * price_per_pack
            outstanding = max(total_cost - amount_paid, 0.0)

            st.markdown("---")
            st.markdown("#### 💰 Calculation")
            calc_col1, calc_col2 = st.columns(2)
            calc_col1.metric("Total Cost", f"₹{total_cost:.2f}", help=f"{packs_purchased:.2f} packs × ₹{price_per_pack:.2f}")
            calc_col2.metric("Outstanding Credit", f"₹{outstanding:.2f}", help=f"₹{total_cost:.2f} (Total) - ₹{amount_paid:.2f} (Paid)")

        submitted = st.form_submit_button("💾 Save Entry", type="primary", use_container_width=True)
        if submitted:
            if not brand.strip():
                st.error("Brand name cannot be empty.")
            else:
                new_row = [
                    str(in_date), brand.strip(), int(quantity), int(units_per_pack),
                    float(price_per_pack), float(total_cost), payment, float(amount_paid),
                    float(outstanding), vendor.strip(), notes.strip()
                ]
                append_row_to_sheet(ws, new_row)

# --- Tab: View & Edit ---
with tab_view:
    st.header("📊 Your Data Log")

    if df.empty:
        st.info("No data found. Add an entry in the 'Add Entry' tab.")
    else:
        display_df = df.copy().sort_values(by="Date", ascending=False)
        display_df["Date"] = display_df["Date"].dt.strftime('%Y-%m-%d')
        for col in CURRENCY_COLS:
            display_df[col] = display_df[col].apply(lambda x: f"₹{x:,.2f}")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.header("✏️ Edit or Delete an Entry")
    search_term = st.text_input("Search for an entry to edit/delete (by brand, vendor, etc.)", key="search")

    if search_term:
        # Filter dataframe to find matches
        mask = np.column_stack([df[col].astype(str).str.contains(search_term, case=False, na=False) for col in df.columns])
        matched_df = df[mask.any(axis=1)]

        if matched_df.empty:
            st.info("No matching entries found.")
        else:
            # Create labels for the selectbox
            matched_df['label'] = matched_df.apply(
                lambda row: f"{row['Date'].strftime('%Y-%m-%d')} | {row['Brand']} | {row['Quantity']} sticks | ₹{row['TotalCost']:.2f}",
                axis=1
            )
            selected_label = st.selectbox("Select an entry to modify", options=matched_df['label'])
            selected_row_data = matched_df[matched_df['label'] == selected_label].iloc[0]
            
            # Google sheet row index is 1-based + 1 for header
            sheet_row_index = selected_row_data.name + 2 

            col_edit, col_delete = st.columns(2)
            with col_edit:
                with st.expander("✏️ **Edit this entry**", expanded=True):
                    # Convert row to dict for easier access
                    row_dict = selected_row_data.to_dict()

                    e_date = st.date_input("Date", value=row_dict['Date'].date(), key=f"d_{sheet_row_index}")
                    e_brand = st.text_input("Brand", value=row_dict['Brand'], key=f"b_{sheet_row_index}")
                    e_qty = st.number_input("Quantity", min_value=1, value=int(row_dict['Quantity']), key=f"q_{sheet_row_index}")
                    e_units = st.number_input("Units/Pack", min_value=1, value=int(row_dict['UnitsPerPack']), key=f"u_{sheet_row_index}")
                    e_price = st.number_input("Price/Pack (₹)", min_value=0.0, value=float(row_dict['PricePerPack']), format="%.2f", key=f"p_{sheet_row_index}")
                    e_payment = st.selectbox("Payment", ["Credit", "Cash"], index=["Credit", "Cash"].index(row_dict['PaymentMethod']), key=f"pay_{sheet_row_index}")
                    e_paid = st.number_input("Amount Paid (₹)", min_value=0.0, value=float(row_dict['AmountPaid']), format="%.2f", key=f"paid_{sheet_row_index}")
                    e_vendor = st.text_input("Vendor", value=row_dict['Vendor'], key=f"v_{sheet_row_index}")
                    e_notes = st.text_area("Notes", value=row_dict['Notes'], key=f"n_{sheet_row_index}")

                    # Recalculate costs
                    e_total = (e_qty / e_units) * e_price if e_units > 0 else 0
                    e_outstanding = max(e_total - e_paid, 0.0)
                    st.metric("New Total Cost", f"₹{e_total:.2f}")

                    if st.button("💾 Update Entry", type="primary", key=f"upd_{sheet_row_index}"):
                        if not e_brand.strip():
                            st.error("Brand name cannot be empty.")
                        else:
                            updated_row = [
                                str(e_date), e_brand.strip(), int(e_qty), int(e_units), float(e_price),
                                float(e_total), e_payment, float(e_paid), float(e_outstanding),
                                e_vendor.strip(), e_notes.strip()
                            ]
                            update_row_in_sheet(ws, sheet_row_index, updated_row)
            with col_delete:
                with st.expander("🗑️ **Delete this entry**"):
                    st.warning("⚠️ This action is permanent and cannot be undone.")
                    if st.button("Confirm Deletion", type="secondary", key=f"del_{sheet_row_index}"):
                        delete_row_from_sheet(ws, sheet_row_index)

# --- Tab: Analytics ---
with tab_analytics:
    st.header("📈 Trends & Insights")

    if df.empty or df['Date'].isnull().all():
        st.info("Add some entries with valid dates to see analytics.")
    else:
        dfa = df.dropna(subset=['Date']).copy()

        # --- KPIs ---
        total_sticks = int(dfa["Quantity"].sum())
        total_spend = float(dfa["TotalCost"].sum())
        outstanding_credit = float(dfa["Outstanding"].sum())
        days_tracked = (dfa["Date"].max() - dfa["Date"].min()).days + 1
        avg_sticks_per_day = total_sticks / days_tracked if days_tracked > 0 else 0
        avg_cost_per_stick = total_spend / total_sticks if total_sticks > 0 else 0

        kpi_cols = st.columns(5)
        kpi_cols[0].metric("Total Cigarettes", f"{total_sticks:,}")
        kpi_cols[1].metric("Total Spend", f"₹{total_spend:,.2f}")
        kpi_cols[2].metric("Outstanding Credit", f"₹{outstanding_credit:,.2f}")
        kpi_cols[3].metric("Avg Sticks/Day", f"{avg_sticks_per_day:.1f}")
        kpi_cols[4].metric("Avg Cost/Stick", f"₹{avg_cost_per_stick:.2f}")

        st.markdown("---")

        # --- Time Series Charts ---
        # Correctly group by date and reset the index to make 'Date' a column
        by_day = dfa.groupby(dfa["Date"].dt.date).agg(
            Sticks=("Quantity", "sum"),
            Spend=("TotalCost", "sum"),
            Outstanding=("Outstanding", "sum")
        ).reset_index()
        by_day["Date"] = pd.to_datetime(by_day["Date"])
        by_day.set_index("Date", inplace=True)

        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.subheader("Daily Consumption (Sticks)")
            st.bar_chart(by_day[["Sticks"]], height=300)
        with chart_col2:
            st.subheader("Daily Spending (₹)")
            st.area_chart(by_day[["Spend"]], height=300, color="#ffaa00")

        # --- Brand Analysis ---
        st.markdown("---")
        st.subheader("🏷️ Brand Analysis")
        brand_stats = dfa.groupby("Brand").agg(
            TotalSticks=("Quantity", "sum"),
            TotalSpend=("TotalCost", "sum"),
            Entries=("Brand", "count")
        ).sort_values("TotalSticks", ascending=False)
        brand_stats['AvgCostPerStick'] = (brand_stats['TotalSpend'] / brand_stats['TotalSticks']).fillna(0)
        
        st.dataframe(
            brand_stats.style.format({
                'TotalSpend': '₹{:,.2f}',
                'AvgCostPerStick': '₹{:,.2f}'
            }),
            use_container_width=True
        )
