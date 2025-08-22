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
        st.rerun()  # Refresh the page to show new data
    except Exception as e:
        _err("Failed to add row.", e)

def replace_row(ws, idx_1based, row):
    """Replace data row at 1-based index (>=2). Keeps header intact."""
    try:
        ws.delete_rows(idx_1based)
        ws.insert_row(row, idx_1based)
        clear_cache()
        st.toast("✏️ Updated", icon="✏️")
        st.rerun()  # Refresh the page to show updated data
    except Exception as e:
        _err("Failed to update row.", e)

def remove_row(ws, idx_1based):
    try:
        ws.delete_rows(idx_1based)
        clear_cache()
        st.toast("🗑️ Deleted", icon="🗑️")
        st.rerun()  # Refresh the page to show updated data
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

# Sidebar for Google Sheet connection
with st.sidebar:
    st.header("Connect to Google Sheet")
    sheet_url_or_title = st.text_input(
        "Paste Spreadsheet URL (recommended) or exact title",
        value="https://docs.google.com/spreadsheets/d/1rcfWMw8XRYj9_3j3sAtyh1LIk1s-JiJDjhKweUisXJU/",
        placeholder="https://docs.google.com/spreadsheets/d/...",
    )
    st.caption("Make sure you **shared** the sheet with your service account email (Editor).")
    
    # Add refresh button
    if st.button("🔄 Refresh Data"):
        clear_cache()
        st.rerun()

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
        price_per_pack = st.number_input("Price per pack (₹)", min_value=0.0, step=0.5, format="%.2f")
        payment = st.selectbox("Payment Method", ["Cash", "Credit"])
    with col3:
        amount_paid = st.number_input("Amount paid now (₹)", min_value=0.0, step=0.5, format="%.2f")
        vendor = st.text_input("Vendor (optional)")
    notes = st.text_area("Notes (optional)")

    # Calculate total cost: (quantity / units_per_pack) * price_per_pack
    # This gives us the cost for the exact number of cigarettes purchased
    if units_per_pack > 0 and price_per_pack >= 0:
        packs_purchased = quantity / units_per_pack
        total_cost = packs_purchased * price_per_pack
        outstanding = max(total_cost - amount_paid, 0.0)

        # Display calculations
        st.divider()
        st.markdown("### 💰 Calculation Breakdown")
        col_calc1, col_calc2 = st.columns(2)
        
        with col_calc1:
            st.info(f"""
            **Step 1:** Packs purchased  
            {quantity} sticks ÷ {units_per_pack} sticks/pack = **{packs_purchased:.3f} packs**
            
            **Step 2:** Total cost  
            {packs_purchased:.3f} packs × ₹{price_per_pack:.2f}/pack = **₹{total_cost:.2f}**
            """)
        
        with col_calc2:
            st.success(f"""
            **Step 3:** Outstanding amount  
            ₹{total_cost:.2f} - ₹{amount_paid:.2f} = **₹{outstanding:.2f}**
            
            **Cost per stick:** ₹{total_cost/quantity:.2f}
            """)

        if st.button("💾 Save Entry", type="primary", use_container_width=True):
            if brand.strip():  # Ensure brand is not empty
                row = [
                    str(in_date), brand.strip(), int(quantity), int(units_per_pack),
                    float(price_per_pack), float(total_cost),
                    payment, float(amount_paid), float(outstanding),
                    vendor.strip(), notes.strip()
                ]
                append_row(ws, row)
            else:
                st.error("Please enter a brand name.")

# ---------- VIEW / EDIT / DELETE ----------
with tab_view:
    st.subheader("📊 Your Data")
    
    if not df.empty:
        # Format the dataframe for better display
        display_df = df.copy()
        if "Date" in display_df.columns:
            display_df["Date"] = pd.to_datetime(display_df["Date"]).dt.strftime("%Y-%m-%d")
        
        # Format currency columns
        currency_cols = ["PricePerPack", "TotalCost", "AmountPaid", "Outstanding"]
        for col in currency_cols:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: f"₹{x:.2f}" if pd.notnull(x) else "₹0.00")
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No data found. Add some entries first.")

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
                    date_str = row[0] if len(row) > 0 else "No date"
                    brand_str = row[1] if len(row) > 1 else "No brand"
                    qty_str = row[2] if len(row) > 2 else "0"
                    cost_str = f"₹{float(row[5]):.2f}" if len(row) > 5 and row[5] else "₹0.00"
                    vendor_str = row[9] if len(row) > 9 and row[9] else "No vendor"
                    lbl = f"{date_str} | {brand_str} | {qty_str} sticks | {cost_str} | {vendor_str}"
                except Exception:
                    lbl = " | ".join(str(cell) for cell in row[:6])
                labels.append(f"Row {idx}: {lbl}")

            selected = st.selectbox("Select a row", options=list(range(len(matches))), format_func=lambda i: labels[i], key="row_selector")
            sel_idx_1based, sel_row = matches[selected]

            st.write("**Selected row values:**")
            # Display selected row in a nice format
            if len(sel_row) >= len(DEFAULT_COLUMNS):
                row_data = {}
                for i, col in enumerate(DEFAULT_COLUMNS):
                    row_data[col] = sel_row[i] if i < len(sel_row) else ""
                st.json(row_data)

            col_edit, col_delete = st.columns(2)
            
            with col_edit:
                with st.expander("✏️ Edit this row", expanded=True):
                    # Map selected row into fields using current header ordering
                    def _get(i, cast=str, default=""):
                        try:
                            if i < len(sel_row):
                                return cast(sel_row[i]) if sel_row[i] != "" else cast(default)
                            return cast(default)
                        except Exception:
                            return cast(default)

                    try:
                        date_value = pd.to_datetime(_get(0)).date() if _get(0) else date.today()
                    except:
                        date_value = date.today()

                    e_date = st.date_input("Edit Date", value=date_value, key=f"edit_date_{sel_idx_1based}")
                    e_brand = st.text_input("Edit Brand", _get(1), key=f"edit_brand_{sel_idx_1based}")
                    e_qty = st.number_input("Edit Quantity (sticks)", min_value=1, value=max(1, int(float(_get(2, float, 1)))), step=1, key=f"edit_qty_{sel_idx_1based}")
                    e_units = st.number_input("Edit Units per pack", min_value=1, value=max(1, int(float(_get(3, float, 20)))), step=1, key=f"edit_units_{sel_idx_1based}")
                    e_price = st.number_input("Edit Price per pack (₹)", min_value=0.0, value=max(0.0, float(_get(4, float, 0.0))), step=0.5, format="%.2f", key=f"edit_price_{sel_idx_1based}")
                    e_payment = st.selectbox("Edit Payment Method", ["Cash", "Credit"], index=0 if _get(6) == "Cash" else 1, key=f"edit_payment_{sel_idx_1based}")
                    e_paid = st.number_input("Edit Amount paid now (₹)", min_value=0.0, value=max(0.0, float(_get(7, float, 0.0))), step=0.5, format="%.2f", key=f"edit_paid_{sel_idx_1based}")
                    e_vendor = st.text_input("Edit Vendor (optional)", _get(9), key=f"edit_vendor_{sel_idx_1based}")
                    e_notes = st.text_area("Edit Notes (optional)", _get(10), key=f"edit_notes_{sel_idx_1based}")

                    # Calculate totals with proper logic
                    if e_units > 0:
                        e_packs = e_qty / e_units
                        e_total = e_packs * e_price
                        e_outstanding = max(e_total - e_paid, 0.0)
                        
                        st.markdown("### 💰 Updated Calculations")
                        st.info(f"""
                        **Packs:** {e_qty} ÷ {e_units} = {e_packs:.3f} packs  
                        **Total Cost:** {e_packs:.3f} × ₹{e_price:.2f} = **₹{e_total:.2f}**  
                        **Outstanding:** ₹{e_total:.2f} - ₹{e_paid:.2f} = **₹{e_outstanding:.2f}**
                        """)

                        if st.button("💾 Update Row", type="primary", key=f"update_btn_{sel_idx_1based}"):
                            if sel_idx_1based == 1:
                                st.warning("Header row is protected.")
                            elif e_brand.strip():
                                new_row = [
                                    str(e_date), e_brand.strip(), int(e_qty), int(e_units),
                                    float(e_price), float(e_total),
                                    e_payment, float(e_paid), float(e_outstanding),
                                    e_vendor.strip(), e_notes.strip()
                                ]
                                replace_row(ws, sel_idx_1based, new_row)
                            else:
                                st.error("Please enter a brand name.")

            with col_delete:
                with st.expander("🗑️ Delete this row"):
                    st.warning("⚠️ This action cannot be undone!")
                    st.write("You are about to delete:")
                    st.code(f"Row {sel_idx_1based}: {labels[selected].split(': ', 1)[1]}")
                    
                    if st.button("🗑️ Confirm Delete", type="secondary", key=f"delete_btn_{sel_idx_1based}"):
                        if sel_idx_1based == 1:
                            st.warning("Header row is protected.")
                        else:
                            remove_row(ws, sel_idx_1based)

# ---------- ANALYTICS ----------
with tab_analytics:
    st.subheader("📈 Trends & Insights")
    
    if df.empty:
        st.info("Add entries to see analytics.")
    else:
        # Prep data
        dfa = df.copy()
        dfa["Date"] = pd.to_datetime(dfa["Date"], errors="coerce")
        dfa = dfa.dropna(subset=["Date"])
        
        if len(dfa) == 0:
            st.warning("No valid date entries found.")
            st.stop()
        
        # Fill NaN values with 0 for numeric columns
        numeric_cols = ["Quantity", "UnitsPerPack", "PricePerPack", "TotalCost", "AmountPaid", "Outstanding"]
        for col in numeric_cols:
            if col in dfa.columns:
                dfa[col] = pd.to_numeric(dfa[col], errors="coerce").fillna(0)
        
        # KPIs
        total_sticks = int(dfa["Quantity"].sum())
        total_spend = float(dfa["TotalCost"].sum())
        outstanding = float(dfa["Outstanding"].sum())
        avg_cost_per_stick = total_spend / max(total_sticks, 1)
        total_days = (dfa["Date"].max() - dfa["Date"].min()).days + 1
        avg_sticks_per_day = total_sticks / max(total_days, 1)
        
        # Display KPIs
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Cigarettes", f"{total_sticks:,}")
        col2.metric("Total Spend", f"₹{total_spend:,.2f}")
        col3.metric("Outstanding Credit", f"₹{outstanding:,.2f}")
        col4.metric("Avg Cost/Stick", f"₹{avg_cost_per_stick:.2f}")
        col5.metric("Avg Sticks/Day", f"{avg_sticks_per_day:.1f}")

        # Charts with error handling
        if len(dfa) > 0:
            st.divider()
            
            # Daily trends
            by_day = dfa.groupby(dfa["Date"].dt.date, as_index=False).agg(
                sticks=("Quantity", "sum"),
                spend=("TotalCost", "sum"),
                outstanding=("Outstanding", "sum")
            )
            by_day["Date"] = pd.to_datetime(by_day["Date"])
            
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.subheader("📊 Daily Consumption")
                if len(by_day) > 0:
                    st.line_chart(by_day.set_index("Date")[["sticks"]], height=300)
                else:
                    st.info("No consumption data available.")
            
            with col_chart2:
                st.subheader("💰 Daily Spending")
                if len(by_day) > 0:
                    st.line_chart(by_day.set_index("Date")[["spend"]], height=300)
                else:
                    st.info("No spending data available.")
            
            st.subheader("📈 Outstanding Credit Over Time")
            if len(by_day) > 0:
                st.line_chart(by_day.set_index("Date")[["outstanding"]], height=300)
            else:
                st.info("No outstanding credit data available.")

            # Brand analysis
            if "Brand" in dfa.columns and len(dfa) > 0:
                brand_stats = dfa.groupby("Brand").agg(
                    total_sticks=("Quantity", "sum"),
                    total_spend=("TotalCost", "sum"),
                    total_outstanding=("Outstanding", "sum"),
                    avg_price_per_pack=("PricePerPack", "mean"),
                    entries=("Brand", "count")
                ).round(2)
                
                brand_stats["avg_cost_per_stick"] = (brand_stats["total_spend"] / brand_stats["total_sticks"]).round(2)
                brand_stats = brand_stats.sort_values("total_sticks", ascending=False)
                
                st.subheader("🏷️ Brand Analysis")
                st.dataframe(
                    brand_stats.style.format({
                        'total_spend': '₹{:.2f}',
                        'total_outstanding': '₹{:.2f}',
                        'avg_price_per_pack': '₹{:.2f}',
                        'avg_cost_per_stick': '₹{:.2f}'
                    }), 
                    use_container_width=True
                )
                
                if len(brand_stats) > 0:
                    st.bar_chart(brand_stats[["total_sticks"]], height=300)
        else:
            st.info("No data available for charts.")
