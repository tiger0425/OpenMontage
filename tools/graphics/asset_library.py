"""Global Asset Library management tool.

Local-first asset reuse: search the shared library before generating new assets,
add external-source assets with metadata, track usage counts, and report missing
photos for user decisions (C7).

Library location: assets/shared_library/ (gitignored). Each asset carries a
.meta.json sidecar (see docs/global-asset-library/README.md and
asset_meta.schema.json). AI-generated content is NOT archived (External Asset
Archiving Rule) - only user uploads, web search results, and purchased/licensed
media enter the library.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

# Repository root: tools/graphics/asset_library.py -> repo root is two levels up
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LIBRARY_ROOT = REPO_ROOT / "assets" / "shared_library"
META_SCHEMA = REPO_ROOT / "docs" / "global-asset-library" / "asset_meta.schema.json"

# Directory -> category mapping for the library
CATEGORY_DIRS = {
    "images/photos": "photo",
    "images/textures": "texture",
    "images/decals": "decal",
    "audio/music": "music",
    "audio/sfx": "sfx",
    "fonts": "font",
    "videos": "video",
}


class AssetLibrary(BaseTool):
    name = "asset_library"
    version = "0.1.0"
    tier = ToolTier.SOURCE
    capability = "asset_management"
    provider = "local"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = []
    install_instructions = "No API key needed. Uses local assets/shared_library/."
    agent_skills = []

    capabilities = ["asset_search", "asset_archive", "asset_usage", "missing_photo_report"]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["search", "add", "touch", "missing"],
                "description": (
                    "search: query the library for matching assets before generating. "
                    "add: archive an external-source asset (user upload, web search, purchased) with metadata. "
                    "touch: increment usage_count for an existing library asset. "
                    "missing: list current missing-photo entries (for user decision, C7)."
                ),
            },
            "query": {
                "type": "string",
                "description": "Search keywords/tags for operation=search. Matches against tags, filename, and description.",
            },
            "category": {
                "type": "string",
                "enum": ["photo", "texture", "decal", "music", "sfx", "font", "video"],
                "description": "Asset category filter for search; target category for add.",
            },
            "file_path": {
                "type": "string",
                "description": "Absolute path of the file to archive (operation=add).",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags for operation=add (e.g. [\"real_content\", \"person\", \"crime\", \"1971\"]).",
            },
            "source_type": {
                "type": "string",
                "enum": ["user_upload", "web_search", "purchased", "licensed", "project_preset"],
                "description": "Provenance of the asset for operation=add.",
            },
            "source_url": {
                "type": "string",
                "description": "Original URL for operation=add (web/purchased sources).",
            },
            "license": {
                "type": "string",
                "enum": ["public_domain", "cc0", "cc_by", "commercial", "unknown"],
                "description": "License for operation=add.",
            },
            "description": {
                "type": "string",
                "description": "Short description for operation=add (also matched in search).",
            },
            "asset_path": {
                "type": "string",
                "description": "Path of an already-archived library asset to touch (operation=touch).",
            },
            "project_name": {
                "type": "string",
                "description": "Project name recorded in .meta.json (default 'vox-paper-collage').",
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "Max search results to return.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=64, vram_mb=0, disk_mb=10, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["operation", "query", "category", "file_path"]
    side_effects = [
        "add: copies file into assets/shared_library/ and writes .meta.json",
        "touch: updates usage_count in .meta.json",
    ]
    user_visible_verification = ["search returns expected library assets", "add archives the file with metadata"]

    def get_status(self) -> ToolStatus:
        if LIBRARY_ROOT.is_dir():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0  # local operation, no cost

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_meta(self, asset_path: Path) -> Path | None:
        """Find the .meta.json sidecar for an asset file."""
        meta = asset_path.with_suffix(asset_path.suffix + ".meta.json")
        if meta.exists():
            return meta
        return None

    def _read_meta(self, asset_path: Path) -> dict | None:
        meta = self._find_meta(asset_path)
        if meta is None:
            return None
        with open(meta, encoding="utf-8") as f:
            return json.load(f)

    def _category_dir(self, category: str) -> Path:
        for rel, cat in CATEGORY_DIRS.items():
            if cat == category:
                return LIBRARY_ROOT / rel
        return LIBRARY_ROOT / "images" / "photos"

    def _iter_assets(self) -> list[Path]:
        if not LIBRARY_ROOT.is_dir():
            return []
        return [p for p in LIBRARY_ROOT.rglob("*") if p.is_file() and p.suffix.lower() not in (".json",)]

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def _search(self, inputs: dict[str, Any]) -> ToolResult:
        query = (inputs.get("query") or "").lower().strip()
        category = inputs.get("category")
        limit = inputs.get("limit", 10)
        start = time.time()

        assets = self._iter_assets()
        matches: list[dict] = []

        for path in assets:
            meta = self._read_meta(path) or {}
            tags = " ".join(meta.get("tags", []))
            haystack = " ".join([
                path.name.lower(),
                tags.lower(),
                (meta.get("description") or "").lower(),
                (meta.get("source_description") or "").lower(),
            ])
            asset_category = meta.get("file_type", "")

            # Category filter
            if category:
                cat_match = False
                posix_path = str(path).replace("\\", "/")
                for rel, cat in CATEGORY_DIRS.items():
                    if cat == category and rel in posix_path:
                        cat_match = True
                        break
                if not cat_match:
                    continue

            # Query match: either all tokens appear, or empty query returns everything
            if query:
                tokens = query.split()
                if not all(tok in haystack for tok in tokens):
                    continue

            matches.append({
                "path": str(path),
                "name": path.name,
                "meta": meta,
                "usage_count": meta.get("usage_count", 0),
            })

        matches.sort(key=lambda m: (-m["usage_count"], m["name"]))
        matches = matches[:limit]

        return ToolResult(
            success=True,
            data={
                "total": len(matches),
                "query": query,
                "category": category,
                "results": matches,
                "hint": "If no results, generate new assets via image_selector and archive external sources via add.",
            },
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
        )

    def _add(self, inputs: dict[str, Any]) -> ToolResult:
        file_path = inputs.get("file_path")
        if not file_path:
            return ToolResult(success=False, error="file_path is required for operation=add")
        src = Path(file_path)
        if not src.is_file():
            return ToolResult(success=False, error=f"Source file not found: {src}")

        category = inputs.get("category") or self._guess_category(src)
        target_dir = self._category_dir(category)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Name collision handling: keep original name if free, else suffix
        target = target_dir / src.name
        if target.exists():
            stem = src.stem
            suffix = src.suffix
            counter = 1
            while target.exists():
                target = target_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.copy2(src, target)

        license_val = inputs.get("license", "unknown")
        meta = {
            "version": "1.0",
            "source_type": inputs.get("source_type", "user_upload"),
            "source_url": inputs.get("source_url", ""),
            "source_description": inputs.get("description", ""),
            "tags": inputs.get("tags", []),
            "license": license_val,
            "usage_count": 1,
            "first_used_project": inputs.get("project_name", "vox-paper-collage"),
            "date_added": time.strftime("%Y-%m-%d"),
            "file_type": self._file_type(target),
        }

        # Validate against the meta schema if jsonschema is available
        try:
            import jsonschema
            with open(META_SCHEMA, encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(meta, schema)
        except ImportError:
            pass  # schema validation optional

        meta_path = target.with_suffix(target.suffix + ".meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return ToolResult(
            success=True,
            data={
                "archived_to": str(target),
                "meta_written": str(meta_path),
                "category": category,
                "license": license_val,
            },
            artifacts=[str(target), str(meta_path)],
            cost_usd=0.0,
            duration_seconds=0.0,
        )

    def _touch(self, inputs: dict[str, Any]) -> ToolResult:
        asset_path = inputs.get("asset_path")
        if not asset_path:
            return ToolResult(success=False, error="asset_path is required for operation=touch")
        path = Path(asset_path)
        meta_path = self._find_meta(path)
        if meta_path is None:
            return ToolResult(success=False, error=f"No .meta.json found for {path}")

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        meta["usage_count"] = meta.get("usage_count", 0) + 1
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return ToolResult(
            success=True,
            data={"asset": str(path), "usage_count": meta["usage_count"]},
            cost_usd=0.0,
            duration_seconds=0.0,
        )

    def _missing(self, inputs: dict[str, Any]) -> ToolResult:
        # Missing-photo list is maintained in the project's asset_manifest (schema:
        # missing_photos[]). This operation reads a manifest path if provided.
        manifest_path = inputs.get("asset_path")
        if not manifest_path:
            return ToolResult(
                success=True,
                data={
                    "message": "Pass asset_path pointing to the asset_manifest.json to report missing photos (C7).",
                    "missing_photos": [],
                },
                cost_usd=0.0,
            )
        path = Path(manifest_path)
        if not path.is_file():
            return ToolResult(success=False, error=f"Manifest not found: {path}")
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
        missing = manifest.get("missing_photos", [])
        return ToolResult(
            success=True,
            data={
                "missing_count": len(missing),
                "missing_photos": missing,
                "next_step": "Submit this list to the user for decision: replace photo, change element, or downgrade to creative.",
            },
            cost_usd=0.0,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _guess_category(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
            return "photo"
        if suffix in (".mp3", ".wav", ".flac", ".m4a", ".ogg"):
            return "sfx"
        if suffix in (".ttf", ".otf", ".woff", ".woff2"):
            return "font"
        if suffix in (".mp4", ".webm", ".mov"):
            return "video"
        return "photo"

    def _file_type(self, path: Path) -> str:
        mime = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".svg": "image/svg+xml", ".gif": "image/gif",
            ".mp3": "audio/mpeg", ".wav": "audio/wav", ".flac": "audio/flac",
            ".m4a": "audio/mp4", ".ogg": "audio/ogg",
            ".ttf": "font/ttf", ".otf": "font/otf", ".woff": "font/woff", ".woff2": "font/woff2",
            ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
        }
        return mime.get(path.suffix.lower(), "application/octet-stream")

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if not LIBRARY_ROOT.is_dir():
            LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)

        operation = inputs.get("operation")
        if operation == "search":
            return self._search(inputs)
        if operation == "add":
            return self._add(inputs)
        if operation == "touch":
            return self._touch(inputs)
        if operation == "missing":
            return self._missing(inputs)
        return ToolResult(success=False, error=f"Unknown operation: {operation}")
