"""
upload.py — YouTube Data API v3 uploader for the Clip-Anything pipeline.

Usage:
  Single upload:
    python upload.py --video path/to/video.mp4 --seo path/to/seo.md

  Single upload (no SEO, uses filename as title):
    python upload.py --video path/to/video.mp4

  Batch upload (all Viral_Short_*.mp4 in a directory):
    python upload.py --batch path/to/output_dir
"""

import os
import sys
import io
import re
import glob
import pickle
import argparse
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLIENT_SECRET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secret.json")
TOKEN_PICKLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.pickle")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# Retry configuration for resumable uploads
MAX_RETRIES = 5
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def get_authenticated_service():
    """
    Build and return an authenticated YouTube Data API service object.
    Loads cached credentials from token.pickle if available, otherwise
    initiates the OAuth2 installed-app flow and caches the new token.
    """
    credentials = None

    # 1. Try loading cached token
    if os.path.exists(TOKEN_PICKLE_PATH):
        print("🔑 Loading cached YouTube credentials...")
        with open(TOKEN_PICKLE_PATH, "rb") as token_file:
            credentials = pickle.load(token_file)

    # 2. Refresh or re-authenticate
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            print("🔄 Refreshing expired YouTube token...")
            try:
                credentials.refresh(Request())
            except Exception as e:
                print(f"   ⚠️ Token refresh failed ({e}). Re-authenticating...")
                credentials = None

        if not credentials:
            if not os.path.exists(CLIENT_SECRET_PATH):
                raise FileNotFoundError(
                    f"❌ client_secret.json not found at {CLIENT_SECRET_PATH}\n"
                    "   Download it from the Google Cloud Console → APIs & Services → Credentials."
                )
            print("🌐 Opening browser for YouTube OAuth2 consent...")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
            credentials = flow.run_local_server(port=0)
            print("✅ YouTube authentication successful!")

        # 3. Persist for next run
        with open(TOKEN_PICKLE_PATH, "wb") as token_file:
            pickle.dump(credentials, token_file)
        print(f"💾 Token saved to {TOKEN_PICKLE_PATH}")

    return build(API_SERVICE_NAME, API_VERSION, credentials=credentials)


# ---------------------------------------------------------------------------
# SEO Markdown Parser
# ---------------------------------------------------------------------------
def parse_seo_markdown(md_path: str) -> dict:
    """
    Parse the SEO agent's markdown output and extract structured metadata.

    Expected sections:
        ### 1. Titles          → first listed title
        ### 3. Description     → preview snippet + full description body
        ### 4. Tags            → 'Semantic Long-Tail Tags' comma-separated line

    Returns dict with keys: title, description, tags (list[str]).
    """
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"❌ SEO markdown not found: {md_path}")

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    result = {"title": "", "description": "", "tags": []}

    # ── Title ──────────────────────────────────────────────────────────────
    # Look for the first title under the "### 1. Titles" (or similar) section
    titles_match = re.search(
        r"###\s*1\.\s*Titles?.*?\n(.*?)(?=\n###|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if titles_match:
        titles_block = titles_match.group(1).strip()
        # Pick the first non-empty line that looks like a title (may start with - or number)
        for line in titles_block.splitlines():
            cleaned = re.sub(r"^[\s\-\d\.\)\*]+", "", line).strip()
            # Strip surrounding quotes if present
            cleaned = cleaned.strip('"').strip("'").strip("`")
            if cleaned:
                result["title"] = cleaned
                break

    # ── Description ────────────────────────────────────────────────────────
    desc_match = re.search(
        r"###\s*3\.\s*.*?Description.*?\n(.*?)(?=\n###|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if desc_match:
        desc_block = desc_match.group(1).strip()
        # Collapse markdown formatting but keep newlines for readability
        desc_lines = []
        for line in desc_block.splitlines():
            stripped = line.strip()
            # Skip sub-header labels like "**Preview Snippet:**"
            if re.match(r"^\*\*.*:\*\*$", stripped):
                continue
            desc_lines.append(stripped)
        result["description"] = "\n".join(desc_lines).strip()

    # ── Tags ───────────────────────────────────────────────────────────────
    tags_match = re.search(
        r"###\s*4\.\s*.*?Tags?.*?\n(.*?)(?=\n###|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if tags_match:
        tags_block = tags_match.group(1).strip()
        # Prefer the "Semantic Long-Tail Tags" line
        longtail_match = re.search(
            r"Semantic\s+Long[\-\s]Tail\s+Tags\s*[:\-–—]\s*(.*)", tags_block, re.IGNORECASE
        )
        if longtail_match:
            raw_tags = longtail_match.group(1)
        else:
            # Fallback: grab the first comma-separated line with 3+ items
            raw_tags = ""
            for line in tags_block.splitlines():
                if line.count(",") >= 2:
                    # Strip leading label like "**Tags:** ..."
                    raw_tags = re.sub(r"^\*\*.*?:\*\*\s*", "", line)
                    break
            if not raw_tags:
                raw_tags = tags_block.splitlines()[0] if tags_block else ""

        result["tags"] = [
            t.strip().strip("#").strip()
            for t in raw_tags.split(",")
            if t.strip()
        ]

    return result


# ---------------------------------------------------------------------------
# Upload (resumable)
# ---------------------------------------------------------------------------
def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list = None,
    category_id: str = "17",
) -> str:
    """
    Upload a single video to YouTube via the Data API v3 resumable upload.

    Args:
        video_path:   Absolute or relative path to the .mp4 file.
        title:        Video title (max 100 chars, truncated automatically).
        description:  Video description.
        tags:         List of tag strings.
        category_id:  YouTube category ID (default '17' = Sports).

    Returns:
        The YouTube video ID on success.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"❌ Video file not found: {video_path}")

    tags = tags or []
    # YouTube title limit = 100 chars
    title = title[:100]

    print(f"\n📤 Uploading: {os.path.basename(video_path)}")
    print(f"   🏷️  Title: {title}")
    print(f"   🏷️  Tags:  {', '.join(tags[:8])}{'…' if len(tags) > 8 else ''}")

    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10 MB chunks
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # ── Resumable upload loop ──────────────────────────────────────────────
    response = None
    retry = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"   ⏫ Uploaded {pct}%")
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES and retry < MAX_RETRIES:
                retry += 1
                wait = 2 ** retry
                print(f"   ⚠️ Retriable HTTP {e.resp.status}. Waiting {wait}s (attempt {retry}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            if retry < MAX_RETRIES:
                retry += 1
                wait = 2 ** retry
                print(f"   ⚠️ Transient error: {e}. Waiting {wait}s (attempt {retry}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise

    video_id = response.get("id", "unknown")
    print(f"   ✅ Upload complete! → https://youtu.be/{video_id}")
    return video_id


# ---------------------------------------------------------------------------
# Batch Upload
# ---------------------------------------------------------------------------
def batch_upload(output_dir: str) -> list:
    """
    Find all Viral_Short_*.mp4 files in `output_dir`, pair each with a
    matching .md SEO file (same stem), and upload sequentially.

    Naming convention expected:
        Viral_Short_1.mp4  →  Viral_Short_1.md  (or Viral_Short_1_seo.md)

    Returns a list of (filename, video_id) tuples for successful uploads.
    """
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(f"❌ Directory not found: {output_dir}")

    pattern = os.path.join(output_dir, "Viral_Short_*.mp4")
    videos = sorted(glob.glob(pattern))

    if not videos:
        print(f"⚠️ No Viral_Short_*.mp4 files found in {output_dir}")
        return []

    print(f"\n🎬 Batch upload: found {len(videos)} video(s) in {output_dir}")

    results = []
    for video_path in videos:
        stem = os.path.splitext(video_path)[0]
        basename = os.path.basename(stem)

        # Search for matching SEO markdown
        seo_candidates = [
            f"{stem}.md",
            f"{stem}_seo.md",
            os.path.join(output_dir, f"{basename}_seo.md"),
        ]
        seo_path = None
        for candidate in seo_candidates:
            if os.path.isfile(candidate):
                seo_path = candidate
                break

        try:
            if seo_path:
                print(f"\n📝 Found SEO metadata: {os.path.basename(seo_path)}")
                seo = parse_seo_markdown(seo_path)
                title = seo["title"] or basename.replace("_", " ")
                description = seo["description"] or f"Viral highlight — {basename}"
                tags = seo["tags"]
            else:
                print(f"\n⚠️ No SEO file for {basename}. Using defaults.")
                title = basename.replace("_", " ")
                description = f"Viral highlight — {basename}"
                tags = []

            video_id = upload_video(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
            )
            results.append((os.path.basename(video_path), video_id))

        except Exception as e:
            print(f"   ❌ Failed to upload {basename}: {e}")
            results.append((os.path.basename(video_path), None))

    # Summary
    print("\n" + "═" * 50)
    print("📊 BATCH UPLOAD SUMMARY")
    print("═" * 50)
    success = sum(1 for _, vid in results if vid)
    failed = len(results) - success
    for filename, vid in results:
        status = f"✅ https://youtu.be/{vid}" if vid else "❌ FAILED"
        print(f"   {filename}  →  {status}")
    print(f"\n   Total: {success} uploaded, {failed} failed")
    print("═" * 50)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Upload videos to YouTube using the Data API v3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python upload.py --video Viral_Short_1.mp4 --seo Viral_Short_1.md
  python upload.py --video Viral_Short_1.mp4
  python upload.py --batch Output__KG3-eXb40M
        """,
    )

    # Mutually exclusive: single upload vs batch
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--video", type=str, help="Path to a single .mp4 file to upload")
    group.add_argument("--batch", type=str, help="Directory containing Viral_Short_*.mp4 files for batch upload")

    parser.add_argument("--seo", type=str, default=None, help="Path to the SEO agent's .md output (single-upload mode only)")
    parser.add_argument("--category", type=str, default="17", help="YouTube category ID (default: 17 = Sports)")

    args = parser.parse_args()

    try:
        # ── Batch mode ────────────────────────────────────────────────────
        if args.batch:
            batch_upload(args.batch)
            return

        # ── Single-video mode ─────────────────────────────────────────────
        video_path = args.video
        if not os.path.isfile(video_path):
            print(f"❌ Video file not found: {video_path}")
            sys.exit(1)

        if args.seo:
            print(f"📝 Parsing SEO metadata from: {args.seo}")
            seo = parse_seo_markdown(args.seo)
            title = seo["title"] or os.path.splitext(os.path.basename(video_path))[0].replace("_", " ")
            description = seo["description"] or "Viral sports highlight"
            tags = seo["tags"]
        else:
            title = os.path.splitext(os.path.basename(video_path))[0].replace("_", " ")
            description = "Viral sports highlight — uploaded via Clip-Anything pipeline"
            tags = []

        upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=tags,
            category_id=args.category,
        )

        print("\n🎉 Upload pipeline complete!")

    except FileNotFoundError as e:
        print(f"\n{e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UPLOAD HALTED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
