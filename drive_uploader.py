import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_FILE = "client_secrets.json"
TOKEN_FILE = "token.pickle"

def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)
    service = build("drive", "v3", credentials=creds)
    return service

def find_or_create_folder(folder_name, parent_folder_id=None):
    service = get_drive_service()
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
    if parent_folder_id:
        query += f" and '{parent_folder_id}' in parents"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    folders = results.get("files", [])
    if folders:
        return folders[0]["id"]
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    if parent_folder_id:
        metadata["parents"] = [parent_folder_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]

def upload_file_to_folder(file_path, parent_folder_name):
    service = get_drive_service()
    parent_id = find_or_create_folder(parent_folder_name)
    file_name = os.path.basename(file_path)
    file_metadata = {"name": file_name, "parents": [parent_id]}
    media = MediaFileUpload(file_path)
    results = service.files().list(q=f"name='{file_name}' and '{parent_id}' in parents", fields="files(id)").execute()
    existing_files = results.get("files", [])
    if existing_files:
        file_id = existing_files[0]["id"]
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        service.files().create(body=file_metadata, media_body=media, fields="id").execute()

def upload_receipt(file_path, year, category):
    service = get_drive_service()
    root_id = find_or_create_folder("Receipts")
    year_id = find_or_create_folder(str(year), root_id)
    category_id = find_or_create_folder(category, year_id)
    file_name = os.path.basename(file_path)
    file_metadata = {"name": file_name, "parents": [category_id]}
    media = MediaFileUpload(file_path)
    service.files().create(body=file_metadata, media_body=media, fields="id").execute()