import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, APIError
from datetime import date

st.set_page_config(page_title="🚬 Smoking & Spend Tracker", layout="wide")

# ---------- Settings ----------
DEFAULT_COLUMNS = [
    "Date", "Brand", "Quantity", "UnitsPerPack",
    "PricePerPack", "TotalCost",
    "PaymentMethod", "AmountPaid", "Outstanding",
    "Vendor", "Notes"
]

def _err(msg, e=None):
    st.error(msg + (f"\n\nDetails: {e}" if e else ""))

# ---------- Google Sheets: Auth + Open ----------
def get_client():
    try:
        info = st.secrets["gcp_service_account"]  # stored in Secrets
    except Exception:
        _err("Secrets not found. Add your service account under **Settings → Secrets** as `[gcp_service_account]`.")
        return None
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        _err("Authentication failed. Check private key formatting and fields.", e)
        return None

def open_sheet(sheet_url_or_title: str):
    client = get_client()
    if not client:
        return None
    try:
        if sheet_url_or_title.startswith("http"):
            sh = client.open_by_url(sheet_url_or_title)
        else:
            sh = client.open(sheet_url_or_title)
        ws = sh.sheet1
        return ws
    except SpreadsheetNotFound:
        _err("Spreadsheet not found. Ensure the **service account email** has **Editor** access and the **URL/title** is correct.")
    except APIError as e:
        _err("Google Sheets API error (quota/permissions/invalid request).", e)
    except Exception as e:
        _err("Unexpected error opening spreadsheet.", e)
    return None

# ---------- Helpers ----------
def ensure_headers(ws):
    """Create headers if the sheet is empty."""
    try:
        values = ws.get_all_values()
        if not values:
            ws.append_row(DEFAULT_COLUMNS)
        else:
            # If first row is missing columns, upsert headers (non-destructive to data)
            current_headers = values[0]
            if current_headers != DEFAULT_COLUMNS:
                # Do not delete user data; just warn
                st.warning("Header row differs from expected schema. Using existing headers.")
    except Exception as e:
        _err("Failed to verify/create header row.", e)
        st.stop()

@st.cache_data(ttl=240)
def load_df(sheet_url_or_title: str):
    """Load dataframe from Google Sheet with caching"""
    ws = open_sheet(sheet_url_or_title)
    if ws is None:
        return pd.DataFrame(columns=DEFAULT_COLUMNS)
    
    try:
        values = ws.get_all_records()  # skips header row
        df = pd.DataFrame(values)
        # Backfill missing columns (if older data)
        for c in DEFAULT_COLUMNS:
            if c not in df.columns:
                df[c] = None
        # Type fixes
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            float_cols = ["Quantity", "UnitsPerPack", "PricePerPack", "TotalCost", "AmountPaid", "Outstanding"]
            for c in float_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df[DEFAULT_COLUMNS] if not df.empty else pd.DataFrame(columns=DEFAULT_COLUMNS)
    except Exception as e:
        _err("Failed to read data from Google Sheet.", e)
        return pd.DataFrame(columns=DEFAULT_COLUMNS)

def clear_cache():
    load_df.clear()

def append_row(ws, row):
    try:
        ws.append_row(row)
        clear_cache()
        st.toast("✅ Added", icon="✅")
    except Exception as e:
        _err("Failed to add row.", e)

def replace_row(ws, idx_1based, row):
    """Replace data row at 1-based index (>=2). Keeps header intact."""
    try:
        ws.delete_rows(idx_1based)
        ws.insert_row(row, idx_1based)
        clear_cache()
        st.toast("✏️ Updated", icon="✏️")
    except Exception as e:
        _err("Failed to update row.", e)

def remove_row(ws, idx_1based):
    try:
        ws.delete_rows(idx_1based)
        clear_cache()
        st.toast("🗑️ Deleted", icon="🗑️")
    except Exception as e:
        _err("Failed to delete row.", e)

def search_rows(ws, keyword: str):
    """Return matches as list of (row_index_1based, row_values)."""
    try:
        data = ws.get_all_values()
        matches = []
        for i, row in enumerate(data, start=1):
            if i == 1:  # skip header
                continue
            if any(keyword.lower() in str(cell).lower() for cell in row):
                matches.append((i, row))
        return matches
    except Exception as e:
        _err("Failed to search rows.", e)
        return []

# ---------- UI ----------
st.title("🚬 Smoking Habit & Credit Spend Tracker")

with st.sidebar:
    st.header("Connect to Google Sheet")

    #st.text_input(
    #    "Paste Spreadsheet URL (recommended) or exact title",
     #   placeholder="https://docs.google.com/spreadsheets/d/...",
    #)
    st.caption("Make sure you **shared** the sheet with your service account email (Editor).")

if not sheet_url_or_title:
    st.info("Enter your Google Sheet URL or exact title to begin.")
    st.stop()

ws = open_sheet(sheet_url_or_title)
if ws is None:
    st.stop()

ensure_headers(ws)
df = load_df(sheet_url_or_title)

tab_add, tab_view, tab_analytics = st.tabs(["➕ Add Entry", "📄 View / Edit / Delete", "📈 Analytics"])

# ---------- ADD ----------
with tab_add:
    st.subheader("Add a new log")
    col1, col2, col3 = st.columns(3)
    with col1:
        in_date = st.date_input("Date", value=date.today())
        brand = st.text_input("Brand", placeholder="Marlboro, Classic, ...")
        quantity = st.number_input("Quantity (sticks)", min_value=1, step=1, value=1)
    with col2:
        units_per_pack = st.number_input("Units per pack", min_value=1, value=20, step=1)
        price_per_pack = st.number_input("Price per pack", min_value=0.0, step=0.5, format="%.2f")
        payment = st.selectbox("Payment Method", ["Cash", "Credit"])
    with col3:
        amount_paid = st.number_input("Amount paid now", min_value=0.0, step=0.5, format="%.2f")
        vendor = st.text_input("Vendor (optional)")
    notes = st.text_area("Notes (optional)")

    total_cost = price_per_pack * (quantity / max(units_per_pack, 1))
    outstanding = max(total_cost - amount_paid, 0.0)

    st.caption(f"Calculated Total Cost: **{total_cost:.2f}** | Outstanding: **{outstanding:.2f}**")

    if st.button("Save Entry", type="primary"):
        row = [
            str(in_date), brand, int(quantity), int(units_per_pack),
            float(price_per_pack), float(total_cost),
            payment, float(amount_paid), float(outstanding),
            vendor, notes
        ]
        append_row(ws, row)

# ---------- VIEW / EDIT / DELETE ----------
with tab_view:
    st.subheader("Your data")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### 🔍 Find rows to **edit/delete** by keyword")
    keyword = st.text_input("Search keyword (matches any column, case-insensitive)")
    if keyword:
        matches = search_rows(ws, keyword)
        if not matches:
            st.info("No matching rows found.")
        else:
            # Present a friendly selector
            labels = []
            for idx, row in matches:
                # Build a short label: Date | Brand | Qty | Cost | Vendor
                try:
                    lbl = f"{row[0]} | {row[1]} | {row[2]} | {row[5]} | {row[9]}"
                except Exception:
                    lbl = " | ".join(row[:6])
                labels.append(f"Row {idx}: {lbl}")

            selected = st.selectbox("Select a row", options=list(range(len(matches))), format_func=lambda i: labels[i])
            sel_idx_1based, sel_row = matches[selected]

            st.write("**Selected row values:**", sel_row)

            with st.expander("✏️ Edit this row"):
                # Map selected row into fields using current header ordering
                # We rely on DEFAULT_COLUMNS ordering for UI
                # sel_row includes header row? Already skipped header above.
                def _get(i, cast=str, default=""):
                    try:
                        return cast(sel_row[i])
                    except Exception:
                        return default

                e_date = st.date_input("Edit Date", value=pd.to_datetime(_get(0)).date() if _get(0) else date.today(), key=f"edit_date_{sel_idx_1based}")
                e_brand = st.text_input("Edit Brand", _get(1), key=f"edit_brand_{sel_idx_1based}")
                e_qty = st.number_input("Edit Quantity (sticks)", min_value=1, value=int(float(_get(2, float, 1))), step=1, key=f"edit_qty_{sel_idx_1based}")
                e_units = st.number_input("Edit Units per pack", min_value=1, value=int(float(_get(3, float, 20))), step=1, key=f"edit_units_{sel_idx_1based}")
                e_price = st.number_input("Edit Price per pack", min_value=0.0, value=float(_get(4, float, 0.0)), step=0.5, format="%.2f", key=f"edit_price_{sel_idx_1based}")
                e_payment = st.selectbox("Edit Payment Method", ["Cash", "Credit"], index=0 if _get(6) == "Cash" else 1, key=f"edit_payment_{sel_idx_1based}")
                e_paid = st.number_input("Edit Amount paid now", min_value=0.0, value=float(_get(7, float, 0.0)), step=0.5, format="%.2f", key=f"edit_paid_{sel_idx_1based}")
                e_vendor = st.text_input("Edit Vendor (optional)", _get(9), key=f"edit_vendor_{sel_idx_1based}")
                e_notes = st.text_area("Edit Notes (optional)", _get(10), key=f"edit_notes_{sel_idx_1based}")

                e_total = e_price * (e_qty / max(e_units, 1))
                e_outstanding = max(e_total - e_paid, 0.0)
                st.caption(f"Recomputed Total: **{e_total:.2f}** | Outstanding: **{e_outstanding:.2f}**")

                if st.button("Update row", type="primary"):
                    # Convert to 1-based index and ensure not header
                    if sel_idx_1based == 1:
                        st.warning("Header row is protected.")
                    else:
                        new_row = [
                            str(e_date), e_brand, int(e_qty), int(e_units),
                            float(e_price), float(e_total),
                            e_payment, float(e_paid), float(e_outstanding),
                            e_vendor, e_notes
                        ]
                        replace_row(ws, sel_idx_1based, new_row)

            with st.expander("🗑️ Delete this row"):
                if st.button("Confirm delete"):
                    if sel_idx_1based == 1:
                        st.warning("Header row is protected.")
                    else:
                        remove_row(ws, sel_idx_1based)

# ---------- ANALYTICS ----------
with tab_analytics:
    st.subheader("Trends & insights")
    if df.empty:
        st.info("Add entries to see analytics.")
    else:
        # Prep
        dfa = df.copy()
        dfa["Date"] = pd.to_datetime(dfa["Date"], errors="coerce")
        dfa = dfa.dropna(subset=["Date"])
        # KPIs
        total_sticks = int(dfa["Quantity"].sum())
        total_spend = float(dfa["TotalCost"].sum())
        outstanding = float(dfa["Outstanding"].sum())
        left, mid, right = st.columns(3)
        left.metric("Total sticks", f"{total_sticks}")
        mid.metric("Total spend", f"{total_spend:.2f}")
        right.metric("Outstanding credit", f"{outstanding:.2f}")

        # Charts
        by_day = dfa.groupby("Date", as_index=False).agg(
            sticks=("Quantity", "sum"),
            spend=("TotalCost", "sum")
        )
        st.line_chart(by_day.set_index("Date")[["sticks"]], height=220)
        st.line_chart(by_day.set_index("Date")[["spend"]], height=220)

        by_brand = dfa.groupby("Brand", as_index=False)["Quantity"].sum().sort_values("Quantity", ascending=False)
        st.bar_chart(by_brand.set_index("Brand"))
------------------------------------------------

import streamlit as st
import pandas as pd
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import SpreadsheetNotFound, APIError
from datetime import date

st.set_page_config(page_title="🚬 Smoking & Spend Tracker", layout="wide")

# ---------- Settings ----------
DEFAULT_COLUMNS = [
    "Date", "Brand", "Quantity", "UnitsPerPack",
    "PricePerPack", "TotalCost",
    "PaymentMethod", "AmountPaid", "Outstanding",
    "Vendor", "Notes"
]

def _err(msg, e=None):
    st.error(msg + (f"\n\nDetails: {e}" if e else ""))

# ---------- Google Sheets: Auth + Open ----------
def get_client():
    try:
        info = st.secrets["gcp_service_account"]  # stored in Secrets
    except Exception:
        _err("Secrets not found. Add your service account under **Settings → Secrets** as `[gcp_service_account]`.")
        return None
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        _err("Authentication failed. Check private key formatting and fields.", e)
        return None

def open_sheet(sheet_url_or_title: str):
    client = get_client()
    if not client:
        return None
    try:
        if sheet_url_or_title.startswith("http"):
            sh = client.open_by_url(sheet_url_or_title)
        else:
            sh = client.open(sheet_url_or_title)
        ws = sh.sheet1
        return ws
    except SpreadsheetNotFound:
        _err("Spreadsheet not found. Ensure the **service account email** has **Editor** access and the **URL/title** is correct.")
    except APIError as e:
        _err("Google Sheets API error (quota/permissions/invalid request).", e)
    except Exception as e:
        _err("Unexpected error opening spreadsheet.", e)
    return None

# ---------- Helpers ----------
def ensure_headers(ws):
    """Create headers if the sheet is empty."""
    try:
        values = ws.get_all_values()
        if not values:
            ws.append_row(DEFAULT_COLUMNS)
        else:
            # If first row is missing columns, upsert headers (non-destructive to data)
            current_headers = values[0]
            if current_headers != DEFAULT_COLUMNS:
                # Do not delete user data; just warn
                st.warning("Header row differs from expected schema. Using existing headers.")
    except Exception as e:
        _err("Failed to verify/create header row.", e)
        st.stop()

@st.cache_data(ttl=240)
def load_df(sheet_url_or_title: str):
    """Load dataframe from Google Sheet with caching"""
    ws = open_sheet(sheet_url_or_title)
    if ws is None:
        return pd.DataFrame(columns=DEFAULT_COLUMNS)
    
    try:
        values = ws.get_all_records()  # skips header row
        df = pd.DataFrame(values)
        # Backfill missing columns (if older data)
        for c in DEFAULT_COLUMNS:
            if c not in df.columns:
                df[c] = None
        # Type fixes
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            float_cols = ["Quantity", "UnitsPerPack", "PricePerPack", "TotalCost", "AmountPaid", "Outstanding"]
            for c in float_cols:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df[DEFAULT_COLUMNS] if not df.empty else pd.DataFrame(columns=DEFAULT_COLUMNS)
    except Exception as e:
        _err("Failed to read data from Google Sheet.", e)
        return pd.DataFrame(columns=DEFAULT_COLUMNS)

def clear_cache():
    load_df.clear()

def append_row(ws, row):
    try:
        ws.append_row(row)
        clear_cache()
        st.toast("✅ Added", icon="✅")
    except Exception as e:
        _err("Failed to add row.", e)

def replace_row(ws, idx_1based, row):
    """Replace data row at 1-based index (>=2). Keeps header intact."""
    try:
        ws.delete_rows(idx_1based)
        ws.insert_row(row, idx_1based)
        clear_cache()
        st.toast("✏️ Updated", icon="✏️")
    except Exception as e:
        _err("Failed to update row.", e)

def remove_row(ws, idx_1based):
    try:
        ws.delete_rows(idx_1based)
        clear_cache()
        st.toast("🗑️ Deleted", icon="🗑️")
    except Exception as e:
        _err("Failed to delete row.", e)

def search_rows(ws, keyword: str):
    """Return matches as list of (row_index_1based, row_values)."""
    try:
        data = ws.get_all_values()
        matches = []
        for i, row in enumerate(data, start=1):
            if i == 1:  # skip header
                continue
            if any(keyword.lower() in str(cell).lower() for cell in row):
                matches.append((i, row))
        return matches
    except Exception as e:
        _err("Failed to search rows.", e)
        return []

# ---------- UI ----------
st.title("🚬 Smoking Habit & Credit Spend Tracker")

     sheet_url_or_title = "https://docs.google.com/spreadsheets/d/1rcfWMw8XRYj9_3j3sAtyh1LIk1s-JiJDjhKweUisXJU/" 

if not sheet_url_or_title:
    st.info("Enter your Google Sheet URL or exact title to begin.")
    st.stop()

ws = open_sheet(sheet_url_or_title)
if ws is None:
    st.stop()

ensure_headers(ws)
df = load_df(sheet_url_or_title)

tab_add, tab_view, tab_analytics = st.tabs(["➕ Add Entry", "📄 View / Edit / Delete", "📈 Analytics"])

# ---------- ADD ----------
with tab_add:
    st.subheader("Add a new log")
    col1, col2, col3 = st.columns(3)
    with col1:
        in_date = st.date_input("Date", value=date.today())
        brand = st.text_input("Brand", placeholder="Marlboro, Classic, ...")
        quantity = st.number_input("Quantity (sticks)", min_value=1, step=1, value=1)
    with col2:
        units_per_pack = st.number_input("Units per pack", min_value=1, value=20, step=1)
        price_per_pack = st.number_input("Price per pack", min_value=0.0, step=0.5, format="%.2f")
        payment = st.selectbox("Payment Method", ["Cash", "Credit"])
    with col3:
        amount_paid = st.number_input("Amount paid now", min_value=0.0, step=0.5, format="%.2f")
        vendor = st.text_input("Vendor (optional)")
    notes = st.text_area("Notes (optional)")

    # Calculate total cost: (quantity / units_per_pack) * price_per_pack
    # This gives us the cost for the exact number of cigarettes purchased
    packs_purchased = quantity / max(units_per_pack, 1)
    total_cost = packs_purchased * price_per_pack
    outstanding = max(total_cost - amount_paid, 0.0)

    st.caption(f"**Calculation:** {quantity} sticks ÷ {units_per_pack} sticks/pack = {packs_purchased:.3f} packs")
    st.caption(f"**Total Cost:** {packs_purchased:.3f} packs × ₹{price_per_pack:.2f}/pack = **₹{total_cost:.2f}**")
    st.caption(f"**Outstanding:** ₹{total_cost:.2f} - ₹{amount_paid:.2f} = **₹{outstanding:.2f}**")

    if st.button("Save Entry", type="primary"):
        row = [
            str(in_date), brand, int(quantity), int(units_per_pack),
            float(price_per_pack), float(total_cost),
            payment, float(amount_paid), float(outstanding),
            vendor, notes
        ]
        append_row(ws, row)

# ---------- VIEW / EDIT / DELETE ----------
with tab_view:
    st.subheader("Your data")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("### 🔍 Find rows to **edit/delete** by keyword")
    keyword = st.text_input("Search keyword (matches any column, case-insensitive)", key="search_keyword")
    if keyword:
        matches = search_rows(ws, keyword)
        if not matches:
            st.info("No matching rows found.")
        else:
            # Present a friendly selector
            labels = []
            for idx, row in matches:
                # Build a short label: Date | Brand | Qty | Cost | Vendor
                try:
                    lbl = f"{row[0]} | {row[1]} | {row[2]} | {row[5]} | {row[9]}"
                except Exception:
                    lbl = " | ".join(row[:6])
                labels.append(f"Row {idx}: {lbl}")

            selected = st.selectbox("Select a row", options=list(range(len(matches))), format_func=lambda i: labels[i], key="row_selector")
            sel_idx_1based, sel_row = matches[selected]

            st.write("**Selected row values:**", sel_row)

            with st.expander("✏️ Edit this row"):
                # Map selected row into fields using current header ordering
                # We rely on DEFAULT_COLUMNS ordering for UI
                # sel_row includes header row? Already skipped header above.
                def _get(i, cast=str, default=""):
                    try:
                        return cast(sel_row[i])
                    except Exception:
                        return default

                e_date = st.date_input("Edit Date", value=pd.to_datetime(_get(0)).date() if _get(0) else date.today(), key=f"edit_date_{sel_idx_1based}")
                e_brand = st.text_input("Edit Brand", _get(1), key=f"edit_brand_{sel_idx_1based}")
                e_qty = st.number_input("Edit Quantity (sticks)", min_value=1, value=int(float(_get(2, float, 1))), step=1, key=f"edit_qty_{sel_idx_1based}")
                e_units = st.number_input("Edit Units per pack", min_value=1, value=int(float(_get(3, float, 20))), step=1, key=f"edit_units_{sel_idx_1based}")
                e_price = st.number_input("Edit Price per pack", min_value=0.0, value=float(_get(4, float, 0.0)), step=0.5, format="%.2f", key=f"edit_price_{sel_idx_1based}")
                e_payment = st.selectbox("Edit Payment Method", ["Cash", "Credit"], index=0 if _get(6) == "Cash" else 1, key=f"edit_payment_{sel_idx_1based}")
                e_paid = st.number_input("Edit Amount paid now", min_value=0.0, value=float(_get(7, float, 0.0)), step=0.5, format="%.2f", key=f"edit_paid_{sel_idx_1based}")
                e_vendor = st.text_input("Edit Vendor (optional)", _get(9), key=f"edit_vendor_{sel_idx_1based}")
                e_notes = st.text_area("Edit Notes (optional)", _get(10), key=f"edit_notes_{sel_idx_1based}")

                # Calculate totals with proper logic
                e_packs = e_qty / max(e_units, 1)
                e_total = e_packs * e_price
                e_outstanding = max(e_total - e_paid, 0.0)
                
                st.caption(f"**Calculation:** {e_qty} sticks ÷ {e_units} sticks/pack = {e_packs:.3f} packs")
                st.caption(f"**Total Cost:** {e_packs:.3f} packs × ₹{e_price:.2f}/pack = **₹{e_total:.2f}**")
                st.caption(f"**Outstanding:** ₹{e_total:.2f} - ₹{e_paid:.2f} = **₹{e_outstanding:.2f}**")

                if st.button("Update row", type="primary", key=f"update_btn_{sel_idx_1based}"):
                    # Convert to 1-based index and ensure not header
                    if sel_idx_1based == 1:
                        st.warning("Header row is protected.")
                    else:
                        new_row = [
                            str(e_date), e_brand, int(e_qty), int(e_units),
                            float(e_price), float(e_total),
                            e_payment, float(e_paid), float(e_outstanding),
                            e_vendor, e_notes
                        ]
                        replace_row(ws, sel_idx_1based, new_row)

            with st.expander("🗑️ Delete this row"):
                if st.button("Confirm delete", key=f"delete_btn_{sel_idx_1based}"):
                    if sel_idx_1based == 1:
                        st.warning("Header row is protected.")
                    else:
                        remove_row(ws, sel_idx_1based)

# ---------- ANALYTICS ----------
with tab_analytics:
    st.subheader("Trends & insights")
    if df.empty:
        st.info("Add entries to see analytics.")
    else:
        # Prep
        dfa = df.copy()
        dfa["Date"] = pd.to_datetime(dfa["Date"], errors="coerce")
        dfa = dfa.dropna(subset=["Date"])
        # KPIs with better handling of NaN values
        numeric_df = dfa.select_dtypes(include=[np.number]).fillna(0)
        total_sticks = int(numeric_df["Quantity"].sum()) if "Quantity" in numeric_df.columns else 0
        total_spend = float(numeric_df["TotalCost"].sum()) if "TotalCost" in numeric_df.columns else 0.0
        outstanding = float(numeric_df["Outstanding"].sum()) if "Outstanding" in numeric_df.columns else 0.0
        
        # Calculate average cost per stick
        avg_cost_per_stick = total_spend / max(total_sticks, 1)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Cigarettes", f"{total_sticks:,}")
        col2.metric("Total Spend", f"₹{total_spend:,.2f}")
        col3.metric("Outstanding Credit", f"₹{outstanding:,.2f}")
        col4.metric("Avg Cost/Stick", f"₹{avg_cost_per_stick:.2f}")

        # Charts with error handling
        if len(dfa) > 0:
            # Daily trends
            by_day = dfa.groupby("Date", as_index=False).agg(
                sticks=("Quantity", "sum"),
                spend=("TotalCost", "sum"),
                outstanding=("Outstanding", "sum")
            ).fillna(0)
            
            st.subheader("📊 Daily Consumption Trend")
            st.line_chart(by_day.set_index("Date")[["sticks"]], height=300)
            
            st.subheader("💰 Daily Spending Trend") 
            st.line_chart(by_day.set_index("Date")[["spend"]], height=300)
            
            st.subheader("📈 Outstanding Credit Trend")
            st.line_chart(by_day.set_index("Date")[["outstanding"]], height=300)

            # Brand analysis
            brand_analysis = dfa.groupby("Brand", as_index=False).agg(
                total_sticks=("Quantity", "sum"),
                total_spend=("TotalCost", "sum"),
                avg_price_per_stick=("TotalCost", lambda x: x.sum() / dfa.loc[x.index, "Quantity"].sum() if dfa.loc[x.index, "Quantity"].sum() > 0 else 0)
            ).sort_values("total_sticks", ascending=False).fillna(0)
            
            st.subheader("🏷️ Brand Analysis")
            st.dataframe(brand_analysis, use_container_width=True)
            st.bar_chart(brand_analysis.set_index("Brand")[["total_sticks"]], height=300)
        else:
            st.info("No data available for charts.")
