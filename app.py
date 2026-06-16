import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import re
import json
import argparse
import asyncio

import requests
import subprocess
import shutil
import edge_tts
import time
import math
import random
import urllib.request
import random
from gradio_client import Client, handle_file

YTDLP_EXE = shutil.which("yt-dlp") or "yt-dlp"

def _ytdlp_base_args():
    """Return base yt-dlp args with cookies and JS solver if available."""
    cmd = [
        YTDLP_EXE,
        "--no-playlist",
        "--geo-bypass",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=android,ios,web_creator,default",
        "--impersonate", "chrome",
        "--force-ipv6"
    ]
    cookies_path = os.path.join(os.path.dirname(__file__), "cookies.txt")
    if os.path.exists(cookies_path):
        cmd.extend(["--cookies", cookies_path])
    return cmd

def get_rapidapi_stream_urls(youtube_url):
    import urllib.request, json, ssl, re
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", youtube_url)
    video_id = match.group(1) if match else youtube_url
    url = f'https://youtube-media-downloader.p.rapidapi.com/v2/video/details?videoId={video_id}'
    req = urllib.request.Request(url, headers={
        'x-rapidapi-host': 'youtube-media-downloader.p.rapidapi.com',
        'x-rapidapi-key': '1b6e7b51admsh0df00418041aee6p1a5a1cjsn4274af0ba0d9'
    })
    try:
        res = json.loads(urllib.request.urlopen(req, context=ssl._create_unverified_context()).read().decode())
        vid_url = None
        aud_url = None
        
        videos = res.get('videos', {}).get('items', [])
        for v in videos:
            if v.get('quality') == '1080p50' and v.get('extension') == 'mp4':
                vid_url = v.get('url')
                break
        if not vid_url:
            for v in videos:
                if '1080' in str(v.get('quality')) and v.get('extension') == 'mp4':
                    vid_url = v.get('url')
                    break
        if not vid_url and videos:
            vid_url = videos[0].get('url')

        audios = res.get('audios', {}).get('items', [])
        if audios:
            aud_url = audios[0].get('url')
        
        return vid_url, aud_url
    except Exception as e:
        print(f"RapidAPI Error: {e}")
        return None, None

def download_full_audio_for_whisper(youtube_url, output_path="audio_for_whisper.mp3"):
    print("➔ Downloading audio track for transcription...")
    _, aud_url = get_rapidapi_stream_urls(youtube_url)
    if not aud_url:
        raise RuntimeError("RapidAPI failed to provide an audio stream.")
    
    res = subprocess.run(["ffmpeg", "-y", "-i", aud_url, "-b:a", "64k", "-map", "a", output_path], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {res.stderr}")
    return output_path

def download_youtube_video(youtube_url, start_time, end_time, output_path):
    print(f"➔ Downloading high-quality segment ({start_time}s to {end_time}s) for final render...")
    vid_url, aud_url = get_rapidapi_stream_urls(youtube_url)
    if not vid_url or not aud_url:
        raise RuntimeError("RapidAPI failed to provide video/audio streams.")
    
    res = subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_time), "-to", str(end_time),
        "-i", vid_url, "-ss", str(start_time), "-to", str(end_time),
        "-i", aud_url, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        output_path
    ], capture_output=True, text=True)
    
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg merge/crop failed: {res.stderr}")
    return output_path

def get_unique_background_music(index, sport_type):
    print(f"➔ Sourcing hype background track for Video #{index+1}...")
    import sys; sys.stdout.flush()
    music_styles = [
        f"{sport_type} hype background music royalty free phonk",
        f"NCS aggressive bass drop beat for {sport_type}",
        f"cinematic epic {sport_type} background music no copyright"
    ]
    search_query = random.choice(music_styles)
    output_base = f"bg_music_{index}"
    try:
        from pytubefix import Search
        s = Search(search_query)
        if s.videos:
            yt = s.videos[0]
            _, aud_url = get_rapidapi_stream_urls(yt.watch_url)
            if aud_url:
                res = subprocess.run(["ffmpeg", "-y", "-i", aud_url, "-q:a", "0", "-map", "a", f"{output_base}.mp3"], capture_output=True, text=True)
                if res.returncode != 0:
                    raise RuntimeError(f"ffmpeg bg music extract failed: {res.stderr}")
                return f"{output_base}.mp3"
    except Exception as e:
        print(f"   ⚠️ Background music fetch failed: {e}")
    return None

def transcribe_audio(audio_path):
    print("➔ Transcribing audio with lightning-fast Groq API...")
    import requests
    
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set in the environment variables.")
        
    url = "https://api.groq.com/openai/v1/audio/translations"
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {"model": "whisper-large-v3", "response_format": "verbose_json"}
    
    with open(audio_path, "rb") as f:
        files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
        response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        
    if response.status_code != 200:
        raise RuntimeError(f"Groq transcription failed: {response.text}")
        
    result = response.json()
    
    return [{'start': s['start'], 'end': s['end'], 'text': s['text'].strip()} for s in result['segments']]

def get_viral_scripts(transcript_data, user_query, youtube_title):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: raise ValueError("CRITICAL ERROR: GEMINI_API_KEY missing.")
    
    transcript_text = "\n".join([f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}" for s in transcript_data])
    
    system_prompt = f"""You are an elite, multi-million-subscriber viral YouTube Shorts producer. Your ONLY goal is GUARANTEED VIRALITY.
Analyze the transcript and isolate the absolute most mind-blowing, high-energy action sequences based on the query. 
The original video title is: "{youtube_title}" - Use this context to generate highly accurate and viral SEO metadata.
Each clip must be between 20 and 30 seconds long.

CRITICAL — HOOK SCRIPT RULES:
For each clip, write a SHORT, EXPLOSIVE 2-second intro script for a female sports commentator. These must be SCROLL-STOPPING openers that feel like a live broadcast reaction, NOT a question.

GOOD examples (use this aggressive, direct style):
- "WHAT. A. STRIKE! This is absolutely INSANE!"
- "OH MY GOD! LOOK AT THAT!"

The hook must sound like someone who just witnessed something incredible LIVE and is reacting with pure adrenaline. Keep it under 8 words.

Also, determine the specific sport (e.g., "Football", "Hockey") AND the perfect music vibe for this specific moment (e.g., "epic intense cinematic", "fast paced phonk drift", "sad emotional orchestral").
Output strictly valid JSON. Format: {{ "sport_type": "Football", "music_vibe": "epic intense cinematic", "clips": [{{"start": 10.5, "end": 35.0, "hook_script": "WHAT A STRIKE! Absolutely UNREAL!", "title": "INSANE Goal You Have To See! 🔥⚽", "description": "Watch this incredible goal that left everyone speechless! #football #fifa", "tags": ["football", "fifa", "viral"]}}] }}"""

    available_models = []
    try:
        models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        res = requests.get(models_url).json()
        available_models = [m['name'] for m in res.get('models', [])]
    except Exception: pass
    
    flash_models = sorted([m for m in available_models if "flash" in m], reverse=True)
    pro_models = sorted([m for m in available_models if "pro" in m], reverse=True)
    model_queue = flash_models + pro_models
    if not model_queue: model_queue = ["models/gemini-1.5-pro"]

    for target_model in model_queue:
        url = f"https://generativelanguage.googleapis.com/v1beta/{target_model}:generateContent?key={api_key}"
        data = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": f"Query: {user_query}\n\nTranscript:\n{transcript_text}"}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}
        }
        for attempt in range(3):
            try:
                response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, timeout=60)
                if response.status_code == 200:
                    response_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if not json_match: raise ValueError(f"AI did not return JSON: {response_text}")
                    return json.loads(json_match.group(0))
                elif response.status_code in [503, 429, 404]: break
                else: raise RuntimeError(f"API Error ({response.status_code}): {response.text}")
            except requests.exceptions.RequestException as e:
                print(f"      ⚠️ Network hiccup ({e}). Retrying {attempt+1}/3...")
                time.sleep(3)
        continue
    raise RuntimeError("CRITICAL: All AI models overloaded or network failed.")

async def generate_voiceover(text, output_path):
    communicate = edge_tts.Communicate(text, "en-US-AriaNeural", rate="+25%", pitch="+8Hz")
    await communicate.save(output_path)

def build_subtitles_from_original(transcript_data, start_time, end_time, srt_path):
    clip_segments = [s for s in transcript_data if s['end'] > start_time and s['start'] < end_time]
    with open(srt_path, 'w', encoding='utf-8') as f:
        for idx, seg in enumerate(clip_segments):
            s_time = max(0, seg['start'] - start_time)
            e_time = min(end_time - start_time, seg['end'] - start_time)
            def fmt(sec): return f"{int(sec//3600):02d}:{int((sec%3600)//60):02d}:{int(sec%60):02d},{int((sec%1)*1000):03d}"
            f.write(f"{idx+1}\n{fmt(s_time)} --> {fmt(e_time)}\n{seg['text']}\n\n")

def get_video_duration(video_path, fallback_duration=15.0):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path
        ], capture_output=True, text=True)
        duration_str = result.stdout.strip()
        if duration_str == 'N/A' or not duration_str:
            return float(fallback_duration)
        return float(duration_str)
    except Exception:
        return float(fallback_duration)

def compose_hybrid_video(local_segment_video, clip, idx, hook_voice, bg_music, transcript, output_dir):
    output_vid = os.path.join(output_dir, f"Viral_Short_{idx+1}.mp4")
    srt_path = f"temp_subs_{idx+1}.srt"
    
    build_subtitles_from_original(transcript, clip['start'], clip['end'], srt_path)
    permanent_srt = os.path.join(output_dir, f"Viral_Short_{idx+1}.srt")
    shutil.copy(srt_path, permanent_srt)
    print(f"   📝 SRT preserved for YouTube upload: {permanent_srt}")
    
    public_dir = os.path.join("bouncy-subs", "public")
    os.makedirs(public_dir, exist_ok=True)
    
    shutil.copy(local_segment_video, os.path.join(public_dir, "current_video.mp4"))
    shutil.copy(srt_path, os.path.join(public_dir, "current_subs.srt"))
    
    bg_target = os.path.join(public_dir, "current_bg.mp3")
    if bg_music and os.path.exists(bg_music):
        shutil.copy(bg_music, bg_target)
    elif os.path.exists(bg_target):
        os.remove(bg_target)

    hook_target = os.path.join(public_dir, "current_hook.mp3")
    if hook_voice and os.path.exists(hook_voice):
        shutil.copy(hook_voice, hook_target)
    elif os.path.exists(hook_target):
        os.remove(hook_target)

    print(f"   🎬 Rendering Premium Cinematic Edit #{idx+1} with Remotion...")
    
    vid_duration = get_video_duration(local_segment_video, fallback_duration=(clip['end'] - clip['start']))
        
    total_frames = int(vid_duration * 60)
    
    props = json.dumps({
        "videoDuration": vid_duration,
        "totalFrames": total_frames
    })
    
    output_vid_abs = os.path.abspath(output_vid)
    res = subprocess.run(["npx.cmd" if os.name == 'nt' else "npx", "remotion", "render", "BouncySubs", output_vid_abs, f"--props={props}", "--timeout=120000", "--jpeg-quality=100", "--concurrency=4"], cwd="bouncy-subs", capture_output=False)
    if res.returncode != 0:
        raise RuntimeError(f"Remotion render failed with exit code {res.returncode}")
    print(f"   ✅ Saved: {output_vid}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()

    try:
        # Try to get the original video title for context-aware SEO
        yt_title = "FIFA Highlights"
        try:
            from pytubefix import YouTube as PTF
            yt = PTF(args.url, client='ANDROID', use_oauth=True, allow_oauth_cache=True)
            yt_title = yt.title
        except Exception as e:
            print(f"   ⚠️ pytubefix title fetch failed ({e}), trying yt-dlp...")
            try:
                title_result = subprocess.run(
                    _ytdlp_base_args() + ["--print", "%(title)s", "--no-download", args.url],
                    capture_output=True, text=True, timeout=30
                )
                if title_result.returncode == 0 and title_result.stdout.strip():
                    yt_title = title_result.stdout.strip()
            except Exception:
                pass
        print(f"📺 Original video title: {yt_title}")
        
        import urllib.parse as urlparse
        parsed = urlparse.urlparse(args.url)
        vid_id = urlparse.parse_qs(parsed.query).get('v', ['output'])[0] if 'youtube.com' in args.url else args.url.split('/')[-1]
        out_dir = f"Output_{vid_id}"
        os.makedirs(out_dir, exist_ok=True)
        print(f"📁 All final assets will be saved to: {out_dir}")

        audio_file = download_full_audio_for_whisper(args.url)
        transcript = transcribe_audio(audio_file)
        ai_response = get_viral_scripts(transcript, args.prompt, yt_title)
        
        sport_type = ai_response.get("sport_type", "epic sports")
        music_vibe = ai_response.get("music_vibe", "epic cinematic phonk")
        viral_clips = ai_response.get("clips", [])
        
        for i, clip in enumerate(viral_clips):
            import sys; sys.stdout.flush()
            print(f"\n➔ Processing Hybrid Short #{i+1}")
            print(f"   🗣️ Avatar Hook Script: \"{clip['hook_script']}\"")
            
            # --- 4. EXTRACT HIGH-QUALITY SEGMENT ---
            print("\n[Step 4] Downloading Ultra-HD Segment...")
            segment_video = os.path.join(out_dir, f"segment_{i}.mp4")
            if not os.path.exists(segment_video):
                download_youtube_video(args.url, clip['start'], clip['end'], segment_video)
            
            hook_voice = f"temp_hook_{i+1}.mp3"
            
            # Save temporary music_vibe wrapper for get_unique_background_music
            bg_music = get_unique_background_music(i, f"{sport_type} {music_vibe}")
            
            asyncio.run(generate_voiceover(clip['hook_script'], hook_voice))
            
            compose_hybrid_video(segment_video, clip, i, hook_voice, bg_music, transcript, out_dir)
            
            # Save SEO metadata for the uploader
            md_path = os.path.join(out_dir, f"Viral_Short_{i+1}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"### 1. Title\n{clip.get('title', f'Epic {sport_type} Moment #{i+1}')}\n\n")
                f.write(f"### 3. Description\n{clip.get('description', 'Incredible sports highlights!')}\n\n")
                f.write(f"### 4. Tags\n{', '.join(clip.get('tags', [sport_type, 'viral']))}\n")
            
            for file in [hook_voice, bg_music, segment_video]:
                if file and os.path.exists(file): os.remove(file)
            
        if os.path.exists(audio_file): os.remove(audio_file)
        print("\n🎉 PRODUCTION COMPLETE! High-Fidelity files ready for YouTube.")
    except Exception as e:
        print(f"\n❌ PIPELINE HALTED: {e}")

if __name__ == "__main__":
    main()