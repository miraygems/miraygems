from drive_uploader import authenticate

if __name__ == "__main__":
    print("Authenticating with Google Drive...")
    creds = authenticate()
    print("Authentication successful! token.pickle has been saved.")
