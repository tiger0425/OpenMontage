#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 YouTube 管理 CLI（凭证复用 + 上传/字幕/播放列表/可见性/元数据）

凭证约定（与 upload_youtube.py 一致）：
  1. client_secret.json 搜索顺序:
     - 环境变量 YOUTUBE_CLIENT_SECRET
     - %USERPROFILE%\\.youtube-upload\\client_secret.json
     - 项目根 client_secret.json
  2. token.json 与 client_secret.json 同目录（可用 YOUTUBE_TOKEN 覆盖）
  3. token 过期自动刷新并回写；无 token 时启动本地浏览器授权

子命令:
  auth status                    检查凭证状态（不弹浏览器）
  upload <video> --title ...     上传视频（可 resumable 断点续传）
  caption <video_id> <srt> ...   上传字幕
  visibility <video_id> ...      设置可见性 private/unlisted/public
  metadata <video_id> ...        更新标题/描述/标签
  playlist list                  列出本人全部播放列表
  playlist create --title ...    创建播放列表
  playlist items <pl> ...        列出播放列表内的视频
  playlist add <pl> <vid>...     往播放列表添加视频
  playlist build <manifest>      按 JSON manifest 批量建列表+加视频（支持断点续传）

示例:
  python bin/youtube.py auth status
  python bin/youtube.py upload out.mp4 --title "My Video" --desc "..." --privacy unlisted --playlist "我的合集"
  python bin/youtube.py playlist build manifests/pi.json
"""

import argparse
import json
import os
import sys
import time
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
DEFAULT_CATEGORY = "28"  # Science & Technology
MAX_RETRY = 5


# ---------------- 凭证 ----------------

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


def get_credentials(client_secret, headless=False):
    token_dir = client_secret.parent
    token_path = os.environ.get("YOUTUBE_TOKEN") or (token_dir / "token.json")
    token_path = Path(token_path)
    if token_path.exists():
        creds = google.oauth2.credentials.Credentials.from_authorized_user_file(
            str(token_path), SCOPES
        )
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            print("[auth] refreshing token...")
            creds.refresh(google.auth.transport.requests.Request())
            if creds.valid:
                token_path.write_text(creds.to_json(), encoding="utf-8")
                print("[auth] token refreshed and saved")
                return creds
    if headless:
        raise SystemExit("ERROR: no valid token (needs interactive login). Run without --headless once.")
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        str(client_secret), SCOPES
    )
    creds = flow.run_local_server(port=0, prompt="consent")
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print("[auth] token saved to %s" % token_path)
    return creds


def get_api(headless=False):
    client_secret = find_client_secret()
    if not client_secret:
        print("ERROR: client_secret.json not found.")
        print("  1. Create an OAuth Client ID (Desktop app) at https://console.cloud.google.com/apis/credentials")
        print("  2. Download client_secret.json to %s\\.youtube-upload\\ or project root" % Path.home())
        sys.exit(1)
    creds = get_credentials(client_secret, headless=headless)
    return build("youtube", "v3", credentials=creds)


# ---------------- 重试工具 ----------------

def retry(fn, what="op", max_attempts=MAX_RETRY):
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except HttpError as e:
            code = e.resp.status
            print("  ! %s attempt %d/%d failed: HTTP %d" % (what, attempt, max_attempts, code))
            if code in (409, 500, 503):
                time.sleep(2 * attempt)
                continue
            raise
        except Exception as e:
            print("  ! %s attempt %d/%d failed: %s" % (what, attempt, max_attempts, type(e).__name__))
            time.sleep(2 * attempt)
    raise RuntimeError("giving up on %s" % what)


# ---------------- 上传 ----------------

def upload_video(youtube, video_path, title, desc="", tags=None, privacy="private", category=DEFAULT_CATEGORY):
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags or [],
            "categoryId": category,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    max_attempts = int(os.environ.get("YT_UPLOAD_ATTEMPTS", "5"))
    for attempt in range(1, max_attempts + 1):
        try:
            media = MediaFileUpload(str(video_path), chunksize=4 * 1024 * 1024, resumable=True)
            req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            print("[upload] attempt %d/%d: %s ..." % (attempt, max_attempts, Path(video_path).name))
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
                time.sleep(5 * attempt)
            else:
                raise
    return None


def upload_caption(youtube, video_id, srt_path, lang, name="Subtitles"):
    srt_path = Path(srt_path)
    if not srt_path.exists():
        print("[captions] skip %s (not found)" % srt_path.name)
        return False
    body = {
        "snippet": {
            "videoId": video_id,
            "language": lang,
            "name": name,
            "isDraft": False,
        }
    }
    media = MediaFileUpload(str(srt_path), mimetype="application/ttml+xml")
    retry(lambda: youtube.captions().insert(part="snippet", body=body, media_body=media).execute(),
          what="caption %s" % srt_path.name)
    print("[captions] uploaded %s (%s)" % (srt_path.name, lang))
    return True


def set_visibility(youtube, video_id, privacy):
    retry(lambda: youtube.videos().update(
        part="status",
        body={"id": video_id, "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}},
    ).execute(), what="set visibility %s" % privacy)
    print("[visibility] %s -> %s" % (video_id, privacy))


def update_metadata(youtube, video_id, title=None, desc=None, tags=None):
    resp = retry(lambda: youtube.videos().list(part="snippet", id=video_id).execute(),
                 what="fetch video %s" % video_id)
    items = resp.get("items", [])
    if not items:
        raise SystemExit("ERROR: video %s not found" % video_id)
    snippet = items[0]["snippet"]
    if title:
        snippet["title"] = title
    if desc is not None:
        snippet["description"] = desc
    if tags is not None:
        snippet["tags"] = tags
    retry(lambda: youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute(),
          what="update metadata")
    print("[metadata] updated %s" % video_id)


# ---------------- 播放列表 ----------------

def resolve_playlist_id(youtube, ref):
    """ref 可以是 playlist ID 或标题。找不到返回 None。"""
    if ref.startswith("PL") and len(ref) > 10:
        return ref
    playlists = list_all_playlists(youtube)
    if ref in playlists:
        return playlists[ref]
    # 标题模糊匹配
    for title, pid in playlists.items():
        if ref.lower() in title.lower():
            return pid
    return None


def list_all_playlists(youtube):
    result = {}
    token = None
    while True:
        req = youtube.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=token)
        resp = retry(lambda: req.execute(), what="list playlists")
        for item in resp.get("items", []):
            result[item["snippet"]["title"]] = item["id"]
        token = resp.get("nextPageToken")
        if not token:
            break
    return result


def create_playlist(youtube, title, desc="", privacy="unlisted"):
    body = {
        "snippet": {"title": title, "description": desc},
        "status": {"privacyStatus": privacy},
    }
    resp = retry(lambda: youtube.playlists().insert(part="snippet,status", body=body).execute(),
                 what="create playlist %r" % title)
    print("[playlist] created: %s -> %s" % (title, resp["id"]))
    return resp["id"]


def playlist_items(youtube, playlist_id):
    ids = set()
    token = None
    while True:
        try:
            req = youtube.playlistItems().list(
                part="contentDetails", playlistId=playlist_id, maxResults=50, pageToken=token
            )
            resp = retry(lambda: req.execute(), what="list playlist items")
        except HttpError as e:
            if e.resp.status == 404:
                return None  # 列表不可访问，需要重建
            raise
        for item in resp.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                ids.add(vid)
        token = resp.get("nextPageToken")
        if not token:
            break
    return ids


def add_to_playlist(youtube, playlist_id, video_id):
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        }
    }
    retry(lambda: youtube.playlistItems().insert(part="snippet", body=body).execute(),
          what="add %s to %s" % (video_id, playlist_id))


def delete_playlist(youtube, playlist_id):
    retry(lambda: youtube.playlists().delete(id=playlist_id).execute(),
          what="delete broken playlist %s" % playlist_id)


def build_from_manifest(youtube, manifest_path):
    """manifest JSON:
    {
      "playlists": [
        {"title": "...", "description": "...", "privacy": "unlisted", "videos": ["id1", ...]},
        ...
      ],
      "master": "总表标题"   # 可选：把所有 videos 也并入该列表
    }
    已存在的列表/条目自动跳过；访问 404 的旧列表删除重建。
    """
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    existing = list_all_playlists(youtube)
    print("[scan] found %d existing playlists" % len(existing))

    master_title = manifest.get("master")
    master_id = None
    master_ids = set()
    if master_title:
        if master_title in existing:
            master_id = existing[master_title]
            got = playlist_items(youtube, master_id)
            if got is None:
                print("[master] broken list, deleting and recreating...")
                delete_playlist(youtube, master_id)
                master_id = create_playlist(youtube, master_title, manifest.get("master_desc", ""))
                master_ids = set()
            else:
                master_ids = got
        else:
            master_id = create_playlist(youtube, master_title, manifest.get("master_desc", ""))
        print("[master] %s has %d videos so far" % (master_id, len(master_ids)))

    for pl in manifest["playlists"]:
        title = pl["title"]
        if title in existing:
            pid = existing[title]
            have = playlist_items(youtube, pid)
            if have is None:
                print("[%s] broken list, deleting and recreating..." % title)
                delete_playlist(youtube, pid)
                pid = create_playlist(youtube, title, pl.get("description", ""), pl.get("privacy", "unlisted"))
                have = set()
            else:
                print("[reuse] %s -> %s" % (title, pid))
        else:
            pid = create_playlist(youtube, title, pl.get("description", ""), pl.get("privacy", "unlisted"))
            existing[title] = pid
            have = set()
            print("[create] %s -> %s" % (title, pid))

        added = 0
        failed = []
        for vid in pl.get("videos", []):
            try:
                if vid not in have:
                    add_to_playlist(youtube, pid, vid)
                    have.add(vid)
                if master_id and vid not in master_ids:
                    add_to_playlist(youtube, master_id, vid)
                    master_ids.add(vid)
                added += 1
            except HttpError as e:
                print("  ! skip %s: HTTP %d" % (vid, e.resp.status))
                failed.append(vid)
        print("[%s] added/verified %d videos, skipped %d" % (title, added, len(failed)))
        if failed:
            print("[%s]   failed: %s" % (title, ", ".join(failed)))

    print("DONE. master=%s  categories=%d" % (master_id, len(manifest["playlists"])))


# ---------------- CLI ----------------

def main():
    parser = argparse.ArgumentParser(description="通用 YouTube 管理 CLI")
    parser.add_argument("--headless", action="store_true", help="不弹浏览器授权（无 token 时报错）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # auth status
    p = sub.add_parser("auth", help="凭证管理")
    p.add_argument("action", choices=["status"])

    # upload
    p = sub.add_parser("upload", help="上传视频")
    p.add_argument("video", type=str)
    p.add_argument("--title", required=True)
    p.add_argument("--desc", default="")
    p.add_argument("--tags", default="", help="逗号分隔")
    p.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    p.add_argument("--category", default=DEFAULT_CATEGORY)
    p.add_argument("--playlist", default=None, help="上传后加入的播放列表（标题或 ID）")
    p.add_argument("--caption", action="append", default=[], metavar="LANG=SRT", help="可多次，如 en=sub.srt")
    p.add_argument("--publish", action="store_true", help="上传后直接设为 public")

    # caption
    p = sub.add_parser("caption", help="上传字幕")
    p.add_argument("video_id", type=str)
    p.add_argument("srt", type=str)
    p.add_argument("--lang", required=True)
    p.add_argument("--name", default="Subtitles")

    # visibility
    p = sub.add_parser("visibility", help="设置可见性")
    p.add_argument("video_id", type=str)
    p.add_argument("--privacy", required=True, choices=["private", "unlisted", "public"])

    # metadata
    p = sub.add_parser("metadata", help="更新元数据")
    p.add_argument("video_id", type=str)
    p.add_argument("--title", default=None)
    p.add_argument("--desc", default=None)
    p.add_argument("--tags", default=None)

    # playlist
    p = sub.add_parser("playlist", help="播放列表操作")
    p.add_argument("action", choices=["list", "create", "items", "add", "build"])
    p.add_argument("--title", default=None)
    p.add_argument("--desc", default="")
    p.add_argument("--privacy", default="unlisted", choices=["private", "unlisted", "public"])
    p.add_argument("--pl", default=None, help="播放列表标题或 ID")
    p.add_argument("--video", action="append", default=[], help="视频 ID（可多次）")
    p.add_argument("manifest", nargs="?", default=None, help="build 用 manifest JSON 路径")

    args = parser.parse_args()

    if args.cmd == "auth":
        client_secret = find_client_secret()
        if not client_secret:
            print("STATUS: client_secret.json NOT FOUND")
            print("  1. Create an OAuth Client ID (Desktop app) at https://console.cloud.google.com/apis/credentials")
            print("  2. Download client_secret.json to %s\\.youtube-upload\\ or project root" % Path.home())
            sys.exit(1)
        token_path = os.environ.get("YOUTUBE_TOKEN") or (client_secret.parent / "token.json")
        if Path(token_path).exists():
            creds = google.oauth2.credentials.Credentials.from_authorized_user_file(str(token_path), SCOPES)
            print("STATUS: token found at %s" % token_path)
            print("  valid=%s expired=%s has_refresh=%s" % (
                creds.valid, creds.expired, bool(creds.refresh_token)))
            print("  scopes=%s" % creds.scopes)
        else:
            print("STATUS: no token yet at %s (will open browser on first use)" % token_path)
        print("  client_secret=%s" % client_secret)
        return

    youtube = get_api(headless=args.headless)

    if args.cmd == "upload":
        video_path = Path(args.video)
        if not video_path.exists():
            raise SystemExit("ERROR: video %s not found" % video_path)
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        privacy = "public" if args.publish else args.privacy
        video_id = upload_video(youtube, video_path, args.title, args.desc, tags, privacy, args.category)
        for cap in args.caption:
            lang, _, srt = cap.partition("=")
            upload_caption(youtube, video_id, srt, lang)
        if args.playlist:
            pid = resolve_playlist_id(youtube, args.playlist)
            if not pid:
                pid = create_playlist(youtube, args.playlist)
            add_to_playlist(youtube, pid, video_id)
        print("DONE. Video: https://youtu.be/%s" % video_id)

    elif args.cmd == "caption":
        upload_caption(youtube, args.video_id, args.srt, args.lang, args.name)

    elif args.cmd == "visibility":
        set_visibility(youtube, args.video_id, args.privacy)

    elif args.cmd == "metadata":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags is not None else None
        update_metadata(youtube, args.video_id, args.title, args.desc, tags)

    elif args.cmd == "playlist":
        if args.action == "list":
            playlists = list_all_playlists(youtube)
            for title, pid in sorted(playlists.items()):
                print("%s  %s" % (pid, title))
            print("TOTAL: %d" % len(playlists))
        elif args.action == "create":
            if not args.title:
                raise SystemExit("ERROR: --title required for create")
            create_playlist(youtube, args.title, args.desc, args.privacy)
        elif args.action == "items":
            pid = resolve_playlist_id(youtube, args.pl)
            if not pid:
                raise SystemExit("ERROR: playlist not found: %s" % args.pl)
            ids = playlist_items(youtube, pid)
            if ids is None:
                raise SystemExit("ERROR: playlist %s inaccessible (404)" % args.pl)
            for vid in sorted(ids):
                print(vid)
            print("TOTAL: %d" % len(ids))
        elif args.action == "add":
            if not args.pl or not args.video:
                raise SystemExit("ERROR: --pl and --video required for add")
            pid = resolve_playlist_id(youtube, args.pl)
            if not pid:
                pid = create_playlist(youtube, args.pl)
            for vid in args.video:
                add_to_playlist(youtube, pid, vid)
                print("[add] %s -> %s" % (vid, pid))
        elif args.action == "build":
            if not args.manifest:
                raise SystemExit("ERROR: manifest path required for build")
            build_from_manifest(youtube, args.manifest)


if __name__ == "__main__":
    main()
