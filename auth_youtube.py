"""
Run this script directly to authenticate with YouTube.
A browser window will open — log in with your YouTube Google account and click Allow.
"""
import os, sys, pickle
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")

from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_SECRET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secret.json")
TOKEN_PICKLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.pickle")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

print("🌐 Opening browser for YouTube login...")
print("   Log in with the Google account that owns your YouTube channel.")
print("   Then click 'Allow' to grant upload permission.\n")

flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
credentials = flow.run_local_server(port=8080, prompt="consent")

with open(TOKEN_PICKLE, "wb") as f:
    pickle.dump(credentials, f)

print("\n✅ Authentication successful! Token saved to token.pickle")
print("   You won't need to log in again.")
