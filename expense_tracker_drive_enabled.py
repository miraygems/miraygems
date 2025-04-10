import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import tempfile
from PIL import Image
import pytesseract
import re
import os
import uuid
import base64

from drive_uploader import upload_receipt

# CRA Deductible Rules
CATEGORIES = {
    "Meals & Entertainment": 0.50,
    "Office Supplies": 1.00,
    "Travel": 1.00,
    "Automobile": 0.50,
    "Professional Fees": 1.00,
    "Rent": 1.00,
    "Salaries/Wages": 1.00,
    "Utilities": 1.00,
    "Advertising": 1.00,
    "Insurance": 1.00,
    "Miscellaneous": 1.00,
}

DB_FILE = "expenses.db"
LOCAL_SAVE_DIR = "receipts"
os.makedirs(LOCAL_SAVE_DIR, exist_ok=True)

# Initialize DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        year INTEGER,
        date TEXT,
        category TEXT,
        description TEXT,
        amount REAL
    )
    """)
    conn.commit()
    conn.close()

def insert_expense(year, date, category, description, amount):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT INTO expenses (year, date, category, description, amount) VALUES (?, ?, ?, ?, ?)",
                (year, date, category, description, amount))
    conn.commit()
    conn.close()

def get_summary(year):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM expenses WHERE year = ?", conn, params=(year,))
    conn.close()
    if df.empty:
        return pd.DataFrame()
    df['deductible'] = df.apply(lambda row: round(row['amount'] * CATEGORIES.get(row['category'], 1.0), 2), axis=1)
    summary = df.groupby('category').agg(
        total_spent=pd.NamedAgg(column='amount', aggfunc='sum'),
        deductible_total=pd.NamedAgg(column='deductible', aggfunc='sum')
    ).reset_index()
    return summary

# OCR using pytesseract
def extract_text_and_save(file, year, category):
    try:
        img = Image.open(file).convert('L')
        today_str = datetime.today().strftime("%d-%m-%Y")
        base_name = f"receipt_{today_str}"
        counter = 1

        while True:
            local_name = f"{base_name}_{counter}.png"
            local_path = os.path.join(LOCAL_SAVE_DIR, local_name)
            if not os.path.exists(local_path):
                break
            counter += 1

        img.save(local_path)
        text = pytesseract.image_to_string(img)

        # Upload to Google Drive
        upload_receipt(local_path, year, category)

        return text, local_path
    except Exception as e:
        st.error(f"OCR failed: {e}")
        return f"OCR Error: {e}", None

# --- Streamlit UI ---
st.title("Canadian Corp Expense Tracker (with Google Drive Upload)")

init_db()

menu = st.sidebar.selectbox("Menu", ["Enter Expense", "Upload Receipt", "View Summary"])

if menu == "Enter Expense":
    st.header("Enter New Expense")
    year = st.number_input("Tax Year", min_value=2000, max_value=2100, value=datetime.now().year)
    date = st.date_input("Expense Date")
    category = st.selectbox("Category", list(CATEGORIES.keys()))
    description = st.text_input("Description")
    amount = st.number_input("Amount ($)", min_value=0.01, format="%.2f")

    if st.button("Save Expense"):
        insert_expense(year, date.isoformat(), category, description, amount)
        st.success("Expense saved successfully!")

elif menu == "Upload Receipt":
    st.header("Scan Receipt (Auto-Category)")
    uploaded_file = st.file_uploader("Upload receipt image", type=["jpg", "jpeg", "png"])

    if uploaded_file:
        year = datetime.now().year
        category = st.selectbox("Detected or Expected Category", list(CATEGORIES.keys()), index=0)

        with st.spinner("Reading and uploading receipt..."):
            text, local_path = extract_text_and_save(uploaded_file, year, category)
            if text.startswith("OCR Error"):
                st.error("Could not process receipt.")
            else:
                st.success("Receipt saved and uploaded to Google Drive.")
                st.text_area("Extracted Text", text, height=150)

                amount_match = re.search(r"total\s*\$?([0-9]+\.?[0-9]*)", text, re.IGNORECASE)
                amount = float(amount_match.group(1)) if amount_match else 0.0

                st.subheader("Confirm Detected Details")
                date = st.date_input("Date", value=datetime.today())
                description = st.text_input("Description", value=text[:100])
                amount = st.number_input("Amount ($)", value=amount if amount > 0 else 0.01, min_value=0.01, format="%.2f")

                if st.button("Save Expense"):
                    insert_expense(year, date.isoformat(), category, description, amount)
                    st.success("Auto-categorized expense saved!")

elif menu == "View Summary":
    st.header("Year-End Expense Summary")
    year = st.number_input("Select Year", min_value=2000, max_value=2100, value=datetime.now().year)
    df = get_summary(year)
    if not df.empty:
        st.dataframe(df)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", csv, f"summary_{year}.csv", "text/csv")
    else:
        st.info("No expenses found for this year.")