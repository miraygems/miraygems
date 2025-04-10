import os
import pickle
import io
import mimetypes
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def authenticate():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)
    return creds

def get_or_create_folder(service, parent_id, name):
    query = f"'{parent_id}' in parents and name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive').execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    file_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    file = service.files().create(body=file_metadata, fields="id").execute()
    return file.get("id")

def upload_receipt(file_path, year, category):
    creds = authenticate()
    service = build("drive", "v3", credentials=creds)

    base_folder_id = get_or_create_folder(service, "root", "Receipts")
    year_folder_id = get_or_create_folder(service, base_folder_id, str(year))
    category_folder_id = get_or_create_folder(service, year_folder_id, category)

    file_name = os.path.basename(file_path)
    mime_type = mimetypes.guess_type(file_path)[0] or "image/png"
    file_metadata = {"name": file_name, "parents": [category_folder_id]}
    media = MediaIoBaseUpload(io.FileIO(file_path, "rb"), mimetype=mime_type)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    return file.get("id")
