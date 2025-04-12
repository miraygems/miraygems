import streamlit as st
import sqlite3
import os
from datetime import datetime
from PIL import Image
from utils import init_db, insert_expense, get_summary, extract_text_and_save, upload_receipt

DB_FILE = "expenses.db"
LOCAL_SAVE_DIR = "receipts"
CATEGORIES = {
    "Meals and Entertainment": 1000,
    "Travel": 2000,
    "Supplies": 1500,
    "Utilities": 1200,
    "Miscellaneous": 800
}
from utils import download_db_from_drive
download_db_from_drive()

init_db()

st.title("Canadian Tax Expense Tracker")

menu = st.sidebar.selectbox("Menu", ["Enter Expense", "Upload Receipt", "View Summary"])

if menu == "Enter Expense":
    st.header("Enter New Expense")
    with st.form("manual_expense_form"):
        year = st.number_input("Tax Year", min_value=2000, max_value=2100, value=datetime.now().year, key="manual_entry_year_v1")
        date = st.date_input("Expense Date", key="manual_entry_date_v1")
        category = st.selectbox("Category", list(CATEGORIES.keys()), key="manual_entry_category_v1")
        description = st.text_input("Description", key="manual_entry_description_v1")
        amount = st.number_input("Amount ($)", min_value=0.01, format="%.2f", key="manual_entry_amount_v1")
        manual_receipt_file = st.file_uploader("Optional: Upload receipt image manually", type=["jpg", "jpeg", "png"], key="manual_entry_receipt_v1")
        submitted_manual = st.form_submit_button("Save Expense")
        if submitted_manual:
            insert_expense(year, date.isoformat(), category, description, amount)
            st.success("Expense saved successfully!")
            if manual_receipt_file:
                today_str = datetime.today().strftime("%d-%m-%Y")
                base_name = f"receipt_{today_str}"
                counter = 1
                while True:
                    local_name = f"{base_name}_{counter}.png"
                    local_path = os.path.join(LOCAL_SAVE_DIR, local_name)
                    if not os.path.exists(local_path):
                        break
                    counter += 1
                with open(local_path, "wb") as f:
                    f.write(manual_receipt_file.getbuffer())
                img = Image.open(local_path).convert("RGB")
                if img.width > 1024:
                    ratio = 1024 / float(img.width)
                    height = int(float(img.height) * ratio)
                    img = img.resize((1024, height), Image.Resampling.LANCZOS)
                    img.save(local_path)
                upload_receipt(local_path, year, category)

elif menu == "Upload Receipt":
    st.header("Upload Receipt Image")
    file = st.file_uploader("Upload receipt image", type=["jpg", "jpeg", "png"], key="receipt_file")
    if file is not None:
        image = Image.open(file).convert("RGB")
        if image.width > 1024:
            ratio = 1024 / float(image.width)
            height = int((float(image.height) * float(ratio)))
            image = image.resize((1024, height), Image.Resampling.LANCZOS)
        temp_path = os.path.join(LOCAL_SAVE_DIR, "temp_receipt.png")
        image.save(temp_path)
        with st.spinner("Extracting text from receipt..."):
            text, local_path, category, amount = extract_text_and_save(temp_path)
        if text:
            st.success("Text extracted successfully!")
            st.text_area("Receipt Text", text)
            st.write(f"**Detected Category**: {category}")
            st.write(f"**Detected Amount**: ${amount:.2f}")
        else:
            st.error("Could not process receipt.")

elif menu == "View Summary":
    st.header("Year-End Expense Summary")
    year = st.number_input("Tax Year", min_value=2000, max_value=2100, value=datetime.now().year, key="summary_year_v1")
    df = get_summary(year)
    if df is not None and not df.empty:
        st.dataframe(df)
        for category, limit in CATEGORIES.items():
            total = df[df['category'] == category]['amount'].sum()
            st.write(f"{category}: ${total:.2f} / Max Allowed: ${limit}")
    else:
        st.info("No expenses found for the selected year.")
