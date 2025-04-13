import sqlite3
import shutil
import os
import pytesseract
from PIL import Image
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import streamlit as st

DB_FILE = "expenses.db"
LOCAL_SAVE_DIR = "receipts"

CATEGORIES = {
    "food": "Meals and Entertainment",
    "restaurant": "Meals and Entertainment",
    "uber": "Travel",
    "hotel": "Travel",
    "flight": "Travel",
    "pen": "Supplies",
    "paper": "Supplies",
    "internet": "Utilities",
    "hydro": "Utilities",
    "misc": "Miscellaneous"
}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, year INTEGER, date TEXT, category TEXT, description TEXT, amount REAL)")
    conn.commit()
    conn.close()

def insert_expense(year, date, category, description, amount):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO expenses (year, date, category, description, amount) VALUES (?, ?, ?, ?, ?)",
              (year, date, category, description, amount))
    conn.commit()
    conn.close()

def get_summary(year):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT category, SUM(amount) as amount FROM expenses WHERE year = ? GROUP BY category", (year,))
    rows = c.fetchall()
    conn.close()
    import pandas as pd
    return pd.DataFrame(rows, columns=["category", "amount"])

def extract_text_and_save(image_path):
    try:
        import requests

        with open(image_path, "rb") as f:
            file_bytes = f.read()

        api_key = st.secrets["ocr"]["api_key"]
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": file_bytes},
            data={"apikey": api_key, "language": "eng", "isOverlayRequired": False},
        )
        result = response.json()

        if "ParsedResults" not in result or not result["ParsedResults"]:
            raise ValueError(result.get("ErrorMessage", "No text found."))

        parsed = result["ParsedResults"][0]["ParsedText"]
        if not parsed:
            raise ValueError("OCR returned empty text")

        # Save receipt image
        year = datetime.now().year
        category = categorize_expense(parsed)
        amount = extract_amount(parsed) or 0.0  # fallback to 0 if not detected

        filename = f"{datetime.now().strftime('%d-%m-%Y-%H%M%S')}.png"
        local_path = os.path.join(LOCAL_SAVE_DIR, filename)
        shutil.copy(image_path, local_path)

        return parsed, local_path, category, amount

    except Exception as e:
        return f"OCR Error: {e}", None, None, 0.0

def get_drive_service():
    creds = None
    if "token" in st.secrets:
        import base64, pickle
        token_str = st.secrets.get("token")
        if isinstance(token_str, dict):
            token_str = token_str.get("token")

        if not token_str:
            raise Exception("Missing Google Drive token in secrets.")

        creds = pickle.loads(base64.b64decode(token_str))
        return build("drive", "v3", credentials=creds)

def find_or_create_folder(service, name, parent=None):
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder'"
    if parent:
        query += f" and '{parent}' in parents"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    items = results.get("files", [])
    if items:
        return items[0]["id"]
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent:
        metadata["parents"] = [parent]
    file = service.files().create(body=metadata, fields="id").execute()
    return file.get("id")

def upload_file_to_folder(service, folder_id, file_path, filename):
    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }
    media = MediaFileUpload(file_path, resumable=True)
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()

def upload_receipt(image_path, year, category):
    try:
        service = get_drive_service()
        root_folder = find_or_create_folder(service, "Receipts")
        year_folder = find_or_create_folder(service, str(year), parent=root_folder)
        category_folder = find_or_create_folder(service, category, parent=year_folder)
        filename = os.path.basename(image_path)
        upload_file_to_folder(service, category_folder, image_path, filename)
    except Exception as e:
        st.error(f"Failed to upload to Google Drive: {e}")

def download_db_from_drive():
    try:
        service = get_drive_service()
        # Look for a file named 'expenses.db' in root or Receipts folder
        query = "name='expenses.db'"
        results = service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
        items = results.get("files", [])
        if not items:
            print("No remote DB found in Drive.")
            return False
        file_id = items[0]["id"]
        request = service.files().get_media(fileId=file_id)
        local_path = DB_FILE
        from googleapiclient.http import MediaIoBaseDownload
        import io
        fh = io.FileIO(local_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        print("✅ Downloaded DB from Google Drive.")
        return True
    except Exception as e:
        print(f"⚠️ Failed to download DB from Drive: {e}")
        return False