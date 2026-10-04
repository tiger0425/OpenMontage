# -*- coding: utf-8 -*-
"""Wikimedia Commons 真实素材抓取工具 (commons_fetcher.py)

从 Wikimedia Commons 抓取高分辨率真车/真实装备/企业Logo/历史档案照片，
并记录来源页、作者、版权许可进 manifest.json，用于后续审核与法律确权。
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "OpenMontage-VoxCollage/1.0 (editorial collage research; contact: local)"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
API = "https://commons.wikimedia.org/w/api.php"


def api_get(params: dict) -> dict:
    p = dict(params)
    p["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(p)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def search_commons(term: str, limit: int = 6, width: int = 1600) -> list[dict]:
    data = api_get({
        "action": "query",
        "generator": "search",
        "gsrsearch": term,
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size|mime",
        "iiurlwidth": str(width),
    })
    pages = (data.get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        if not ii:
            continue
        mime = ii.get("mime", "")
        if not mime.startswith("image/") or "svg" in mime:
            continue
        meta = ii.get("extmetadata") or {}

        def get_val(k):
            return re.sub(r"<[^>]+>", "", str(meta.get(k, {}).get("value", ""))).strip()

        out.append({
            "title": p.get("title", ""),
            "thumb": ii.get("thumburl") or ii.get("url"),
            "orig": ii.get("url"),
            "desc_url": ii.get("descriptionurl", ""),
            "artist": get_val("Artist"),
            "license": get_val("LicenseShortName"),
            "width": ii.get("width", 0),
            "height": ii.get("height", 0),
        })
    # 不要按 title 重排：Commons 的 generator=search 本身按相关性返回，
    # 重排会把“最相关”换成“首字母最靠前”，导致抓到语义不符的图。
    return out


def download_file(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 1024:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:
        print(f"[commons_fetcher] Download error {url}: {e}", file=sys.stderr)
        return False


def fetch_queries(queries: list[dict], out_dir: Path) -> dict:
    """
    queries: [{"key": "ford_puma", "query": "Ford Puma Rally1", "limit": 6}, ...]
    """
    manifest_file = out_dir / "manifest.json"
    manifest = {}
    if manifest_file.exists():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    for q in queries:
        key = q["key"]
        term = q["query"]
        limit = q.get("limit", 6)
        print(f"[commons_fetcher] Searching: '{key}' -> '{term}' (limit={limit})...")
        results = search_commons(term, limit=limit)
        key_dir = out_dir / key
        key_dir.mkdir(parents=True, exist_ok=True)

        stored_items = []
        for idx, item in enumerate(results, start=1):
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", item["title"][:40]).strip("_")
            fname = f"{idx:02d}_{slug}.jpg"
            dest = key_dir / fname
            ok = download_file(item["thumb"], dest)
            if ok:
                rec = dict(item)
                rec["local_path"] = str(dest.relative_to(out_dir))
                stored_items.append(rec)
            time.sleep(0.2)

        manifest[key] = {
            "query": term,
            "count": len(stored_items),
            "items": stored_items,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[commons_fetcher] Done. Saved manifest to {manifest_file}")
    return manifest
