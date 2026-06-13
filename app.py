import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import re
import json
import argparse
import asyncio
import whisper
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

def _ytdlp_base_args():
    """Return base yt-dlp args with cookies if available."""
    import shutil
    exe = shutil.which("yt-dlp") or "yt-dlp"
    args = [exe]
    if os.path.exists("cookies.txt"):
        args += ["--cookies", "cookies.txt"]
    return args

def download_full_audio_for_whisper(youtube_url, output_path="audio_for_whisper.mp3"):
    print("➔ Downloading audio track for transcription...")
    cmd = _ytdlp_base_args() + [
        "-x", "--audio-format", "mp3",
        "-o", output_path.replace(".mp3", ""),
        youtube_url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='ignore')
            print(f"yt-dlp audio stderr: {stderr}")
            # If cookies failed, retry without cookies
            if "cookies" in stderr.lower() or "bot" in stderr.lower():
                print("   ↻ Retrying without cookies...")
                cmd_no_cookies = [c for c in cmd if c not in ["--cookies", "cookies.txt"]]
                result = subprocess.run(cmd_no_cookies, capture_output=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"yt-dlp failed: {result.stderr.decode('utf-8', errors='ignore')}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp audio download timed out after 5 minutes")
    return output_path

def download_youtube_video(youtube_url, start_time, end_time, output_path):
    print(f"➔ Downloading high-quality segment ({start_time}s to {end_time}s) for final render...")
    cmd = _ytdlp_base_args() + [
        "--download-sections", f"*{start_time}-{end_time}",
        "--force-keyframes-at-cuts",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", output_path,
        youtube_url
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        if result.returncode != 0:
            stderr = result.stderr.decode('utf-8', errors='ignore')
            print(f"yt-dlp video stderr: {stderr}")
            if "cookies" in stderr.lower() or "bot" in stderr.lower():
                print("   ↻ Retrying without cookies...")
                cmd_no_cookies = [c for c in cmd if c not in ["--cookies", "cookies.txt"]]
                result = subprocess.run(cmd_no_cookies, capture_output=True, timeout=600)
            if result.returncode != 0:
                raise RuntimeError(f"yt-dlp failed: {result.stderr.decode('utf-8', errors='ignore')}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp video download timed out after 10 minutes")
    return output_path

def get_unique_background_music(index, sport_type):
    print(f"➔ Sourcing hype background track for Video #{index+1}...")
    music_styles = [
        f"ytsearch1: {sport_type} hype background music royalty free phonk",
        f"ytsearch1: NCS aggressive bass drop beat for {sport_type}",
        f"ytsearch1: cinematic epic {sport_type} background music no copyright"
    ]
    search_query = random.choice(music_styles)
    output_base = f"bg_music_{index}"
    
    import yt_dlp
    ydl_opts = {
        'format': 'bestaudio/best', 'outtmpl': f'{output_base}.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        'noplaylist': True,
        'quiet': True, 'no_warnings': True,
        'extractor_args': {'youtube': ['player_client=ios,default']}
    }
    # Use cookies if available
    if os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = 'cookies.txt'
    try:
        if os.path.exists(f"{output_base}.mp3"): os.remove(f"{output_base}.mp3")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([search_query])
        if os.path.exists(f"{output_base}.mp3"): return f"{output_base}.mp3"
        return None
    except Exception: return None

def transcribe_audio(audio_path):
    print("➔ Loading Whisper AI to map the original commentator...")
    try:
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA not available in PyTorch")
        model = whisper.load_model("base", device="cuda")
    except Exception as e:
        print(f"   ⚠️ GPU Acceleration failed. Falling back to CPU... Error: {str(e)[:100]}")
        model = whisper.load_model("base", device="cpu")
    
    result = model.transcribe(audio_path)
    return [{'start': s['start'], 'end': s['end'], 'text': s['text'].strip()} for s in result['segments']]

def get_viral_scripts(transcript_data, user_query):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: raise ValueError("CRITICAL ERROR: GEMINI_API_KEY missing.")
    
    transcript_text = "\n".join([f"[{s['start']:.1f}s - {s['end']:.1f}s] {s['text']}" for s in transcript_data])
    
    system_prompt = """You are an elite, multi-million-subscriber viral YouTube Shorts producer. Your ONLY goal is GUARANTEED VIRALITY.
Analyze the transcript and isolate the 5 absolute most mind-blowing, high-energy action sequences based on the query. Ignore boring commentary. Focus ONLY on jaw-dropping moments, massive plays, insane highlights, or shocking events that will instantly hook a viewer and make them share the video. 
Each clip must be between 20 and 30 seconds long.

CRITICAL — HOOK SCRIPT RULES:
For each clip, write a SHORT, EXPLOSIVE 2-second intro script for a female sports commentator. These must be SCROLL-STOPPING openers that feel like a live broadcast reaction, NOT a question.

GOOD examples (use this aggressive, direct style):
- "WHAT. A. STRIKE! This is absolutely INSANE!"
- "OH MY GOD! LOOK AT THAT!"
- "NO WAY! He just did the IMPOSSIBLE!"
- "THIS IS UNREAL! Watch this!"
- "GOAAAAL! The crowd goes WILD!"

BAD examples (NEVER use these weak styles):
- "You won't believe what happens next" (too generic, clickbait)
- "Watch until the end" (boring)
- "This might be the craziest play" (too soft, uses 'might')

The hook must sound like someone who just witnessed something incredible LIVE and is reacting with pure adrenaline. Use CAPS for emphasis words. Keep it under 8 words.

Also, determine the specific sport (e.g., "Football", "Hockey", "Cricket") so we can source the perfect hype track.
Output strictly valid JSON. Format: { "sport_type": "Football", "clips": [{"start": 10.5, "end": 35.0, "hook_script": "WHAT A STRIKE! Absolutely UNREAL!"}] }"""

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
    subprocess.run(["npx.cmd" if os.name == 'nt' else "npx", "remotion", "render", "BouncySubs", output_vid_abs, f"--props={props}", "--timeout=120000", "--scale=4", "--jpeg-quality=100", "--video-bitrate=50M", "--audio-bitrate=320k", "--pixel-format=yuv420p"], cwd="bouncy-subs")
    print(f"   ✅ Saved: {output_vid}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args()

    try:
        import urllib.parse as urlparse
        parsed = urlparse.urlparse(args.url)
        vid_id = urlparse.parse_qs(parsed.query).get('v', ['output'])[0] if 'youtube.com' in args.url else args.url.split('/')[-1]
        out_dir = f"Output_{vid_id}"
        os.makedirs(out_dir, exist_ok=True)
        print(f"📁 All final assets will be saved to: {out_dir}")

        audio_file = download_full_audio_for_whisper(args.url)
        transcript = transcribe_audio(audio_file)
        ai_response = get_viral_scripts(transcript, args.prompt)
        
        sport_type = ai_response.get("sport_type", "epic sports")
        viral_clips = ai_response.get("clips", [])
        
        for i, clip in enumerate(viral_clips):
            print(f"\n➔ Processing Hybrid Short #{i+1}")
            print(f"   🗣️ Avatar Hook Script: \"{clip['hook_script']}\"")
            
            # --- 4. EXTRACT HIGH-QUALITY SEGMENT ---
            print("\n[Step 4] Downloading Ultra-HD Segment...")
            segment_video = os.path.join(out_dir, f"segment_{i}.mp4")
            if not os.path.exists(segment_video):
                download_youtube_video(args.url, clip['start'], clip['end'], segment_video)
            
            hook_voice = f"temp_hook_{i+1}.mp3"
            bg_music = get_unique_background_music(i, sport_type)
            
            asyncio.run(generate_voiceover(clip['hook_script'], hook_voice))
            
            compose_hybrid_video(segment_video, clip, i, hook_voice, bg_music, transcript, out_dir)
            
            # Save SEO metadata for the uploader
            md_path = os.path.join(out_dir, f"Viral_Short_{i+1}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"### 1. Title\n{clip.get('title', f'Epic Football Moment #{i+1}')}\n\n")
                f.write(f"### 3. Description\n{clip.get('description', 'Incredible football highlights!')}\n\n")
                f.write(f"### 4. Tags\n{', '.join(clip.get('tags', ['football', 'fifa']))}\n")
            
            for file in [hook_voice, bg_music, segment_video]:
                if file and os.path.exists(file): os.remove(file)
            
        if os.path.exists(audio_file): os.remove(audio_file)
        print("\n🎉 PRODUCTION COMPLETE! High-Fidelity files ready for YouTube.")
    except Exception as e:
        print(f"\n❌ PIPELINE HALTED: {e}")

if __name__ == "__main__":
    main()