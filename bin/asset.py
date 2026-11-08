#!/usr/bin/env python3
"""Real asset source CLI (rule 4).

Search and download CC0 textures/HDRIs/models and real archive images
from Poly Haven, ambientCG, Wikimedia Commons and the Library of Congress.
Downloads are archived into assets/shared_library with a .meta.json
licence log by default.

Examples:
    python bin/asset.py search --provider polyhaven --category texture --query "old paper"
    python bin/asset.py search --provider wikimedia --category image --query "1946 map"
    python bin/asset.py download --provider polyhaven --asset-id brick_4 \
        --license cc0 --license-url https://polyhaven.com/license \
        --source-url https://polyhaven.com/a/brick_4 --title "Brick 4" \
        --tags brick,paper-collage --creator "Rob Tuytel"
    python bin/asset.py download --provider wikimedia --download-url https://... \
        --kind image --license public_domain --license-url https://... --title "Map"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.graphics.asset_sources import AssetSources


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search and download real assets with licence provenance."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search a real asset source.")
    search.add_argument(
        "--provider",
        default="any",
        choices=["polyhaven", "ambientcg", "wikimedia", "loc", "any"],
    )
    search.add_argument(
        "--category",
        default="any",
        choices=["texture", "hdri", "model", "image", "photo", "any"],
    )
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)

    download = sub.add_parser("download", help="Download and archive one asset.")
    download.add_argument(
        "--provider",
        required=True,
        choices=["polyhaven", "ambientcg", "wikimedia", "loc"],
    )
    download.add_argument("--asset-id", default="")
    download.add_argument("--download-url", default="")
    download.add_argument(
        "--kind",
        default="texture",
        choices=["texture", "hdri", "model", "image"],
    )
    download.add_argument(
        "--resolution",
        default="1k",
        choices=["1k", "2k", "4k", "8k"],
    )
    download.add_argument("--output-dir", default="")
    download.add_argument(
        "--no-archive",
        action="store_true",
        help="Download only; do not copy into assets/shared_library.",
    )
    download.add_argument("--license", default="unknown")
    download.add_argument("--license-url", default="")
    download.add_argument("--source-url", default="")
    download.add_argument("--creator", default="")
    download.add_argument("--title", default="")
    download.add_argument("--tags", default="")
    download.add_argument("--project-name", default="")

    parser.add_argument("--json", action="store_true", help="Print raw JSON.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    tool = AssetSources()

    if args.command == "search":
        result = tool.execute(
            {
                "operation": "search",
                "provider": args.provider,
                "category": args.category,
                "query": args.query,
                "limit": args.limit,
            }
        )
    else:
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        payload = {
            "operation": "download",
            "provider": args.provider,
            "asset_id": args.asset_id,
            "download_url": args.download_url,
            "kind": args.kind,
            "resolution": args.resolution,
            "archive": not args.no_archive,
            "license": args.license,
            "license_url": args.license_url,
            "source_url": args.source_url,
            "creator": args.creator,
            "title": args.title,
            "tags": tags,
            "project_name": args.project_name,
        }
        if args.output_dir:
            payload["output_dir"] = args.output_dir
        result = tool.execute(payload)

    if args.json or not result.success:
        print(
            json.dumps(
                {"success": result.success, "error": result.error, "data": result.data},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "search":
        data = result.data or {}
        print(f"query: {data.get('query')}  total: {data.get('total')}")
        for item in data.get("results") or []:
            if item.get("error"):
                print(f"  ! {item.get('provider')}: {item['error']}")
                continue
            print(
                f"  [{item.get('provider')}] {item.get('id')}  "
                f"{item.get('license')}  {item.get('title')}\n"
                f"    {item.get('source_url')}"
            )
    else:
        data = result.data or {}
        print(
            f"downloaded: {data.get('downloaded_to')}\n"
            f"archived:   {data.get('archived_to')}\n"
            f"license:    {data.get('license')} "
            f"(checked={data.get('license_checked')})"
        )

    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
