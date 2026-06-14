from pytubefix import YouTube
import shutil
import sys
import os

print("\n========================================================")
print("🔑 YouTube Bot Bypass - OAuth Token Generator")
print("========================================================\n")
print("1. In a moment, you will see a link and a code.")
print("2. Open the link in your browser and enter the code.")
print("3. Log into your YouTube account and allow access.")
print("   (This is required to prove to YouTube that you are human)\n")

try:
    yt = YouTube('https://www.youtube.com/watch?v=xp763iNB_MA', use_oauth=True, allow_oauth_cache=True)
    # Trigger the oauth flow by requesting streams
    print("Initializing OAuth flow... please wait.")
    yt.streams.first()
    
    print("\n✅ SUCCESS! Authenticated successfully.")
    
    # Locate the tokens.json file
    import pytubefix
    token_file = os.path.join(os.path.dirname(pytubefix.__file__), "__cache__", "tokens.json")
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            token_data = f.read()
        print("\n========================================================")
        print("YOUR OAUTH TOKEN DATA:")
        print("========================================================")
        print(token_data)
        print("========================================================")
        print("\nINSTRUCTIONS:")
        print("1. Copy ALL of the text between the equal signs above.")
        print("2. Go to your GitHub Repository -> Settings -> Secrets and variables -> Actions")
        print("3. Create a New repository secret named: YOUTUBE_OAUTH_TOKEN")
        print("4. Paste the text and click 'Add secret'.")
    else:
        print(f"\n❌ Could not locate the tokens.json file at {token_file}")
except Exception as e:
    print(f"\n❌ An error occurred: {e}")
