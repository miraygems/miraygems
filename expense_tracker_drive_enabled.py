import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import requests
import os
import re
from PIL import Image
from PIL import ImageOps

from drive_uploader import upload_receipt, get_drive_service, find_or_create_folder, upload_file_to_folder

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

def download_db_from_drive():
    try:
        import io
        from googleapiclient.http import MediaIoBaseDownload
        service = get_drive_service()
        folder_id = find_or_create_folder("Receipts")
        query = f"name = 'expenses.db' and '{folder_id}' in parents"
        result = service.files().list(q=query, fields="files(id, name)").execute()
        files = result.get('files', [])
        if files:
            file_id = files[0]['id']
            request = service.files().get_media(fileId=file_id)
            with open("expenses.db", "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
    except Exception as e:
        print("DB not found or download error:", e)

def upload_db_to_drive():
    try:
        upload_file_to_folder("expenses.db", "Receipts")
    except Exception as e:
        print("Upload error:", e)

def init_db():
    download_db_from_drive()
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
    upload_db_to_drive()

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

def compress_image(path, max_size_kb=1024, quality=85, step=5):
    img = Image.open(path)
    img = img.convert("RGB")
    width, height = img.size
    while os.path.getsize(path) > max_size_kb * 1024 and quality > 10:
        new_width = int(width * 0.9)
        new_height = int(height * 0.9)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        img.save(path, optimize=True, quality=quality)
        quality -= step
    return path

def extract_text_and_save(file, year):
    try:
        
        # Try to extract date from text (format: dd-mm-yyyy or yyyy-mm-dd or mm/dd/yyyy)
        import datetime
        date_match = re.search(r"(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})", parsed_text)
        if date_match:
            receipt_date = date_match.group(0).replace("/", "-")
        else:
            receipt_date = datetime.datetime.today().strftime("%d-%m-%Y")
        base_name = f"receipt_{receipt_date}"
    
        base_name = f"receipt_{today_str}"
        counter = 1
        while True:
            local_name = f"{base_name}_{counter}.png"
            local_path = os.path.join(LOCAL_SAVE_DIR, local_name)
            if not os.path.exists(local_path):
                break
            counter += 1

        
        # Save original uploaded file
        with open(local_path, "wb") as f:
            f.write(file.getbuffer())

        # Resize quickly to 1024px width if needed
        img = Image.open(local_path)
        img = img.convert("RGB")
        if img.width > 1024:
            ratio = 1024 / float(img.width)
            height = int((float(img.height) * float(ratio)))
            img = img.resize((1024, height), Image.Resampling.LANCZOS)
            img.save(local_path)
    

        compress_image(local_path)
        

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

        
        if not result.get("ParsedResults") or len(result["ParsedResults"]) == 0:
            st.error("OCR failed: No text could be extracted from the image.")
            return "OCR Error: No text extracted", None, None, 0.0
        parsed_text = result["ParsedResults"][0]["ParsedText"]
    
        
        vendor_line = next((line.strip() for line in parsed_text.splitlines() if len(line.strip().split()) > 1 and any(c.isalpha() for c in line)), "Vendor")
    
        detected_category = categorize_with_google(vendor_line)
        upload_receipt(local_path, year, detected_category)

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

# Streamlit UI
st.title("Canadian Corp Expense Tracker (Google-Powered Categorization)")
init_db()

menu = st.sidebar.selectbox("Menu", ["Enter Expense", "Upload Receipt", "View Summary"])


if menu == "Enter Expense":
    st.header("Enter New Expense")
    year = st.number_input("Tax Year", min_value=2000, max_value=2100, value=datetime.now().year, key="manual_year")
    date = st.date_input("Expense Date", key="manual_date")
    category = st.selectbox("Category", list(CATEGORIES.keys()), key="manual_category")
    description = st.text_input("Description", key="manual_description")
    amount = st.number_input("Amount ($)", min_value=0.01, format="%.2f", key="manual_amount")

    manual_receipt_file = st.file_uploader("Optional: Upload receipt image manually", type=["jpg", "jpeg", "png"], key="manual_receipt")

    if st.button("Save Expense"):
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
                height = int((float(img.height) * float(ratio)))
                img = img.resize((1024, height), Image.Resampling.LANCZOS)
                img.save(local_path)

            upload_receipt(local_path, year, category)

    st.header("Enter New Expense")
    year = st.number_input("Tax Year", min_value=2000, max_value=2100, value=datetime.now().year, key="manual_year")
    date = st.date_input("Expense Date", key="manual_date")
    category = st.selectbox("Category", list(CATEGORIES.keys()), key="manual_category")
    description = st.text_input("Description", key="manual_description")
    amount = st.number_input("Amount ($)", min_value=0.01, format="%.2f", key="manual_amount")

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
    year = st.number_input("Select Year", min_value=2000, max_value=2100, value=datetime.now().year, key="summary_year")
    df = get_summary(year)
    if not df.empty:
        st.dataframe(df)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", csv, f"summary_{year}.csv", "text/csv")
    else:
        st.info("No expenses found for this year.")