#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube 自动化上传工具（series-adapt 系列用）

功能:
  1. 上传视频（读 publish/metadata.json 的标题/描述/标签）
  2. 上传英/中 SRT 字幕
  3. 创建/复用 "Iron Dragon" 系列播放列表并加入视频
  4. 更新 publish/publish_log.json 的 upload_status

用法:
  python bin/upload_youtube.py <episode_dir>
  例: python bin/upload_youtube.py projects/series-adapt-99/ep-01

首次运行:
  1. 在 Google Cloud Console 创建 OAuth Client ID (Desktop app 类型),
     下载 client_secret.json 放到项目根或 %USERPROFILE%\\.youtube-upload\\
  2. 运行本脚本, 浏览器弹出授权页, 登录 Google 账号并授权
  3. token.json 自动保存, 后续无需再授权

环境变量:
  YOUTUBE_CLIENT_SECRET   client_secret.json 路径 (默认自动搜索)
  或
  YOUTUBE_TOKEN           token.json 路径 (默认与 client_secret 同目录)
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import google.auth.transport.requests
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
PLAYLIST_NAME = "Iron Dragon - The Story of China's Tanks"
PLAYLIST_DESC = (
    "The story of China's tanks and the engineers who built them - "
    "an original English documentary series."
)


def find_client_secret():
    env = os.environ.get("YOUTUBE_CLIENT_SECRET")
    if env and Path(env).exists():
        return Path(env)
    candidates = [
        Path.home() / ".youtube-upload" / "client_secret.json",
        Path("client_secret.json"),
        Path(__file__).resolve().parent.parent / "client_secret.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def get_credentials(client_secret):
    token_dir = client_secret.parent
    token_path = os.environ.get("YOUTUBE_TOKEN") or (token_dir / "token.json")
    token_path = Path(token_path)
    if token_path.exists():
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            str(token_path), SCOPES
        )
        if creds.valid:
            return creds, token_path
        if creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
            if creds.valid:
                token_path.write_text(creds.to_json(), encoding="utf-8")
                print("[auth] token refreshed")
                return creds, token_path
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        str(client_secret), SCOPES
    )
    creds = flow.run_local_server(port=0, prompt="consent")
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print("[auth] token saved to %s" % token_path)
    return creds, token_path


def upload_video(youtube, video_path, metadata):
    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata.get("tags", []),
            "categoryId": "28",  # Science & Technology
            "defaultLanguage": metadata.get("language", "en"),
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": metadata.get("visibility", "private"),
            "selfDeclaredMadeForKids": False,
        },
    }
    max_attempts = int(os.environ.get("YT_UPLOAD_ATTEMPTS", "5"))
    for attempt in range(1, max_attempts + 1):
        try:
            media = MediaFileUpload(str(video_path), chunksize=4 * 1024 * 1024, resumable=True)
            req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            video_id = None
            print("[upload] attempt %d/%d: %s ..." % (attempt, max_attempts, video_path.name))
            while True:
                status, resp = req.next_chunk()
                if resp:
                    video_id = resp["id"]
                    print("\n[upload] video_id = %s" % video_id)
                    return video_id
                if status:
                    pct = int(status.progress() * 100)
                    print("[upload] progress %d%%" % pct, end="\r", flush=True)
        except Exception as e:
            print("\n[upload] attempt %d failed: %s" % (attempt, type(e).__name__), flush=True)
            if attempt < max_attempts:
                import time
                time.sleep(5 * attempt)
            else:
                raise
    return None


def upload_caption(youtube, video_id, srt_path, lang, name):
    if not srt_path.exists():
        print("[captions] skip %s (not found)" % srt_path.name)
        return
    body = {
        "snippet": {
            "videoId": video_id,
            "language": lang,
            "name": name,
            "isDraft": False,
        }
    }
    media = MediaFileUpload(str(srt_path), mimetype="application/ttml+xml")
    try:
        youtube.captions().insert(part="snippet", body=body, media_body=media).execute()
        print("[captions] uploaded %s (%s)" % (srt_path.name, lang))
    except HttpError as e:
        print("[captions] FAILED %s: %s" % (srt_path.name, e))


def ensure_playlist(youtube):
    req = youtube.playlists().list(
        part="snippet", mine=True, maxResults=50
    )
    for item in req.execute().get("items", []):
        if item["snippet"]["title"] == PLAYLIST_NAME:
            print("[playlist] found existing: %s" % item["id"])
            return item["id"]
    body = {
        "snippet": {"title": PLAYLIST_NAME, "description": PLAYLIST_DESC},
        "status": {"privacyStatus": "public"},
    }
    resp = youtube.playlists().insert(part="snippet,status", body=body).execute()
    print("[playlist] created: %s" % resp["id"])
    return resp["id"]


def add_to_playlist(youtube, playlist_id, video_id):
    body = {"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
    youtube.playlistItems().insert(part="snippet", body=body).execute()
    print("[playlist] added video %s" % video_id)


def update_metadata(youtube, video_id, metadata):
    resp = youtube.videos().list(part="snippet", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        print("[update] video %s not found" % video_id)
        return False
    snippet = items[0]["snippet"]
    snippet["title"] = metadata["title"]
    snippet["description"] = metadata["description"]
    snippet["tags"] = metadata.get("tags", [])
    snippet["categoryId"] = "28"
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    print("[update] metadata updated for %s" % video_id)
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload a series-adapt episode to YouTube")
    parser.add_argument("episode_dir", type=str, help="episode dir, e.g. projects/series-adapt-99/ep-01")
    parser.add_argument("--playlist", action="store_true", default=True, help="add to Iron Dragon playlist (default)")
    parser.add_argument("--no-playlist", action="store_true", help="skip playlist")
    parser.add_argument("--publish", action="store_true", help="set visibility to public")
    parser.add_argument("--update-only", action="store_true", help="only update metadata of already-uploaded video (video_id from publish_log)")
    args = parser.parse_args()

    ep = Path(args.episode_dir).resolve()
    meta_path = ep / "publish" / "metadata.json"
    if not meta_path.exists():
        print("ERROR: %s not found. Run publish step first." % meta_path)
        sys.exit(1)
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    video_id = None
    video_path = None
    if args.update_only:
        log_path = ep / "publish" / "publish_log.json"
        if not log_path.exists():
            print("ERROR: publish_log.json not found (need video_id for --update-only)")
            sys.exit(1)
        log = json.loads(log_path.read_text(encoding="utf-8"))
        video_id = log.get("youtube", {}).get("video_id")
        if not video_id:
            print("ERROR: video_id not in publish_log.json (upload first, then --update-only)")
            sys.exit(1)
    else:
        video_path = ep / metadata.get("video_path", "vox-ep01-nosub.mp4")
        if not video_path.exists():
            print("ERROR: video %s not found" % video_path)
            sys.exit(1)

    client_secret = find_client_secret()
    if not client_secret:
        print("ERROR: client_secret.json not found.")
        print("  1. Create an OAuth Client ID (Desktop app) at https://console.cloud.google.com/apis/credentials")
        print("  2. Download client_secret.json to %s\\.youtube-upload\\ or project root" % Path.home())
        sys.exit(1)

    creds, _ = get_credentials(client_secret)
    youtube = build("youtube", "v3", credentials=creds)

    if args.update_only:
        update_metadata(youtube, video_id, metadata)
    else:
        video_id = upload_video(youtube, video_path, metadata)

        srt_dir = ep / "publish" / "srt"
        upload_caption(youtube, video_id, srt_dir / "ep01.en.srt", "en", "English")
        upload_caption(youtube, video_id, srt_dir / "ep01.zh.srt", "zh-Hans", "Chinese (Simplified)")

        if args.playlist and not args.no_playlist:
            pid = ensure_playlist(youtube)
            add_to_playlist(youtube, pid, video_id)

    if args.publish:
        youtube.videos().update(
            part="status",
            body={"id": video_id, "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}},
        ).execute()
        print("[publish] video set to PUBLIC")

    log_path = ep / "publish" / "publish_log.json"
    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
        log["youtube"]["video_id"] = video_id
        log["upload_status"] = "published" if args.publish else "uploaded_private"
        import datetime
        log["published_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[log] publish_log.json updated")

    print("DONE. Video: https://youtu.be/%s" % video_id)


if __name__ == "__main__":
    main()
