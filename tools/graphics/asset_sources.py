"""Real asset source connectors (rule 4).

Give the agent a real library, not a subscription:

  - Poly Haven      — CC0 textures, HDRIs and 3D models
  - ambientCG       — CC0 PBR materials
  - Wikimedia Commons — real archive images, licence per file
  - Library of Congress — real archive images, rights per item

Every search result carries provenance and licence metadata. `download`
streams the file and (by default) archives it into the shared library
with a `.meta.json` licence log, so the asset can be audited and reused.

This tool is deliberately separate from `tools/video/stock_sources`
(which feeds the b-roll corpus): rule 4 is about textures, archive
photos and reference objects, not clips.
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote, urlencode

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)
from tools.graphics.asset_library import AssetLibrary, LIBRARY_ROOT

_PROVIDERS = ("polyhaven", "ambientcg", "wikimedia", "loc")
_UA = "OpenMontage/1.0 (asset-source connector)"


# ---------------------------------------------------------------------------
# HTTP / parsing helpers
# ---------------------------------------------------------------------------


def _get_json(url: str, timeout: int = 45, retries: int = 3) -> Any:
    import requests  # lazy

    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            response = requests.get(
                url, headers={"User-Agent": _UA}, timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - retry transient network errors
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def _strip_html(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _find_url(node: Any, prefer: Iterable[str] = ("jpg", "png", "hdr", "exr", "gltf")) -> Optional[str]:
    """Recursively find the first download URL, preferring known formats."""
    if isinstance(node, dict):
        for key in prefer:
            child = node.get(key)
            if isinstance(child, dict) and isinstance(child.get("url"), str):
                return child["url"]
        if isinstance(node.get("url"), str):
            return node["url"]
        for child in node.values():
            found = _find_url(child, prefer)
            if found:
                return found
    elif isinstance(node, list):
        for child in node:
            found = _find_url(child, prefer)
            if found:
                return found
    return None


def _license_from_wikimedia(short: str, code: str) -> str:
    text = f"{short} {code}".lower()
    if "cc0" in text or "cc-0" in text:
        return "cc0"
    if "public domain" in text or code.lower() == "pd":
        return "public_domain"
    if "by-sa" in text or "by sa" in text:
        return "cc_by_sa"
    if "no known restrictions" in text:
        return "no_known_restrictions"
    if "cc by" in text or "cc-by" in text:
        return "cc_by"
    return "unknown"


def _license_from_loc(rights: Any) -> str:
    if isinstance(rights, list):
        text = " ".join(str(r) for r in rights)
    else:
        text = str(rights or "")
    text = text.lower()
    if "public domain" in text:
        return "public_domain"
    if "no known restrictions" in text:
        return "no_known_restrictions"
    if "restricted" in text or "rights" in text:
        return "rights_managed"
    return "unknown"


def _polyhaven_download_url(
    asset_id: str,
    resolution: str = "1k",
    kind: str = "texture",
) -> Optional[str]:
    files = _get_json(f"https://api.polyhaven.com/files/{quote(asset_id)}")
    if kind == "hdri":
        node = files.get("hdri") or {}
        res_node = node.get(resolution) or node.get("1k") or {}
        return _find_url(res_node, prefer=("hdr", "exr"))
    if kind == "model":
        node = files.get("gltf") or {}
        res_node = node.get(resolution) or node.get("1k") or {}
        inner = res_node.get("gltf") if isinstance(res_node, dict) else None
        if isinstance(inner, dict):
            return inner.get("url") or _find_url(inner)
        return _find_url(res_node)
    # texture: prefer the diffuse map, then any map that has a URL.
    for name in ("Diffuse", "diffuse", "Color", "col"):
        node = files.get(name)
        if isinstance(node, dict):
            res_node = node.get(resolution) or node.get("1k") or {}
            found = _find_url(res_node, prefer=("jpg", "png"))
            if found:
                return found
    for node in files.values():
        if isinstance(node, dict):
            res_node = node.get(resolution) or node.get("1k") or {}
            found = _find_url(res_node, prefer=("jpg", "png"))
            if found:
                return found
    return None


def _ambientcg_download_url(asset_id: str, resolution: str = "1k") -> Optional[str]:
    url = (
        "https://ambientcg.com/api/v2/full_json"
        f"?type=Material&limit=1&q={quote(asset_id)}&include=downloadData"
    )
    data = _get_json(url)
    for asset in data.get("foundAssets") or []:
        if asset.get("assetId") != asset_id:
            continue
        folders = asset.get("downloadFolders") or {}
        default = folders.get("default") or {}
        categories = default.get("downloadFiletypeCategories") or {}
        downloads = (categories.get("zip") or {}).get("downloads") or []
        target = f"{resolution.upper()}-JPG"
        for item in downloads:
            if item.get("attribute") == target:
                return item.get("downloadLink") or item.get("fullDownloadPath")
        if downloads:
            return downloads[0].get("downloadLink") or downloads[0].get("fullDownloadPath")
    # Stable fallback URL pattern used by ambientCG.
    return f"https://ambientcg.com/get?file={asset_id}_{resolution.upper()}-JPG.zip"


def _stream_download(url: str, out_path: Path, retries: int = 3) -> Path:
    import requests  # lazy

    out_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with requests.get(
                url, stream=True, timeout=180, headers={"User-Agent": _UA}
            ) as r:
                r.raise_for_status()
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if chunk:
                            f.write(chunk)
            return out_path
        except Exception as exc:  # noqa: BLE001 - retry transient network errors
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class AssetSources(BaseTool):
    name = "asset_sources"
    version = "0.1.0"
    tier = ToolTier.SOURCE
    capability = "asset_sourcing"
    provider = "multi"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API

    dependencies = ["python:requests"]
    install_instructions = "No API key required. Network access to Poly Haven / ambientCG / Wikimedia / loc.gov."
    agent_skills = []

    capabilities = [
        "search_textures",
        "search_archive_images",
        "download_asset",
        "license_logging",
    ]
    best_for = [
        "sourcing CC0 paper, wood, brass and stone textures for paper-collage scenes",
        "finding real archive photos instead of generating fake ones",
        "building a reusable local asset library with licence provenance",
    ]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["search", "download"],
                "description": "search: find real assets with licence metadata. download: fetch and archive one result.",
            },
            "provider": {
                "type": "string",
                "enum": ["polyhaven", "ambientcg", "wikimedia", "loc", "any"],
                "default": "any",
                "description": "Source provider. 'any' fans out across the providers that fit the category.",
            },
            "query": {
                "type": "string",
                "description": "Search keywords for operation=search.",
            },
            "category": {
                "type": "string",
                "enum": ["texture", "hdri", "model", "image", "photo", "any"],
                "default": "any",
                "description": "Asset category filter.",
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "Max results per provider.",
            },
            "asset_id": {
                "type": "string",
                "description": "Provider asset id for operation=download (polyhaven / ambientcg).",
            },
            "download_url": {
                "type": "string",
                "description": "Direct file URL for operation=download (wikimedia / loc).",
            },
            "kind": {
                "type": "string",
                "enum": ["texture", "hdri", "model", "image"],
                "default": "texture",
                "description": "Asset kind; controls Poly Haven URL resolution.",
            },
            "resolution": {
                "type": "string",
                "enum": ["1k", "2k", "4k", "8k"],
                "default": "1k",
                "description": "Preferred resolution for Poly Haven / ambientCG.",
            },
            "output_dir": {
                "type": "string",
                "description": "Download directory. Defaults to the shared library textures/photos folder.",
            },
            "archive": {
                "type": "boolean",
                "default": True,
                "description": "Archive the download into assets/shared_library with a .meta.json licence log.",
            },
            "license": {
                "type": "string",
                "description": "Licence from the search result (for download).",
            },
            "license_url": {
                "type": "string",
                "description": "Licence text / item page from the search result.",
            },
            "license_checked": {
                "type": "boolean",
                "description": "Whether the licence was explicitly confirmed. Defaults to true for CC0/PD/CC results, false for unknown.",
            },
            "source_url": {
                "type": "string",
                "description": "Landing page from the search result.",
            },
            "creator": {
                "type": "string",
                "description": "Author / institution from the search result.",
            },
            "title": {
                "type": "string",
                "description": "Human-readable title from the search result.",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags to record in the library metadata.",
            },
            "project_name": {
                "type": "string",
                "description": "Project recorded in .meta.json (default 'vox-paper-collage').",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=200, network_required=True
    )
    side_effects = [
        "download: writes a file to output_dir",
        "download+archive: copies the file into assets/shared_library/ and writes .meta.json",
    ]
    user_visible_verification = [
        "search returns results with a licence field",
        "download reports archived_to and license",
    ]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0  # free sources, no API key

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs.get("operation")
        start = time.time()
        try:
            if operation == "search":
                data = self._search(inputs)
            elif operation == "download":
                data = self._download(inputs)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as exc:  # noqa: BLE001 - surface the provider error to the agent
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")

        return ToolResult(
            success=True,
            data=data,
            artifacts=list(data.get("artifacts") or []),
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _search(self, inputs: dict[str, Any]) -> dict[str, Any]:
        query = str(inputs.get("query") or "").strip()
        category = str(inputs.get("category") or "any").lower()
        provider = str(inputs.get("provider") or "any").lower()
        limit = int(inputs.get("limit", 10))

        results: list[dict[str, Any]] = []
        for name in self._providers_for(provider, category):
            try:
                if name == "polyhaven":
                    results.extend(self._search_polyhaven(query, category, limit))
                elif name == "ambientcg":
                    results.extend(self._search_ambientcg(query, limit))
                elif name == "wikimedia":
                    results.extend(self._search_wikimedia(query, limit))
                elif name == "loc":
                    results.extend(self._search_loc(query, limit))
            except Exception as exc:  # noqa: BLE001 - one provider failing must not kill the rest
                results.append(
                    {
                        "provider": name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        return {
            "query": query,
            "category": category,
            "provider": provider,
            "total": len(results),
            "results": results,
            "next_step": (
                "Call operation=download with provider + asset_id (polyhaven/ambientcg) "
                "or provider + download_url (wikimedia/loc), and pass the licence fields "
                "from the chosen result."
            ),
        }

    @staticmethod
    def _providers_for(provider: str, category: str) -> list[str]:
        if provider != "any":
            return [provider]
        if category in ("texture", "hdri", "model"):
            return ["polyhaven"] if category in ("hdri", "model") else ["polyhaven", "ambientcg"]
        if category in ("image", "photo"):
            return ["wikimedia", "loc"]
        return ["polyhaven", "ambientcg", "wikimedia", "loc"]

    def _search_polyhaven(self, query: str, category: str, limit: int) -> list[dict[str, Any]]:
        asset_type = {"texture": "textures", "hdri": "hdris", "model": "models"}.get(
            category, "textures"
        )
        kind = {"textures": "texture", "hdris": "hdri", "models": "model"}[asset_type]
        data = _get_json(f"https://api.polyhaven.com/assets?t={asset_type}")
        q = query.lower()
        out: list[dict[str, Any]] = []
        for asset_id, meta in data.items():
            haystack = " ".join(
                [
                    str(asset_id),
                    str(meta.get("name") or ""),
                    " ".join(meta.get("tags") or []),
                    " ".join(meta.get("categories") or []),
                    str(meta.get("description") or ""),
                ]
            ).lower()
            if q and q not in haystack:
                continue
            thumb = str(meta.get("thumbnail_url") or "")
            if thumb.startswith("/"):
                thumb = "https://cdn.polyhaven.com" + thumb
            authors = meta.get("authors") or {}
            creator = ", ".join(authors.keys()) if isinstance(authors, dict) else ""
            max_res = meta.get("max_resolution") or []
            out.append(
                {
                    "provider": "polyhaven",
                    "id": asset_id,
                    "title": meta.get("name") or asset_id,
                    "kind": kind,
                    "preview_url": thumb,
                    "download_url": "",
                    "license": "cc0",
                    "license_url": "https://polyhaven.com/license",
                    "license_checked": True,
                    "source_url": f"https://polyhaven.com/a/{asset_id}",
                    "creator": creator,
                    "tags": list(meta.get("tags") or []),
                    "resolution": "x".join(str(x) for x in max_res) if max_res else "",
                }
            )
            if len(out) >= limit:
                break
        return out

    def _search_ambientcg(self, query: str, limit: int) -> list[dict[str, Any]]:
        url = (
            "https://ambientcg.com/api/v2/full_json"
            f"?type=Material&limit={limit}&q={quote(query)}"
            "&include=downloadData,previewData"
        )
        data = _get_json(url)
        out: list[dict[str, Any]] = []
        for asset in data.get("foundAssets") or []:
            preview = asset.get("previewImage") or {}
            preview_url = (
                preview.get("256-PNG")
                or preview.get("128-PNG")
                or next(iter(preview.values()), "")
            )
            out.append(
                {
                    "provider": "ambientcg",
                    "id": asset.get("assetId") or "",
                    "title": asset.get("displayName") or asset.get("assetId") or "",
                    "kind": "texture",
                    "preview_url": preview_url,
                    "download_url": "",
                    "license": "cc0",
                    "license_url": "https://ambientcg.com/license",
                    "license_checked": True,
                    "source_url": f"https://ambientcg.com/view?id={asset.get('assetId', '')}",
                    "creator": "ambientCG",
                    "tags": list(asset.get("tags") or []),
                    "resolution": (
                        f"{asset.get('dimensionX', '')}x{asset.get('dimensionY', '')}"
                        if asset.get("dimensionX")
                        else ""
                    ),
                }
            )
        return out

    def _search_wikimedia(self, query: str, limit: int) -> list[dict[str, Any]]:
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 640,
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php?" + urlencode(params)
        data = _get_json(url)
        pages = ((data.get("query") or {}).get("pages") or {})
        out: list[dict[str, Any]] = []
        for page in pages.values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata") or {}
            short = _strip_html((meta.get("LicenseShortName") or {}).get("value"))
            code = _strip_html((meta.get("License") or {}).get("value"))
            license_val = _license_from_wikimedia(short, code)
            description = _strip_html((meta.get("ImageDescription") or {}).get("value"))
            creator = _strip_html((meta.get("Artist") or {}).get("value"))
            out.append(
                {
                    "provider": "wikimedia",
                    "id": str(page.get("pageid") or ""),
                    "title": str(page.get("title") or "").replace("File:", ""),
                    "kind": "image",
                    "preview_url": info.get("thumburl") or "",
                    "download_url": info.get("url") or "",
                    "license": license_val,
                    "license_url": info.get("descriptionurl") or "",
                    "license_checked": True,
                    "source_url": info.get("descriptionurl")
                    or f"https://commons.wikimedia.org/wiki/{page.get('title', '')}",
                    "creator": creator,
                    "tags": [w for w in re.split(r"[;,]", short) if w],
                    "description": description[:300],
                }
            )
        return out

    def _search_loc(self, query: str, limit: int) -> list[dict[str, Any]]:
        url = f"https://www.loc.gov/photos/?q={quote(query)}&fo=json&c={limit}"
        data = _get_json(url, timeout=90)
        results = ((data.get("content") or {}).get("results") or [])
        out: list[dict[str, Any]] = []
        for item in results:
            images = item.get("image_url") or []
            if isinstance(images, str):
                images = [images]
            download_url = self._largest_loc_image(images)
            rights = item.get("rights") or item.get("rights_advisory")
            license_val = _license_from_loc(rights)
            out.append(
                {
                    "provider": "loc",
                    "id": str(item.get("id") or ""),
                    "title": _strip_html(item.get("title")),
                    "kind": "image",
                    "preview_url": download_url,
                    "download_url": download_url,
                    "license": license_val,
                    "license_url": str(item.get("id") or item.get("url") or ""),
                    "license_checked": False,
                    "source_url": str(item.get("id") or item.get("url") or ""),
                    "creator": "",
                    "tags": list(item.get("partof") or [])[:8],
                    "description": _strip_html(" ".join(item.get("description") or []))[:300],
                }
            )
        return out

    @staticmethod
    def _largest_loc_image(images: list[str]) -> str:
        def score(url: str) -> int:
            match = re.search(r"[#&]h=(\d+)", url)
            if match:
                return int(match.group(1))
            lowered = url.lower()
            if lowered.endswith("v.jpg"):
                return 1024
            if lowered.endswith("r.jpg"):
                return 640
            if "_150px" in lowered or lowered.endswith("t.gif"):
                return 150
            return 0

        best_url = ""
        best_score = -1
        for raw in images:
            if not isinstance(raw, str):
                continue
            current = score(raw)
            if current > best_score:
                best_score = current
                best_url = raw.split("#")[0]
        return best_url

    # ------------------------------------------------------------------
    # Download + archive
    # ------------------------------------------------------------------

    def _download(self, inputs: dict[str, Any]) -> dict[str, Any]:
        provider = str(inputs.get("provider") or "").lower()
        if provider not in _PROVIDERS:
            raise ValueError(f"provider must be one of {_PROVIDERS}")

        asset_id = str(inputs.get("asset_id") or "").strip()
        download_url = str(inputs.get("download_url") or "").strip()
        kind = str(inputs.get("kind") or "texture").lower()
        resolution = str(inputs.get("resolution") or "1k").lower()

        if not download_url:
            if provider == "polyhaven":
                if not asset_id:
                    raise ValueError("asset_id is required for polyhaven downloads")
                download_url = _polyhaven_download_url(asset_id, resolution, kind) or ""
            elif provider == "ambientcg":
                if not asset_id:
                    raise ValueError("asset_id is required for ambientcg downloads")
                download_url = _ambientcg_download_url(asset_id, resolution) or ""
            else:
                raise ValueError(f"download_url is required for provider {provider!r}")

        if not download_url:
            raise ValueError(f"could not resolve a download URL for {provider}/{asset_id}")

        suffix = Path(download_url.split("?")[0]).suffix.lower() or ".bin"
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", asset_id or provider)
        filename = f"{provider}_{safe_id}{suffix}"

        archive = bool(inputs.get("archive", True))
        default_root = LIBRARY_ROOT / "images" / ("textures" if kind in ("texture", "hdri", "model") else "photos")
        output_dir = Path(inputs.get("output_dir") or default_root)

        if archive:
            tmp_dir = Path(tempfile.mkdtemp(prefix="omo_asset_"))
            download_path = tmp_dir / filename
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            download_path = output_dir / filename

        _stream_download(download_url, download_path)

        license_val = inputs.get("license") or "unknown"
        license_checked = inputs.get("license_checked")
        if license_checked is None:
            license_checked = license_val in (
                "cc0",
                "public_domain",
                "cc_by",
                "cc_by_sa",
                "no_known_restrictions",
            )

        data: dict[str, Any] = {
            "provider": provider,
            "asset_id": asset_id,
            "download_url": download_url,
            "downloaded_to": str(download_path),
            "license": license_val,
            "license_url": inputs.get("license_url") or "",
            "license_checked": bool(license_checked),
            "source_url": inputs.get("source_url") or "",
            "artifacts": [str(download_path)],
        }

        if archive:
            category = "texture" if kind in ("texture", "hdri", "model") else "photo"
            library = AssetLibrary()
            result = library.execute(
                {
                    "operation": "add",
                    "file_path": str(download_path),
                    "category": category,
                    "tags": inputs.get("tags") or [],
                    "source_type": "web_search",
                    "source_url": inputs.get("source_url") or "",
                    "source_provider": provider,
                    "license": inputs.get("license") or "unknown",
                    "license_url": inputs.get("license_url") or "",
                    "license_checked": bool(license_checked),
                    "creator": inputs.get("creator") or "",
                    "description": inputs.get("title") or filename,
                    "project_name": inputs.get("project_name") or "vox-paper-collage",
                }
            )
            if not result.success:
                raise RuntimeError(f"archive failed: {result.error}")
            data.update(
                {
                    "archived_to": result.data.get("archived_to"),
                    "meta_written": result.data.get("meta_written"),
                    "category": result.data.get("category"),
                    "artifacts": list(result.artifacts),
                }
            )
            try:
                download_path.unlink(missing_ok=True)
            except OSError:
                pass

        return data


__all__ = ["AssetSources"]
