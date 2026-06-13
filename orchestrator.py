"""
orchestrator.py — FIFA Automation Orchestrator
================================================
The master script that ties everything together:
1. Monitors the FIFA channel for new highlights
2. Generates 3 premium viral clips from each highlight
3. Runs the SEO agent on each clip
4. Uploads to YouTube at the scheduled time

Usage:
  python orchestrator.py                    # Full automated run
  python orchestrator.py --scan-only        # Just check for new videos
  python orchestrator.py --process-only URL # Process a specific URL
  python orchestrator.py --upload-only DIR  # Upload already-processed clips
"""

import os
import sys
import io
import argparse
import subprocess
import shutil
import pathlib
import time
import json
import logging
from datetime import datetime

# Force UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("orchestrator")

# ─────────────────────────── Config ───────────────────────────
PROJECT_ROOT = pathlib.Path(__file__).parent
PYTHON_EXE = str(PROJECT_ROOT / "venv" / "Scripts" / "python.exe")
APP_PY = str(PROJECT_ROOT / "app.py")
UPLOAD_PY = str(PROJECT_ROOT / "upload.py")
SEO_AGENT = pathlib.Path(r"C:\Users\found\Videos\seo_agent\auto_yt_agent.py")
SEO_DROP_ZONE = pathlib.Path(r"C:\Users\found\Videos\seo_agent\Drop_Zone_Videos")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Load .env from SEO agent for API key if not already set
if not GEMINI_API_KEY:
    seo_env = SEO_AGENT.parent / ".env"
    if seo_env.exists():
        for line in seo_env.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                GEMINI_API_KEY = line.split("=", 1)[1].strip()
                os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
                break


# ─────────────────────────── Step 1: Monitor ──────────────────

def scan_for_new_highlights() -> list[dict]:
    """Import and run the monitor to find new FIFA highlights."""
    log.info("=" * 60)
    log.info("📡  STEP 1: Scanning FIFA Channel for new highlights...")
    log.info("=" * 60)

    # Import monitor functions
    sys.path.insert(0, str(PROJECT_ROOT))
    from monitor import find_new_highlights
    return find_new_highlights()


# ─────────────────────────── Step 2: Generate Clips ───────────

def generate_clips(youtube_url: str, num_clips: int = 3) -> str | None:
    """
    Run app.py to generate viral clips from the highlight video.
    Returns the output directory path, or None on failure.
    """
    log.info("=" * 60)
    log.info("🎬  STEP 2: Generating %d premium viral clips...", num_clips)
    log.info("   Source: %s", youtube_url)
    log.info("=" * 60)

    env = os.environ.copy()
    env["GEMINI_API_KEY"] = GEMINI_API_KEY
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        result = subprocess.run(
            [
                PYTHON_EXE, APP_PY,
                "--url", youtube_url,
                "--prompt", f"Find the {num_clips} absolute best, most high-energy action sequences with goals, amazing skills, or dramatic moments."
            ],
            cwd=str(PROJECT_ROOT),
            env=env,
            timeout=1800,  # 30 min timeout
        )

        if result.returncode != 0:
            log.error("❌  Clip generation failed with exit code %d", result.returncode)
            return None

    except subprocess.TimeoutExpired:
        log.error("❌  Clip generation timed out after 30 minutes.")
        return None
    except Exception as e:
        log.error("❌  Clip generation error: %s", e)
        return None

    # Find the output directory
    import urllib.parse as urlparse
    parsed = urlparse.urlparse(youtube_url)
    vid_id = urlparse.parse_qs(parsed.query).get('v', ['output'])[0] if 'youtube.com' in youtube_url else youtube_url.split('/')[-1]
    out_dir = PROJECT_ROOT / f"Output_{vid_id}"

    if out_dir.exists():
        mp4_count = len(list(out_dir.glob("Viral_Short_*.mp4")))
        log.info("✅  Generated %d clips in %s", mp4_count, out_dir.name)
        return str(out_dir)
    else:
        log.error("❌  Output directory not found: %s", out_dir)
        return None


# ─────────────────────────── Step 3: Run SEO Agent ────────────

def run_seo_on_clips(output_dir: str) -> list[str]:
    """
    Copy each generated clip to the SEO agent's Drop Zone, then run
    the SEO agent to generate metadata. Returns list of .md file paths.
    
    Instead of running the full watchdog-based agent, we directly import
    the core processing functions from auto_yt_agent.py for reliability.
    """
    log.info("=" * 60)
    log.info("🧠  STEP 3: Running SEO Agent on generated clips...")
    log.info("=" * 60)

    output_path = pathlib.Path(output_dir)
    clips = sorted(output_path.glob("Viral_Short_*.mp4"))

    if not clips:
        log.warning("⚠️  No Viral_Short_*.mp4 files found in %s", output_dir)
        return []

    # Import the SEO agent's core functions
    sys.path.insert(0, str(SEO_AGENT.parent))

    from google import genai
    from google.genai import types

    # Initialize Gemini client
    client = genai.Client(api_key=GEMINI_API_KEY)
    log.info("🔑  Gemini client initialized for SEO analysis")

    SEO_PROMPT = (
        "Act as an elite dual-platform Growth Strategist specializing in "
        "YouTube Shorts/long-form AND Instagram Reels, with deep expertise in "
        "CTR, AVD, and Reels algorithm optimization.\n\n"
        "TRENDING CONTEXT: FIFA and football content is currently experiencing "
        "a massive surge. Think FIFA 26 hype, World Cup 2026, "
        "transfer window drama, legendary player moments, skills compilations, "
        "match highlights, and football edits. Lean HARD into this trend.\n\n"
        "Watch this video file carefully, analyzing the visual pacing, the "
        "3-second hook, on-screen text, emotional shifts, and audio. "
        "Generate a DUAL-PLATFORM SEO package formatted exactly as follows:\n\n"
        "--- YOUTUBE SEO ---\n"
        "1. Titles (CTR Engine): 5 titles under 60 characters. "
        "2 Curiosity Gap, 2 High-Emotion/Hype, 1 Direct Search. "
        "Weave in trending FIFA/football keywords.\n"
        "2. The Hook Critique: Analyze the first 3 seconds.\n"
        "3. YouTube Description: A punchy 125-character preview snippet, "
        "followed by a 3-paragraph keyword-rich natural language summary.\n"
        "4. YouTube Tags: 3-5 hashtags and 15 semantic long-tail tags.\n\n"
        "--- INSTAGRAM REELS SEO ---\n"
        "5. Reels Caption: Scroll-stopping 1-liner caption.\n"
        "6. Reels Hashtags: 20-25 hashtags in a copy-paste-ready block.\n"
        "7. Reels Audio Suggestion: 2-3 trending audio tracks.\n"
        "8. Best Posting Window: Optimal day/time for global audience."
    )

    md_files = []
    for clip in clips:
        log.info("📹  Analyzing: %s", clip.name)

        try:
            # Upload video to Gemini Files API
            mime = "video/mp4"
            uploaded = client.files.upload(
                file=clip,
                config=types.UploadFileConfig(
                    mime_type=mime,
                    display_name=clip.name,
                ),
            )
            log.info("   ☁️  Uploaded to Gemini: %s", uploaded.name)

            # Wait for processing
            while True:
                status = client.files.get(name=uploaded.name)
                state = status.state.name if hasattr(status.state, "name") else str(status.state)
                if state == "ACTIVE":
                    break
                if state == "FAILED":
                    log.error("   ❌  Gemini processing failed for %s", clip.name)
                    break
                log.info("   ⏳  Processing: %s", state)
                time.sleep(10)

            if state != "ACTIVE":
                continue

            # Run inference
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_uri(
                                file_uri=status.uri,
                                mime_type=status.mime_type,
                            ),
                            types.Part.from_text(text=SEO_PROMPT),
                        ],
                    )
                ],
            )

            if response.text:
                # Write .md file next to the clip
                md_path = clip.with_suffix(".md")
                header = (
                    f"# YouTube SEO Metadata — {clip.stem}\n"
                    f"> Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                    f"by FIFA Automation Pipeline\n\n---\n\n"
                )
                md_path.write_text(header + response.text, encoding="utf-8")
                md_files.append(str(md_path))
                log.info("   ✅  SEO metadata saved: %s", md_path.name)
            else:
                log.error("   ❌  Empty response from Gemini for %s", clip.name)

            # Cleanup remote file
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass

        except Exception as e:
            log.error("   ❌  SEO error for %s: %s", clip.name, str(e)[:200])
            continue

    log.info("🎯  SEO metadata generated for %d/%d clips", len(md_files), len(clips))
    return md_files


# ─────────────────────────── Step 4: Upload ───────────────────

def upload_clips(output_dir: str) -> int:
    """
    Upload all clips in the output directory to YouTube using upload.py.
    Returns the number of successfully uploaded videos.
    """
    log.info("=" * 60)
    log.info("📤  STEP 4: Uploading clips to YouTube...")
    log.info("=" * 60)

    try:
        result = subprocess.run(
            [PYTHON_EXE, UPLOAD_PY, "--batch", output_dir],
            cwd=str(PROJECT_ROOT),
            timeout=600,  # 10 min timeout for uploads
        )

        if result.returncode == 0:
            log.info("✅  Upload complete!")
            return 1
        else:
            log.error("❌  Upload failed with exit code %d", result.returncode)
            return 0

    except subprocess.TimeoutExpired:
        log.error("❌  Upload timed out after 10 minutes.")
        return 0
    except Exception as e:
        log.error("❌  Upload error: %s", e)
        return 0


# ─────────────────────────── Main Orchestrator ────────────────

def run_full_pipeline():
    """
    The complete automated pipeline:
    1. Scan FIFA channel for new highlights
    2. Generate clips from the first new highlight
    3. Run SEO agent
    4. Upload to YouTube
    """
    banner = r"""
    ╔══════════════════════════════════════════════════════════╗
    ║     FIFA AUTOMATION PIPELINE — Full Orchestrator        ║
    ║     ─────────────────────────────────────                ║
    ║   Monitor → Clip → SEO → Upload — All Automated!       ║
    ╚══════════════════════════════════════════════════════════╝
    """
    print(banner)

    start_time = time.time()

    # Step 1: Find new highlights
    new_highlights = scan_for_new_highlights()
    if not new_highlights:
        log.info("💤  No new highlights. Pipeline idle.")
        return

    # Process only the first new highlight (to stay within quotas)
    target = new_highlights[0]
    log.info("🎯  Processing: %s", target["title"])

    # Step 2: Generate clips
    output_dir = generate_clips(target["url"], num_clips=3)
    if not output_dir:
        log.error("💀  Pipeline halted: clip generation failed.")
        return

    # Step 3: Run SEO agent
    seo_files = run_seo_on_clips(output_dir)
    if not seo_files:
        log.warning("⚠️  SEO generation failed, uploading with basic metadata...")

    # Step 4: Upload
    uploaded = upload_clips(output_dir)

    # Mark as processed
    from monitor import mark_as_processed
    mark_as_processed(target["id"])

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("🎉  PIPELINE COMPLETE!")
    log.info("   Video: %s", target["title"][:60])
    log.info("   Clips uploaded: %d", uploaded)
    log.info("   SEO files: %d", len(seo_files))
    log.info("   Total time: %.1f minutes", elapsed / 60)
    log.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="FIFA Automation Orchestrator")
    parser.add_argument("--scan-only", action="store_true",
                       help="Just scan the channel, don't process")
    parser.add_argument("--process-only", type=str, metavar="URL",
                       help="Process a specific YouTube URL")
    parser.add_argument("--upload-only", type=str, metavar="DIR",
                       help="Upload already-processed clips from a directory")
    parser.add_argument("--seo-only", type=str, metavar="DIR",
                       help="Run SEO agent on already-generated clips")
    args = parser.parse_args()

    if args.scan_only:
        scan_for_new_highlights()
    elif args.process_only:
        output_dir = generate_clips(args.process_only, num_clips=3)
        if output_dir:
            seo_files = run_seo_on_clips(output_dir)
            log.info("✅  Clips ready at: %s", output_dir)
            log.info("   SEO files: %d", len(seo_files))
    elif args.upload_only:
        upload_clips(args.upload_only)
    elif args.seo_only:
        run_seo_on_clips(args.seo_only)
    else:
        run_full_pipeline()


if __name__ == "__main__":
    main()
