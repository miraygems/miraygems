from drive_uploader import get_drive_service

if __name__ == "__main__":
    print("Authenticating with Google Drive...")
creds = get_drive_service()
    print("Authentication successful! token.pickle has been saved.")
