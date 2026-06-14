import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    if not os.path.exists("client_secret.json"):
        print("❌ ERROR: client_secret.json not found!")
        print("Please place your client_secret.json file in this directory.")
        return

    print("🌐 Opening browser for YouTube OAuth2 consent...")
    flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
    credentials = flow.run_local_server(port=0)

    with open("token.pickle", "wb") as f:
        pickle.dump(credentials, f)
    
    print("\n✅ SUCCESS! token.pickle generated successfully.")
    
    import base64
    with open("token.pickle", "rb") as f:
        b64_token = base64.b64encode(f.read()).decode("utf-8")
        
    print("\n" + "="*70)
    print("COPY THE FOLLOWING STRING INTO YOUR 'YOUTUBE_TOKEN_BASE64' GITHUB SECRET:")
    print("="*70)
    print(b64_token)
    print("="*70)

if __name__ == "__main__":
    main()
