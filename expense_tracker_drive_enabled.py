import streamlit as st
import os
from datetime import datetime
from PIL import Image
import pandas as pd
import matplotlib.pyplot as plt

from utils import (
    init_db, insert_expense, get_summary, extract_text_and_save,
    upload_receipt, download_db_from_drive
)

DB_FILE = "expenses.db"
LOCAL_SAVE_DIR = "receipts"

CATEGORIES = {
    "Meals and Entertainment": 1000,
    "Travel": 2000,
    "Supplies": 1500,
    "Utilities": 1200,
    "Miscellaneous": 800
}

os.makedirs(LOCAL_SAVE_DIR, exist_ok=True)
download_db_from_drive()
init_db()

st.set_page_config(page_title="Canadian Tax Expense Tracker", layout="wide")
st.title("Canadian Tax Expense Tracker")

menu = st.sidebar.radio("Navigate", ["Enter Expense", "Upload Receipt", "View Summary"])

if menu == "Enter Expense":
    st.subheader("Manual Entry")
    with st.form("manual_expense_form"):
        col1, col2 = st.columns(2)
        with col1:
            year = st.number_input("Tax Year", min_value=2000, max_value=2100, value=datetime.now().year, key="manual_year")
            date = st.date_input("Expense Date", key="manual_date")
        with col2:
            category = st.selectbox("Category", list(CATEGORIES.keys()), key="manual_category")
            amount = st.number_input("Amount ($)", min_value=0.01, format="%.2f", key="manual_amount")
        description = st.text_input("Short Description", key="manual_description")
        manual_receipt = st.file_uploader("Optional: Upload Receipt Image", type=["jpg", "jpeg", "png"], key="manual_receipt")
        submitted = st.form_submit_button("Save Expense")
        
        if submitted:
            insert_expense(year, date.isoformat(), category, description, amount)
            st.success("Expense saved to database.")
            if manual_receipt:
                today_str = datetime.today().strftime("%d-%m-%Y")
                filename = f"manual_{today_str}_{category.replace(' ', '_')}.png"
                local_path = os.path.join(LOCAL_SAVE_DIR, filename)
                with open(local_path, "wb") as f:
                    f.write(manual_receipt.getbuffer())
                img = Image.open(local_path).convert("RGB")
                if img.width > 1024:
                    ratio = 1024 / float(img.width)
                    height = int(float(img.height) * ratio)
                    img = img.resize((1024, height), Image.Resampling.LANCZOS)
                    img.save(local_path)
                upload_receipt(local_path, year, category)
                st.info("Receipt uploaded to Drive.")

elif menu == "Upload Receipt":
    st.subheader("Upload & Scan Receipt")
    file = st.file_uploader("Choose a receipt image", type=["jpg", "jpeg", "png"], key="upload_receipt")
    if file:
        image = Image.open(file).convert("RGB")
        if image.width > 1024:
            ratio = 1024 / float(image.width)
            height = int(float(image.height) * ratio)
            image = image.resize((1024, height), Image.Resampling.LANCZOS)
        temp_path = os.path.join(LOCAL_SAVE_DIR, "temp_receipt.png")
        image.save(temp_path)
        
        with st.spinner("Processing receipt..."):
            text, local_path, category, amount = extract_text_and_save(temp_path)

        if text:
            st.success("Receipt scanned successfully.")
            with st.expander("Show Extracted Text"):
                st.text_area("Extracted Text", text, height=200)
            st.write(f"Predicted Category: {category}")
            st.write(f"Detected Amount: ${amount:.2f}")
            insert_expense(datetime.now().year, datetime.now().isoformat(), category, "OCR Upload", amount)
            upload_receipt(local_path, datetime.now().year, category)
            st.info("Saved and uploaded.")
        else:
            st.error("Could not extract text.")

elif menu == "View Summary":
    st.subheader("Expense Summary")
    year = st.selectbox("Select Tax Year", range(datetime.now().year, 1999, -1), key="summary_year")
    df = get_summary(year)

    if df is not None and not df.empty:
        # New filters
        st.markdown("#### Filter Your Data")
        with st.expander("Filters"):
            available_categories = df["category"].unique().tolist()
            selected_categories = st.multiselect("Select Categories", options=available_categories, default=available_categories)
            start_date = st.date_input("Start Date", datetime.strptime(f"{year}-01-01", "%Y-%m-%d"))
            end_date = st.date_input("End Date", datetime.strptime(f"{year}-12-31", "%Y-%m-%d"))

        # Apply filters
        df["date"] = pd.to_datetime(df["date"])
        filtered_df = df[
            (df["category"].isin(selected_categories)) &
            (df["date"] >= pd.to_datetime(start_date)) &
            (df["date"] <= pd.to_datetime(end_date))
        ]

        st.markdown(f"#### Filtered Summary: {len(filtered_df)} entries")
        st.dataframe(filtered_df.style.format({"amount": "${:.2f}"}), use_container_width=True)

        with st.expander("Category Breakdown"):
            for cat, limit in CATEGORIES.items():
                total = filtered_df[filtered_df["category"] == cat]["amount"].sum()
                pct = (total / limit * 100) if limit else 0
                st.write(f"{cat}: ${total:.2f} / ${limit} ({pct:.1f}%)")
                st.progress(min(int(pct), 100))

        with st.expander("Download Data"):
            csv = filtered_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "filtered_summary.csv", "text/csv")

            try:
                import io
                import xlsxwriter
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    filtered_df.to_excel(writer, index=False, sheet_name="FilteredSummary")
                    writer.save()
                st.download_button("Download Excel", output.getvalue(), "filtered_summary.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except ImportError:
                st.warning("Excel export not available (xlsxwriter not installed)")

        with st.expander("Spending Chart"):
            fig, ax = plt.subplots(figsize=(6, 4))
            chart_data = filtered_df.groupby("category")["amount"].sum()
            if not chart_data.empty:
                chart_data.plot(kind="bar", ax=ax)
                ax.set_ylabel("Amount ($)")
                ax.set_title(f"Spending by Category - Filtered")
                st.pyplot(fig)
            else:
                st.info("No data to display chart.")
    else:
        st.info("No data found for this year.")

    st.subheader("Expense Summary")
    year = st.selectbox("Select Tax Year", range(datetime.now().year, 1999, -1), key="summary_year")
    df = get_summary(year)
    
    if df is not None and not df.empty:
        st.dataframe(df.style.format({"amount": "${:.2f}"}), use_container_width=True)

        # Breakdown section
        with st.expander("Category Breakdown"):
            for cat, limit in CATEGORIES.items():
                total = df[df["category"] == cat]["amount"].sum()
                pct = (total / limit * 100) if limit else 0
                st.write(f"{cat}: ${total:.2f} / ${limit} ({pct:.1f}%)")
                st.progress(min(int(pct), 100))

        # Export section
        with st.expander("Download Data"):
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, "summary.csv", "text/csv")

            try:
                import io
                import xlsxwriter
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    df.to_excel(writer, index=False, sheet_name="Summary")
                    writer.save()
                st.download_button("Download Excel", output.getvalue(), "summary.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except ImportError:
                st.warning("Excel export not available (xlsxwriter not installed)")

        # Charts
        with st.expander("Spending Chart"):
            fig, ax = plt.subplots(figsize=(6, 4))
            chart_data = df.groupby("category")["amount"].sum()
            chart_data.plot(kind="bar", ax=ax)
            ax.set_ylabel("Amount ($)")
            ax.set_title(f"Spending by Category - {year}")
            st.pyplot(fig)

    else:
        st.info("No data found for this year.")
