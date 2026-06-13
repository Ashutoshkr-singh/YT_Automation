from pytubefix import YouTube
yt = YouTube('https://www.youtube.com/watch?v=r09LCmlNjPA', use_oauth=True, allow_oauth_cache=True, client='TV')
stream = yt.streams.filter(only_audio=True).first()
print('URL:', stream.url[:100] + '...')
