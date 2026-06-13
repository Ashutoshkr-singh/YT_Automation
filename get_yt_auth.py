import sys
from pytubefix import YouTube
from pytubefix.cli import on_progress

try:
    print('Attempting to initialize YouTube connection...')
    yt = YouTube('https://www.youtube.com/watch?v=r09LCmlNjPA', use_oauth=True, allow_oauth_cache=True)
    print('Connected successfully: ' + yt.title)
except Exception as e:
    print('Error: ' + str(e))
