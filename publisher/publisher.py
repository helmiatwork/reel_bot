# ═══════════════════════════════════════════════════════════════
# publisher.py — Gap 3: Auto-publish to platforms
# YouTube · TikTok · Instagram Reels
# ═══════════════════════════════════════════════════════════════

import os, json, time, httpx
from pathlib import Path

# ── YouTube ────────────────────────────────────────────────────
def publish_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list,
    privacy: str = "private",     # private → you review → make public
    credentials_file: str = None
) -> dict:
    """
    Upload video to YouTube via Data API v3.
    Uses resumable upload protocol.

    privacy options: private, unlisted, public
    Default is 'private' — safer, you review before publishing.

    Setup:
      1. Create project at console.cloud.google.com
      2. Enable YouTube Data API v3
      3. Create OAuth 2.0 credentials → download as client_secrets.json
      4. Run once manually to get token → saved to youtube_token.json
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        import google_auth_oauthlib.flow as flow_module
    except ImportError:
        raise Exception("Install: pip install google-api-python-client google-auth-oauthlib")

    creds_file = credentials_file or os.getenv("YOUTUBE_CREDENTIALS", "client_secrets.json")
    token_file = "youtube_token.json"

    # Load or refresh credentials
    creds = None
    if Path(token_file).exists():
        creds = Credentials.from_authorized_user_file(token_file)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            fl = flow_module.InstalledAppFlow.from_client_secrets_file(
                creds_file,
                scopes=["https://www.googleapis.com/auth/youtube.upload"]
            )
            creds = fl.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    youtube = build("youtube", "v3", credentials=creds)

    print(f"[YouTube] Uploading: {title}")
    media = MediaFileUpload(video_path, chunksize=10*1024*1024, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:30],
                "categoryId": "22"   # People & Blogs — change as needed
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False
            }
        },
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"[YouTube] Upload progress: {pct}%")

    video_id = response["id"]
    video_url = f"https://youtube.com/watch?v={video_id}"
    print(f"[YouTube] Published: {video_url}")
    return {"platform": "youtube", "video_id": video_id, "url": video_url, "privacy": privacy}


# ── TikTok ─────────────────────────────────────────────────────
def publish_tiktok(
    video_path: str,
    caption: str,
    access_token: str = None,
    post_mode: str = "DIRECT_POST"   # or MEDIA_UPLOAD (saves as draft)
) -> dict:
    """
    Upload video to TikTok via Content Posting API v2.

    post_mode:
      DIRECT_POST   — posts immediately to profile
      MEDIA_UPLOAD  — saves to inbox as draft (safer for review)

    Setup:
      1. Register at developers.tiktok.com
      2. Create app → request video.upload + video.publish scopes
      3. Wait for TikTok approval (can take 1-2 weeks)
      4. Implement OAuth flow to get user access_token
    """
    token = access_token or os.getenv("TIKTOK_ACCESS_TOKEN", "")
    if not token:
        raise Exception("TIKTOK_ACCESS_TOKEN not set")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    file_size = Path(video_path).stat().st_size
    print(f"[TikTok] Initiating upload: {Path(video_path).name} ({file_size//1024//1024}MB)")

    # Step 1: Initialize upload
    init_r = httpx.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {
                "title": caption[:2200],
                "privacy_level": "SELF_ONLY",   # private first — review before making public
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1
            },
            "post_mode": post_mode,
            "media_type": "VIDEO"
        },
        timeout=30
    )

    if init_r.status_code != 200:
        raise Exception(f"TikTok init failed: {init_r.text}")

    data = init_r.json().get("data", {})
    publish_id   = data.get("publish_id")
    upload_url   = data.get("upload_url")

    # Step 2: Upload the file
    print(f"[TikTok] Uploading file...")
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_r = httpx.put(
        upload_url,
        content=video_bytes,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{file_size-1}/{file_size}"
        },
        timeout=300
    )

    if upload_r.status_code not in (200, 201):
        raise Exception(f"TikTok upload failed: {upload_r.text}")

    # Step 3: Poll for completion
    print(f"[TikTok] Polling status: {publish_id}")
    for _ in range(20):
        time.sleep(5)
        status_r = httpx.post(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            headers=headers,
            json={"publish_id": publish_id},
            timeout=15
        )
        status = status_r.json().get("data", {}).get("status", "")
        print(f"[TikTok] Status: {status}")
        if status == "PUBLISH_COMPLETE":
            print(f"[TikTok] Published (draft in inbox)")
            return {"platform": "tiktok", "publish_id": publish_id, "status": "published"}
        elif "FAILED" in status:
            raise Exception(f"TikTok publish failed: {status}")

    return {"platform": "tiktok", "publish_id": publish_id, "status": "pending"}


# ── Instagram ──────────────────────────────────────────────────
def publish_instagram(
    video_url: str,        # must be a public URL — upload to S3/Cloudflare first
    caption: str,
    ig_user_id: str = None,
    access_token: str = None,
    share_to_feed: bool = True
) -> dict:
    """
    Publish video as Instagram Reel via Graph API.

    IMPORTANT: Instagram requires a PUBLIC video URL.
    Upload your video to S3/Cloudflare R2/Supabase Storage first,
    then pass the public URL here.

    Setup:
      1. Create Meta developer account
      2. Create app with Instagram Graph API
      3. Connect Instagram Business/Creator account
      4. Get long-lived access token
      5. Get IG User ID from /me endpoint
    """
    user_id = ig_user_id  or os.getenv("IG_USER_ID", "")
    token   = access_token or os.getenv("IG_ACCESS_TOKEN", "")

    if not user_id or not token:
        raise Exception("IG_USER_ID and IG_ACCESS_TOKEN required")

    base = f"https://graph.facebook.com/v19.0/{user_id}"
    params_base = {"access_token": token}

    print(f"[Instagram] Creating Reel container...")

    # Step 1: Create media container
    container_r = httpx.post(
        f"{base}/media",
        params={
            **params_base,
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "share_to_feed": str(share_to_feed).lower()
        },
        timeout=30
    )
    container_r.raise_for_status()
    container_id = container_r.json()["id"]

    # Step 2: Poll until container is ready
    print(f"[Instagram] Waiting for container: {container_id}")
    for _ in range(30):
        time.sleep(10)
        status_r = httpx.get(
            f"https://graph.facebook.com/v19.0/{container_id}",
            params={**params_base, "fields": "status_code,status"}
        )
        sc = status_r.json().get("status_code", "")
        print(f"[Instagram] Container status: {sc}")
        if sc == "FINISHED":
            break
        elif sc == "ERROR":
            raise Exception(f"Instagram container error: {status_r.json()}")

    # Step 3: Publish
    print(f"[Instagram] Publishing...")
    pub_r = httpx.post(
        f"{base}/media_publish",
        params={**params_base, "creation_id": container_id},
        timeout=30
    )
    pub_r.raise_for_status()
    media_id = pub_r.json()["id"]

    print(f"[Instagram] Published: media_id={media_id}")
    return {"platform": "instagram", "media_id": media_id, "status": "published"}


# ── Unified publisher ──────────────────────────────────────────
def publish_all(
    video_path: str,
    public_video_url: str,  # for Instagram (needs public URL)
    script: dict,
    platforms: list,        # ["youtube", "tiktok", "instagram"]
    credentials: dict = {}  # platform credentials
) -> dict:
    """
    Publish to all specified platforms.
    Returns dict of results per platform.
    """
    results = {}

    title    = script.get("title", "Untitled")
    desc     = script.get("conclusion", "") + "\n\n" + script.get("cta", "")
    ig_cap   = script.get("instagram_caption", title)
    tt_cap   = script.get("tiktok_caption", title)
    tags     = script.get("tags", [])

    for platform in platforms:
        print(f"\n[Publisher] Publishing to {platform}...")
        try:
            if platform == "youtube":
                results["youtube"] = publish_youtube(
                    video_path, title, desc, tags,
                    privacy="private"  # always start private
                )
            elif platform == "tiktok":
                results["tiktok"] = publish_tiktok(
                    video_path, tt_cap,
                    access_token=credentials.get("tiktok_token"),
                    post_mode="MEDIA_UPLOAD"  # draft first
                )
            elif platform == "instagram":
                results["instagram"] = publish_instagram(
                    public_video_url, ig_cap,
                    ig_user_id=credentials.get("ig_user_id"),
                    access_token=credentials.get("ig_token")
                )
        except Exception as e:
            results[platform] = {"platform": platform, "error": str(e)}
            print(f"[Publisher] {platform} failed: {e}")

    return results


if __name__ == "__main__":
    import sys
    print("Publisher service ready.")
    print("Supported platforms: youtube, tiktok, instagram")
    print("Set env vars: YOUTUBE_CREDENTIALS, TIKTOK_ACCESS_TOKEN, IG_USER_ID, IG_ACCESS_TOKEN")
