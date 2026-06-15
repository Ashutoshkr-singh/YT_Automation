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
PYTHON_EXE = sys.executable
APP_PY = str(PROJECT_ROOT / "app.py")
UPLOAD_PY = str(PROJECT_ROOT / "upload.py")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


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
    Since app.py now natively generates SEO metadata alongside the clips,
    we just need to locate the .md files and return them.
    """
    log.info("=" * 60)
    log.info("🧠  STEP 3: Preparing SEO Metadata for Upload...")
    log.info("=" * 60)

    output_path = pathlib.Path(output_dir)
    md_files = sorted(output_path.glob("Viral_Short_*.md"))
    
    if md_files:
        log.info("✅  Found %d SEO metadata files.", len(md_files))
        return [str(f) for f in md_files]
    else:
        log.warning("⚠️  No SEO metadata files found.")
        return []




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

    total_uploaded = 0
    total_seo = 0
    
    # Process ALL new highlights, but generate exactly 1 viral clip per video
    for target in new_highlights:
        log.info("🎯  Processing: %s", target["title"])
    
        # Step 2: Generate clips
        output_dir = generate_clips(target["url"], num_clips=1)
        if not output_dir:
            log.error("💀  Clip generation failed for this video. Skipping to next.")
            continue
    
        # Step 3: Run SEO agent
        seo_files = run_seo_on_clips(output_dir)
        if not seo_files:
            log.warning("⚠️  SEO generation failed, uploading with basic metadata...")
    
        # Step 4: Upload
        uploaded = upload_clips(output_dir)
    
        # Mark as processed
        from monitor import mark_as_processed
        mark_as_processed(target["id"])
        
        total_uploaded += uploaded
        total_seo += len(seo_files)

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("🎉  PIPELINE COMPLETE!")
    log.info("   Videos processed: %d", len(new_highlights))
    log.info("   Clips uploaded: %d", total_uploaded)
    log.info("   SEO files: %d", total_seo)
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
        output_dir = generate_clips(args.process_only, num_clips=1)
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
