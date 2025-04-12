import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import requests
import os
import re
from PIL import Image

from drive_uploader import upload_receipt

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

def categorize_with_google(vendor):
    try:
        url = f"https://www.googleapis.com/customsearch/v1?q={vendor}&key={st.secrets['google_search']['api_key']}&cx={st.secrets['google_search']['cse_id']}"
        res = requests.get(url).json()
        desc = " ".join(item.get("snippet", "") for item in res.get("items", [])[:3]).lower()
        if any(x in desc for x in ["restaurant", "cafe", "coffee", "burger"]):
            return "Meals & Entertainment"
        elif any(x in desc for x in ["office supply", "staples", "stationery", "printer"]):
            return "Office Supplies"
        elif any(x in desc for x in ["hotel", "flight", "travel", "airbnb", "uber"]):
            return "Travel"
        elif any(x in desc for x in ["lawyer", "consultant", "accountant"]):
            return "Professional Fees"
        elif any(x in desc for x in ["fuel", "gas", "car rental"]):
            return "Automobile"
        elif any(x in desc for x in ["internet", "hydro", "electricity", "utility"]):
            return "Utilities"
        elif any(x in desc for x in ["rent", "lease"]):
            return "Rent"
        elif any(x in desc for x in ["salary", "payroll"]):
            return "Salaries/Wages"
        elif any(x in desc for x in ["ads", "marketing", "advertisement"]):
            return "Advertising"
        elif any(x in desc for x in ["insurance", "premium"]):
            return "Insurance"
        else:
            return "Miscellaneous"
    except Exception as e:
        return "Miscellaneous"

def extract_text_and_save(file, year):
    try:
        today_str = datetime.today().strftime("%d-%m-%Y")
        base_name = f"receipt_{today_str}"
        counter = 1
        while True:
            local_name = f"{base_name}_{counter}.png"
            local_path = os.path.join(LOCAL_SAVE_DIR, local_name)
            if not os.path.exists(local_path):
                break
            counter += 1

        
        # Save uploaded file first
        with open(local_path, "wb") as f:
            f.write(file.getbuffer())

        # Resize and compress if over 1MB
        def compress_image(path, max_size_kb=1024, quality=85, step=5):
            img = Image.open(path)
            img = img.convert("RGB")
            width, height = img.size
            while os.path.getsize(path) > max_size_kb * 1024 and quality > 10:
                new_width = int(width * 0.9)
                new_height = int(height * 0.9)
                img = img.resize((new_width, new_height), Image.ANTIALIAS)
                img.save(path, optimize=True, quality=quality)
                quality -= step
            return path

        compress_image(local_path)
    

        upload_receipt(local_path, year, "Uncategorized")

        with open(local_path, 'rb') as image_file:
            response = requests.post(
                'https://api.ocr.space/parse/image',
                files={'filename': image_file},
                data={'apikey': st.secrets["ocr"]["api_key"], 'language': 'eng'},
            )
        result = response.json()
        if result['IsErroredOnProcessing']:
            st.error("OCR API Error: " + result['ErrorMessage'][0])
            return f"OCR Error: {result['ErrorMessage'][0]}", None, None, 0.0

        parsed_text = result['ParsedResults'][0]['ParsedText']
        vendor_line = parsed_text.splitlines()[0].strip()
        detected_category = categorize_with_google(vendor_line)

        amount = 0.01
        for line in parsed_text.splitlines():
            if "total" in line.lower() and "$" in line:
                found = re.findall(r"\$?([0-9]+\.[0-9]{2})", line)
                if found:
                    try:
                        amount = max(map(float, found))
                        break
                    except:
                        continue
        else:
            numbers = re.findall(r"\d+\.\d{2}", parsed_text)
            if numbers:
                amount = max(map(float, numbers))

        return parsed_text, local_path, detected_category, amount

    except Exception as e:
        st.error(f"OCR failed: {e}")
        return f"OCR Error: {e}", None, None, 0.01

st.title("Canadian Corp Expense Tracker (Google-Powered Categorization)")
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
    st.header("Scan Receipt (Auto-Category via Google Search)")
    uploaded_file = st.file_uploader("Upload receipt image", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        year = datetime.now().year
        with st.spinner("Reading and uploading receipt..."):
            text, local_path, category, amount = extract_text_and_save(uploaded_file, year)
            if text.startswith("OCR Error"):
                st.error("Could not process receipt.")
            else:
                st.success("Receipt saved and uploaded to Google Drive.")
                st.text_area("Extracted Text", text, height=150)
                st.subheader("Confirm Detected Details")
                date = st.date_input("Date", value=datetime.today())
                description = st.text_input("Description", value=text[:100])
                category = st.selectbox("Category", list(CATEGORIES.keys()), index=list(CATEGORIES.keys()).index(category))
                amount = st.number_input("Amount ($)", value=amount if amount > 0 else 0.01, min_value=0.01, format="%.2f")
                if st.button("Save Expense"):
                    insert_expense(year, date.isoformat(), category, description, amount)
                    st.success("Google-powered categorized expense saved!")

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