"""
monitor.py — FIFA YouTube Channel Monitor
==========================================
Monitors the official FIFA YouTube channel for new highlight uploads.
When a new video is detected, it triggers the clip generation pipeline.
"""

import os
import sys
import json
import time
import pathlib
import logging
from datetime import datetime, timedelta

# Force UTF-8 output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fifa_monitor")

# ─────────────────────────── Config ───────────────────────────
FIFA_CHANNEL_ID = "UCpcTrCXblq78GZrTUTLWeBw"
STATE_FILE = pathlib.Path(__file__).parent / "monitor_state.json"
import shutil
YTDLP_EXE = shutil.which("yt-dlp") or "yt-dlp"

# Keywords to filter for highlight/recap videos
HIGHLIGHT_KEYWORDS = [
    "highlight", "goals", "recap", "best moments", "match day",
    "goal of the day", "all goals", "top goals", "extended highlights",
    "full highlights", "great goals", "best of", "skills", "final",
    "semi-final", "quarter-final", "group stage"
]

# ─────────────────────────── State Management ─────────────────

def load_state() -> dict:
    """Load the list of already-processed video IDs."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processed_ids": [], "last_check": None}

def save_state(state: dict):
    """Persist processed video IDs to disk."""
    state["last_check"] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

# ─────────────────────────── Channel Scanning ─────────────────

def fetch_recent_videos(max_videos: int = 15) -> list[dict]:
    """
    Use yt-dlp to fetch metadata of recent uploads from the FIFA channel.
    Returns a list of dicts with 'id', 'title', 'upload_date', 'duration', 'url'.
    """
    import subprocess

    log.info("🔍  Scanning FIFA channel for new uploads...")

    cmd = [YTDLP_EXE, "--remote-components", "ejs:github", "--extractor-args", "youtube:player_client=ios,web_creator,default"]
    # Add cookies if available
    cookies_path = pathlib.Path(__file__).parent / "cookies.txt"
    if cookies_path.exists():
        cmd += ["--cookies", str(cookies_path)]
    cmd += [
        "--flat-playlist",
        "--dump-json",
        "--playlist-end", str(max_videos),
        "--no-warnings",
        f"https://www.youtube.com/channel/{FIFA_CHANNEL_ID}/videos"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace"
        )
    except subprocess.TimeoutExpired:
        log.error("❌  yt-dlp timed out scanning the FIFA channel.")
        return []

    if result.returncode != 0:
        log.error("❌  yt-dlp error: %s", result.stderr[:500])
        return []

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            videos.append({
                "id": data.get("id", ""),
                "title": data.get("title", "Untitled"),
                "upload_date": data.get("upload_date", ""),
                "duration": data.get("duration", 0),
                "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
            })
        except json.JSONDecodeError:
            continue

    log.info("📋  Found %d recent uploads on the FIFA channel.", len(videos))
    return videos


def is_highlight_video(title: str, duration: int) -> bool:
    """
    Only process videos that are actual match highlights, goals compilations,
    or skill showcases. Skip press conferences, interviews, and behind-the-scenes
    content because they're talking-head footage that can't produce viral sports clips.
    """
    title_lower = title.lower()
    
    # Reject patterns — these are never clippable
    skip_keywords = [
        "press conference", "post-match interview", "post match interview",
        "takes questions", "take questions", "coach on", "coach talks",
        "behind the scenes", "draw ceremony", "letters that unite"
    ]
    for skip in skip_keywords:
        if skip in title_lower:
            return False
    
    # Accept patterns — these always produce good clips
    accept_keywords = [
        "highlight", "goals", "recap", "best moments", "match day",
        "goal of the day", "all goals", "top goals", "extended highlights",
        "full highlights", "great goals", "best of", "skills", "final",
        "semi-final", "quarter-final", "group stage", "team feature"
    ]
    for kw in accept_keywords:
        if kw in title_lower:
            # Duration sanity check: skip shorts (<30s) and full matches (>3hr)
            if duration and duration > 0:
                return 30 <= duration <= 10800
            return True
    
    # For anything else, accept if duration is reasonable
    if duration and duration > 0:
        return 30 <= duration <= 10800
    
    return True


def find_new_highlights(max_videos: int = 15) -> list[dict]:
    """
    Scan the FIFA channel and return a list of new highlight videos
    that haven't been processed yet.
    """
    state = load_state()
    processed = set(state.get("processed_ids", []))

    all_videos = fetch_recent_videos(max_videos)

    new_highlights = []
    for video in all_videos:
        vid_id = video["id"]

        # Skip already processed
        if vid_id in processed:
            log.info("   ⏭️  Already processed: %s", video["title"][:60])
            continue

        # Check if it's a highlight video
        if is_highlight_video(video["title"], video["duration"]):
            log.info("   🆕  NEW HIGHLIGHT: %s", video["title"][:60])
            new_highlights.append(video)
        else:
            log.info("   ⏭️  Skipping (not highlights): %s", video["title"][:60])

    log.info("🎯  %d new highlight video(s) to process.", len(new_highlights))
    return new_highlights


def mark_as_processed(video_id: str):
    """Mark a video ID as processed so we don't clip it again."""
    state = load_state()
    if video_id not in state["processed_ids"]:
        state["processed_ids"].append(video_id)
    # Keep only last 200 IDs to prevent the file from growing forever
    state["processed_ids"] = state["processed_ids"][-200:]
    save_state(state)


# ─────────────────────────── CLI ──────────────────────────────

def main():
    """Run a single scan and print results."""
    banner = r"""
    ╔══════════════════════════════════════════════════════════╗
    ║        FIFA CHANNEL MONITOR — Highlight Scanner         ║
    ║        ─────────────────────────────────────             ║
    ║   Scans the official FIFA YouTube channel for new        ║
    ║   highlight uploads and triggers the clip pipeline.      ║
    ╚══════════════════════════════════════════════════════════╝
    """
    print(banner)

    new_highlights = find_new_highlights()

    if not new_highlights:
        log.info("✅  No new highlights found. Channel is up to date.")
        return []

    for i, vid in enumerate(new_highlights, 1):
        dur_min = (vid.get("duration", 0) or 0) / 60
        log.info(
            "  %d. [%s] %s (%.1f min)",
            i, vid["id"], vid["title"][:50], dur_min
        )

    return new_highlights


if __name__ == "__main__":
    results = main()
    if results:
        print(f"\n📊 Found {len(results)} new highlight(s) ready for processing.")
    else:
        print("\n💤 No new highlights. Everything is up to date.")
