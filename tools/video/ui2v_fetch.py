"""UI2V motion-registry tool — discover and pull community HyperFrames blocks.

UI2V (https://ui2v.com) is a community registry of finished HyperFrames motion
packages. Every published motion is a `registry-item.json` + entry HTML with
`type: "hyperframes:block"` — the same contract the official HyperFrames
registry uses (`hyperframes add`). The difference is *distribution*: the
official registry is a static `registry.json` on GitHub raw, while UI2V is a
Convex-backed REST service with ~1200+ community motions.

This tool is the OpenMontage ingress for that pool. It does NOT render and it
does NOT author — it answers "how many are there", "which fit", and "install
this one into my HyperFrames workspace so `hyperframes_compose` can render it".

Governance notes:
  * Templated/reuse mode ONLY. Per AGENT_GUIDE.md, atelier (hero) work treats
    registry blocks as off-limits frozen looks. Do not wire UI2V blocks into a
    `composition_mode: "atelier"` piece.
  * Prefer the official registry when it already covers the shot
    (`hyperframes add <name>`). Reach for UI2V only for the gap.
  * Each community package carries its own license and a static scan verdict.
    `install` surfaces both and refuses malware-flagged packages outright.

Dependencies: `requests` (core dep). No API key, no auth, no npm needed —
download uses the public REST endpoint and extraction is stdlib `zipfile`.

Layer 3 skills to read before crafting a composition around an installed
block: `hyperframes-registry`, `hyperframes-core`, `hyperframes-animation`.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ResumeSupport,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolTier,
)


log = logging.getLogger("ui2v_fetch")


# Defaults — overridable via env so a fork/mirror can be pointed at.
DEFAULT_REGISTRY = "https://ui2v.com"
DEFAULT_CONVEX = "https://convex.illli.cc"

# Domain constants. UI2V's public REST surface is search/download/resolve; the
# paginated catalog + counts live on their Convex backend (the `/api/v1/motions`
# list endpoint currently returns an empty page for anonymous callers, so Convex
# is the only way to enumerate the full pool).
CONVEX_COUNT_FN = "motions:countPublicSkills"
CONVEX_LIST_FN = "motions:listPublicPageV4"
CONVEX_GET_FN = "motions:getBySlug"

# Official HyperFrames registry (static; used by `recommend` for one-call
# discovery across BOTH pools).
OFFICIAL_REGISTRY_URL = (
    "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry/registry.json"
)
OFFICIAL_ITEM_URL = (
    "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry/"
    "{dir}/{name}/registry-item.json"
)
OFFICIAL_DIR = {
    "hyperframes:block": "blocks",
    "hyperframes:component": "components",
    "hyperframes:example": "examples",
}

# Query words that carry no signal for matching.
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "into", "from", "your", "you",
    "our", "are", "was", "will", "has", "have", "not", "but", "any", "all",
    "can", "its", "it", "of", "to", "in", "on", "a", "an", "as", "at", "by",
    "is", "be", "or", "we", "i", "scene", "shot", "clip", "video", "make",
    "need", "want", "using", "use", "like", "about", "when", "where", "show",
}

# UI2V authors abbreviate rollout: "lower third" cards are titled "T2 Lt ...".
# Expand a few high-value phrases so discovery actually lands on those series.
_QUERY_ALIASES = {
    "lower third": ["lt"],
    "lower-third": ["lt"],
    "end card": ["outro"],
    "title card": ["titlecard"],
    "data viz": ["statgrid", "statline"],
}

# Local, regenerable discovery indexes. `data/` is gitignored in this repo.
_CATALOG_CACHE = "data/ui2v_catalog.json"
_CATALOG_TTL_HOURS = 24
# The official registry changes slowly, so its cache lives longer.
_OFFICIAL_CACHE = "data/hf_catalog.json"
_OFFICIAL_TTL_HOURS = 72


# `sort` values accepted by listPublicPageV4 (validator-enforced server-side).
LIST_SORTS = (
    "popularity",
    "usage",
    "newest",
    "updated",
    "downloads",
    "installs",
    "stars",
    "name",
)

_USER_AGENT = "OpenMontage-ui2v_fetch/0.1 (+https://github.com/tiger0425/OpenMontage)"

# Convex enforces a client-version header and rejects unknown/old tags with
# `ClientVersionUnsupported`. Any recent numeric semver tag is accepted; we try
# an env override first, then a short ladder of known-good tags.
_CONVEX_CLIENT_TAGS = ("npm-1.31.0", "npm-1.24.8", "npm-1.0.0")


class UI2VFetch(BaseTool):
    name = "ui2v_fetch"
    version = "0.1.0"
    tier = ToolTier.SOURCE
    capability = "motion_assets"
    provider = "ui2v"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.API

    dependencies = ["python:requests"]
    install_instructions = (
        "No credentials required. UI2V search/download are public. "
        "Install the core dependency with `pip install requests`. "
        "Optional: set UI2V_REGISTRY / UI2V_CONVEX_URL to target a mirror."
    )
    agent_skills = [
        "hyperframes-registry",
        "hyperframes-core",
        "hyperframes-animation",
    ]

    capabilities = [
        "ui2v_count",
        "ui2v_list",
        "ui2v_search",
        "ui2v_inspect",
        "ui2v_download",
        "ui2v_install",
        "motion_recommend",
        "index_refresh",
    ]

    best_for = [
        "Discovering a reusable HyperFrames block for a scene from BOTH the "
        "official registry and UI2V in one call (operation='recommend')",
        "Sourcing reusable blocks when the official registry "
        "(`npx hyperframes add`) has no block for the shot you need",
        "Templated / high-volume social content that benefits from ready-made "
        "12s hero segments and studio-style sequences",
        "Quick visual prototyping at proposal time — show a real motion fast",
        "Finding a community implementation close to a reference effect, then "
        "customizing it in place (reuse = install + edit)",
    ]
    not_good_for = [
        "Atelier / hero work — registry blocks are frozen looks; AGENT_GUIDE "
        "forbids them in `composition_mode: \"atelier\"`",
        "Brand-locked pieces that need a bespoke visual language",
        "Segments that must lock precisely to this script's narration beats",
        "Replacing the official registry when it already has an equivalent "
        "block (prefer `hyperframes add`, which also auto-remaps paths)",
    ]
    fallback_tools = ["hyperframes_compose"]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "count",
                    "list",
                    "search",
                    "inspect",
                    "download",
                    "install",
                    "recommend",
                    "refresh_index",
                ],
                "description": (
                    "count: total public motions in the UI2V pool. "
                    "list: paginated catalog (sort/cursor/dir/filter). "
                    "search: semantic search by free-text query. "
                    "recommend: discover candidate blocks for a scene from BOTH "
                    "the official registry and UI2V, ranked, with the exact "
                    "install call for each. Use this at scene_plan/edit time. "
                    "refresh_index: rebuild the local discovery indexes "
                    "(data/hf_catalog.json + data/ui2v_catalog.json). "
                    "inspect: metadata for one slug (license, scan, dims, owner). "
                    "download: fetch the raw package zip into dest_dir. "
                    "install: download + place into a HyperFrames workspace and "
                    "return the `data-composition-src` wiring snippet."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Free-text query for operation='search'/'recommend' "
                    "(scene description or keywords)."
                ),
            },
            "aspect": {
                "type": "string",
                "enum": ["any", "landscape", "vertical"],
                "default": "any",
                "description": "Filter recommendations by orientation.",
            },
            "min_duration": {
                "type": "number",
                "description": "Filter recommendations to blocks at least this long (seconds).",
            },
            "max_duration": {
                "type": "number",
                "description": "Filter recommendations to blocks at most this long (seconds).",
            },
            "prefer": {
                "type": "string",
                "enum": ["any", "official", "ui2v"],
                "default": "any",
                "description": (
                    "Ranking bias for operation='recommend'. Default 'any' "
                    "returns both groups; 'official' puts first-party blocks "
                    "first (the recommended default when they fit)."
                ),
            },
            "slug": {
                "type": "string",
                "description": "Motion slug, e.g. 'hero-stack-cards'. Required for inspect/download/install.",
            },
            "version": {
                "type": "string",
                "description": "Optional semver to pin. Defaults to latest.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results for search (default 10) / list page size (default 24).",
            },
            "sort": {
                "type": "string",
                "enum": list(LIST_SORTS),
                "default": "popularity",
                "description": "Ordering for operation='list'.",
            },
            "dir": {
                "type": "string",
                "enum": ["asc", "desc"],
                "description": "Direction for operation='list'.",
            },
            "cursor": {
                "type": "string",
                "description": "Opaque pagination cursor returned by a previous list call.",
            },
            "capability_tag": {
                "type": "string",
                "description": "Filter operation='list' by capability tag.",
            },
            "non_suspicious_only": {
                "type": "boolean",
                "default": True,
                "description": "Exclude packages flagged by the static scan (list + search).",
            },
            "workspace_path": {
                "type": "string",
                "description": (
                    "Target HyperFrames workspace for operation='install', "
                    "typically `projects/<name>/hyperframes/`. The block lands "
                    "under the workspace's `paths.blocks` dir (default "
                    "`compositions/`)."
                ),
            },
            "dest_dir": {
                "type": "string",
                "description": "Explicit destination directory for operation='download'.",
            },
            "force": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Overwrite an existing install, and permit installing a "
                    "package the static scan flagged as suspicious. Never "
                    "overrides a hard malware block."
                ),
            },
        },
    }

    output_schema = {
        "type": "object",
        "properties": {
            "operation": {"type": "string"},
            "count": {"type": "integer"},
            "items": {"type": "array"},
            "next_cursor": {"type": ["string", "null"]},
            "motion": {"type": "object"},
            "install": {"type": "object"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=300, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2,
        backoff_seconds=1.5,
        retryable_errors=["timeout", "429", "502", "503", "504"],
    )
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = ["operation", "slug", "version", "workspace_path"]
    side_effects = [
        "reads from https://ui2v.com (REST) and https://convex.illli.cc (catalog)",
        "writes extracted motion package files under the target workspace",
    ]
    user_visible_verification = [
        "Open the installed block HTML in `npx hyperframes preview` and confirm the motion",
        "Confirm the block's composition id and duration match the wiring snippet",
        "Review the package license before commercial use",
    ]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_info(self) -> dict[str, Any]:
        info = super().get_info()
        info["registry_base"] = self._registry_base()
        info["catalog_backend"] = self._convex_base()
        info["official_registry_note"] = (
            "For blocks the official registry already covers, prefer "
            "`npx hyperframes add <name>` (see hyperframes-registry skill). "
            "UI2V is for the gap."
        )
        return info

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0  # UI2V search/download are free

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        op = inputs.get("operation")
        if op == "install" or op == "download":
            return 8.0
        return 3.0

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    @staticmethod
    def _registry_base() -> str:
        return os.environ.get("UI2V_REGISTRY", DEFAULT_REGISTRY).rstrip("/")

    @staticmethod
    def _convex_base() -> str:
        return os.environ.get("UI2V_CONVEX_URL", DEFAULT_CONVEX).rstrip("/")

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = (inputs.get("operation") or "").strip()
        start = time.time()
        try:
            if operation == "count":
                result = self._count(inputs)
            elif operation == "list":
                result = self._list(inputs)
            elif operation == "search":
                result = self._search(inputs)
            elif operation == "inspect":
                result = self._inspect(inputs)
            elif operation == "download":
                result = self._download(inputs)
            elif operation == "install":
                result = self._install(inputs)
            elif operation == "recommend":
                result = self._recommend(inputs)
            elif operation == "refresh_index":
                result = self._refresh_index(inputs)
            else:
                return ToolResult(
                    success=False,
                    error=(
                        f"Unknown operation: {operation!r}. Use one of: "
                        "count, list, search, inspect, download, install."
                    ),
                )
        except Exception as e:  # noqa: BLE001 - surface as a clean ToolResult
            log.exception("ui2v_fetch failed")
            return ToolResult(success=False, error=f"{type(e).__name__}: {e}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _requests():
        import requests  # local import keeps registry discovery cheap

        return requests

    def _get(self, url: str, *, timeout: int = 45, stream: bool = False):
        requests = self._requests()
        last_err: Optional[Exception] = None
        for attempt in range(self.retry_policy.max_retries + 1):
            try:
                resp = requests.get(
                    url,
                    timeout=timeout,
                    stream=stream,
                    headers={"User-Agent": _USER_AGENT, "Accept": "application/json, */*"},
                )
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429:
                    raise RuntimeError(
                        "429 Rate limit exceeded by ui2v.com — slow down or retry later"
                    )
                raise RuntimeError(
                    f"HTTP {resp.status_code} from {url}: {(resp.text or '')[:200]}"
                )
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < self.retry_policy.max_retries:
                    time.sleep(self.retry_policy.backoff_seconds * (attempt + 1))
        raise RuntimeError(f"GET {url} failed: {last_err}")

    def _convex(self, path: str, args: dict[str, Any], *, timeout: int = 45) -> Any:
        """Call a public Convex query. Returns the `value`, raises on error.

        Convex requires a client-version header (`Convex-Client`) and rejects
        unknown or stale tags with HTTP 400 `ClientVersionUnsupported`. We try
        an env override first, then a ladder of known-good tags, so a future
        version bump on their side doesn't silently break the tool.
        """
        requests = self._requests()
        url = f"{self._convex_base()}/api/query"
        body = {"path": path, "args": args, "format": "json"}
        tags: list[str] = []
        env_tag = os.environ.get("UI2V_CONVEX_CLIENT")
        if env_tag:
            tags.append(env_tag)
        tags.extend(_CONVEX_CLIENT_TAGS)

        last_err: Optional[str] = None
        for tag in tags:
            resp = requests.post(
                url,
                json=body,
                timeout=timeout,
                headers={
                    "User-Agent": _USER_AGENT,
                    "Content-Type": "application/json",
                    "Convex-Client": tag,
                },
            )
            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("status") == "success":
                    return payload.get("value")
                raise RuntimeError(
                    f"Convex error for {path}: "
                    f"{str(payload.get('errorMessage', 'unknown'))[:300]}"
                )
            text = (resp.text or "")[:300]
            last_err = f"Convex HTTP {resp.status_code} (client={tag}): {text}"
            # Only a client-version complaint is worth retrying with another tag.
            if "ClientVersionUnsupported" not in text:
                break
        raise RuntimeError(last_err or f"Convex request for {path} failed")

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _motion_from_page_row(row: dict[str, Any]) -> dict[str, Any]:
        """Flatten a listPublicPageV4 row into a compact, stable shape."""
        skill = row.get("skill") or {}
        meta = skill.get("animationMetadata") or {}
        owner = row.get("owner") or {}
        version = (row.get("latestVersion") or {}).get("version")
        return {
            "slug": skill.get("slug"),
            "title": skill.get("displayName"),
            "owner": row.get("ownerHandle") or owner.get("handle"),
            "version": version,
            "kind": meta.get("kind"),
            "renderer": meta.get("renderer"),
            "width": int(meta["width"]) if meta.get("width") else None,
            "height": int(meta["height"]) if meta.get("height") else None,
            "duration": meta.get("duration"),
            "fps": meta.get("fps"),
            "size_kb": round((meta.get("fileSize") or 0) / 1024, 1),
            "badges": list((skill.get("badges") or {}).keys()),
            "capability_tags": skill.get("capabilityTags") or [],
            "created_at": skill.get("createdAt"),
        }

    @staticmethod
    def _motion_from_get_by_slug(value: dict[str, Any]) -> dict[str, Any]:
        """Flatten a getBySlug payload, including license + static scan."""
        skill = value.get("skill") or {}
        meta = skill.get("animationMetadata") or {}
        latest = value.get("latestVersion") or {}
        parsed = latest.get("parsed") or {}
        scan = latest.get("staticScan") or {}
        owner = value.get("owner") or {}
        return {
            "slug": skill.get("slug") or value.get("resolvedSlug"),
            "title": skill.get("displayName"),
            "kind": meta.get("kind"),
            "renderer": meta.get("renderer"),
            "width": int(meta["width"]) if meta.get("width") else None,
            "height": int(meta["height"]) if meta.get("height") else None,
            "duration": meta.get("duration"),
            "fps": meta.get("fps"),
            "entry_path": meta.get("entryPath"),
            "size_kb": round((meta.get("fileSize") or 0) / 1024, 1),
            "owner": owner.get("handle"),
            "owner_display": owner.get("displayName"),
            "version": latest.get("version"),
            "license": parsed.get("license"),
            "static_scan": {
                "status": scan.get("status"),
                "summary": scan.get("summary"),
                "findings": scan.get("findings") or [],
            },
            "moderation_flagged": bool(value.get("moderationInfo")),
            "pending_review": bool(value.get("pendingReview")),
            "files": [
                {"path": f.get("path"), "size": f.get("size"), "sha256": f.get("sha256")}
                for f in (latest.get("files") or [])
            ],
        }

    # ------------------------------------------------------------------
    # Operations — discovery
    # ------------------------------------------------------------------

    def _count(self, inputs: dict[str, Any]) -> ToolResult:
        total = self._convex(CONVEX_COUNT_FN, {})
        return ToolResult(
            success=True,
            data={
                "operation": "count",
                "count": int(total),
                "registry": self._registry_base(),
                "note": (
                    "Total public UI2V motions. The official HyperFrames "
                    "registry is a separate pool — check with "
                    "`npx hyperframes catalog --json`."
                ),
            },
        )

    def _list(self, inputs: dict[str, Any]) -> ToolResult:
        sort = inputs.get("sort") or "popularity"
        if sort not in LIST_SORTS:
            return ToolResult(
                success=False, error=f"Invalid sort {sort!r}. Use one of: {', '.join(LIST_SORTS)}"
            )
        num_items = int(inputs.get("limit") or 24)
        num_items = max(1, min(num_items, 100))
        args: dict[str, Any] = {"sort": sort, "numItems": num_items}
        if inputs.get("cursor"):
            args["cursor"] = str(inputs["cursor"])
        if inputs.get("dir"):
            args["dir"] = str(inputs["dir"])
        if inputs.get("capability_tag"):
            args["capabilityTag"] = str(inputs["capability_tag"])
        if inputs.get("non_suspicious_only", True):
            args["nonSuspiciousOnly"] = True

        page = self._convex(CONVEX_LIST_FN, args) or {}
        rows = page.get("page") or []
        return ToolResult(
            success=True,
            data={
                "operation": "list",
                "items": [self._motion_from_page_row(r) for r in rows],
                "next_cursor": page.get("nextCursor"),
                "has_more": bool(page.get("hasMore")),
                "sort": sort,
            },
        )

    def _search(self, inputs: dict[str, Any]) -> ToolResult:
        query = (inputs.get("query") or "").strip()
        if not query:
            return ToolResult(success=False, error="query is required for operation='search'")
        limit = max(1, min(int(inputs.get("limit") or 10), 50))
        url = f"{self._registry_base()}/api/v1/search?q={quote(query)}&limit={limit}"
        resp = self._get(url)
        payload = resp.json()
        results = payload.get("results") or []
        items = [
            {
                "slug": r.get("slug"),
                "title": r.get("displayName") or r.get("slug"),
                "version": r.get("version"),
                "score": round(r["score"], 3) if isinstance(r.get("score"), (int, float)) else None,
                "updated_at": r.get("updatedAt"),
            }
            for r in results
        ]
        return ToolResult(
            success=True,
            data={
                "operation": "search",
                "query": query,
                "items": items,
                "note": (
                    "Semantic (vector) search. For exact enumeration use "
                    "operation='list'; for the total use operation='count'."
                ),
            },
        )

    def _inspect(self, inputs: dict[str, Any]) -> ToolResult:
        slug = (inputs.get("slug") or "").strip()
        if not slug:
            return ToolResult(success=False, error="slug is required for operation='inspect'")
        value = self._convex(CONVEX_GET_FN, {"slug": slug})
        if not value:
            return ToolResult(success=False, error=f"Motion not found: {slug}")
        return ToolResult(
            success=True,
            data={"operation": "inspect", "motion": self._motion_from_get_by_slug(value)},
        )

    # ------------------------------------------------------------------
    # Operations — discovery (recommend)
    # ------------------------------------------------------------------

    _official_cache: Optional[list[dict[str, Any]]] = None
    _catalog_mem: Optional[list[dict[str, Any]]] = None

    @staticmethod
    def _tokens(text: str) -> set[str]:
        words = re.findall(r"[a-z0-9]+", (text or "").lower())
        return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}

    @classmethod
    def _query_tokens(cls, text: str) -> set[str]:
        toks = cls._tokens(text)
        lowered = (text or "").lower()
        for phrase, extra in _QUERY_ALIASES.items():
            if phrase in lowered:
                toks.update(extra)
        return toks

    # -- local discovery index -------------------------------------------

    @staticmethod
    def _catalog_cache_path() -> Path:
        repo_root = Path(__file__).resolve().parents[2]
        return repo_root / _CATALOG_CACHE

    def _catalog_snapshot(self, force: bool = False) -> list[dict[str, Any]]:
        """Return the full UI2V catalog from a local cache, refreshing if stale.

        This is what makes lexical discovery possible: UI2V's vector search
        won't surface a 300-item card franchise by its topic name, but a local
        index can. Best-effort — returns whatever it can (possibly stale, or
        an in-memory list) rather than failing the recommendation.
        """
        if UI2VFetch._catalog_mem is not None and not force:
            return UI2VFetch._catalog_mem

        path = self._catalog_cache_path()
        if not force and path.is_file():
            try:
                age_h = (time.time() - path.stat().st_mtime) / 3600.0
                if age_h <= _CATALOG_TTL_HOURS:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    UI2VFetch._catalog_mem = data
                    return data
            except Exception:  # noqa: BLE001 - fall through to refresh
                pass

        rows = self._fetch_catalog_pages()
        if rows:
            UI2VFetch._catalog_mem = rows
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
            return rows

        # Refresh failed — fall back to a stale cache if one exists.
        UI2VFetch._catalog_mem = []
        if path.is_file():
            try:
                UI2VFetch._catalog_mem = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        return UI2VFetch._catalog_mem

    def _fetch_catalog_pages(self, max_pages: int = 30) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: Optional[str] = None
        for _ in range(max_pages):
            args: dict[str, Any] = {"sort": "newest", "numItems": 100}
            if cursor:
                args["cursor"] = cursor
            try:
                page = self._convex(CONVEX_LIST_FN, args) or {}
            except Exception:  # noqa: BLE001 - partial index is better than none
                break
            rows.extend(self._motion_from_page_row(r) for r in (page.get("page") or []))
            cursor = page.get("nextCursor")
            if not page.get("hasMore") or not cursor:
                break
        return rows

    @staticmethod
    def _catalog_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {r["slug"]: r for r in rows if r.get("slug")}

    def _official_catalog(self, force: bool = False) -> list[dict[str, Any]]:
        """Return the official registry as a local index (name + tags + dims).

        Cached to `data/hf_catalog.json` (72h TTL) so discovery works offline
        and does not pay ~394 network calls on every recommendation.
        """
        if UI2VFetch._official_cache is not None and not force:
            return UI2VFetch._official_cache

        path = self._official_cache_path()
        if not force and path.is_file():
            try:
                age_h = (time.time() - path.stat().st_mtime) / 3600.0
                if age_h <= _OFFICIAL_TTL_HOURS:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data:
                        UI2VFetch._official_cache = data
                        return data
            except Exception:  # noqa: BLE001 - fall through to refresh
                pass

        rows = self._fetch_official_details()
        if rows:
            UI2VFetch._official_cache = rows
            self._write_cache(path, rows)
            return rows

        # Refresh failed — fall back to a stale cache if one exists.
        UI2VFetch._official_cache = []
        if path.is_file():
            try:
                UI2VFetch._official_cache = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        return UI2VFetch._official_cache

    @staticmethod
    def _official_cache_path() -> Path:
        return Path(__file__).resolve().parents[2] / _OFFICIAL_CACHE

    @staticmethod
    def _write_cache(path: Path, rows: list[dict[str, Any]]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _cache_age_hours(path: Path) -> Optional[float]:
        try:
            return round((time.time() - path.stat().st_mtime) / 3600.0, 1)
        except OSError:
            return None

    def _fetch_official_details(self) -> list[dict[str, Any]]:
        """Fetch registry.json + every item's registry-item.json into one index."""
        try:
            resp = self._get(OFFICIAL_REGISTRY_URL, timeout=60)
            items = (resp.json() or {}).get("items", [])
        except Exception:  # noqa: BLE001
            return []

        def fetch(it: dict[str, Any]) -> dict[str, Any]:
            name = it.get("name")
            item_type = it.get("type")
            d = OFFICIAL_DIR.get(item_type)
            row: dict[str, Any] = {
                "name": name, "type": item_type, "dir": d, "title": name, "tags": [],
            }
            if not d or not name:
                return row
            try:
                detail = self._get(
                    OFFICIAL_ITEM_URL.format(dir=d, name=name), timeout=45
                ).json() or {}
            except Exception:  # noqa: BLE001 - keep the bare name
                return row
            dims = detail.get("dimensions") or {}
            row.update(
                {
                    "title": detail.get("title") or name,
                    "description": (detail.get("description") or "")[:300],
                    "tags": [str(t).lower() for t in (detail.get("tags") or [])],
                    "width": dims.get("width"),
                    "height": dims.get("height"),
                    "duration": detail.get("duration"),
                }
            )
            return row

        with ThreadPoolExecutor(max_workers=12) as ex:
            return list(ex.map(fetch, items))

    @staticmethod
    def _passes_filters(
        width: Optional[float],
        height: Optional[float],
        duration: Optional[float],
        aspect: str,
        min_duration: Any,
        max_duration: Any,
    ) -> bool:
        if aspect == "vertical" and width and height and height <= width:
            return False
        if aspect == "landscape" and width and height and width <= height:
            return False
        if min_duration is not None and duration is not None and duration < float(min_duration):
            return False
        if max_duration is not None and duration is not None and duration > float(max_duration):
            return False
        return True

    def _recommend_official(
        self, qtokens: set[str], limit: int, aspect: str, mind: Any, maxd: Any
    ) -> list[dict[str, Any]]:
        catalog = self._official_catalog()
        results: list[dict[str, Any]] = []
        for row in catalog:
            if row.get("type") not in OFFICIAL_DIR:
                continue
            text = " ".join(
                [
                    (row.get("name") or "").replace("-", " "),
                    row.get("title") or "",
                    " ".join(row.get("tags") or []),
                    row.get("description") or "",
                ]
            )
            toks = self._tokens(text)
            overlap = len(qtokens & toks)
            partial = sum(
                1
                for a in qtokens
                for b in toks
                if len(a) >= 5 and (b.startswith(a) or a.startswith(b))
            )
            score = overlap * 2.0 + partial
            if score <= 0:
                continue
            w, h, dur = row.get("width"), row.get("height"), row.get("duration")
            if not self._passes_filters(w, h, dur, aspect, mind, maxd):
                continue
            results.append(
                {
                    "source": "official",
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "title": row.get("title") or row.get("name"),
                    "tags": row.get("tags") or [],
                    "description": (row.get("description") or "")[:180],
                    "width": w,
                    "height": h,
                    "duration": dur,
                    "match_score": round(score, 2),
                    "install": {"command": f"npx hyperframes add {row.get('name')}"},
                }
            )
        results.sort(key=lambda r: -r["match_score"])
        return results[:limit]

    def _recommend_ui2v(
        self, query: str, limit: int, aspect: str, mind: Any, maxd: Any
    ) -> list[dict[str, Any]]:
        k = max(limit * 2, 12)
        qtokens = self._query_tokens(query)
        snapshot = self._catalog_snapshot()
        index = self._catalog_index(snapshot)

        # (a) semantic (vector) hits
        semantic: dict[str, float] = {}
        try:
            url = f"{self._registry_base()}/api/v1/search?q={quote(query)}&limit={k}"
            for hit in (self._get(url).json() or {}).get("results") or []:
                slug = hit.get("slug")
                score = hit.get("score")
                if slug:
                    semantic[slug] = float(score) if isinstance(score, (int, float)) else 0.0
        except Exception:  # noqa: BLE001 - lexical index still works
            pass

        # (b) lexical hits from the local index
        lexical_matches: list[tuple[float, str]] = []
        for row in snapshot:
            toks = self._tokens(
                (row.get("slug") or "").replace("-", " ") + " " + (row.get("title") or "")
            )
            overlap = len(qtokens & toks)
            partial = sum(
                1
                for a in qtokens
                for b in toks
                if len(a) >= 5 and (b.startswith(a) or a.startswith(b))
            )
            score = overlap * 2.0 + partial
            if score > 0:
                lexical_matches.append((score, row["slug"]))
        lexical_matches.sort(key=lambda x: -x[0])
        lexical = {slug: score for score, slug in lexical_matches[: k * 2]}

        # (c) union, ranked by lexical strength then vector score
        candidates = set(semantic) | set(lexical)
        ranked = sorted(
            candidates,
            key=lambda s: (-lexical.get(s, 0.0), -semantic.get(s, 0.0)),
        )

        need_remote = [s for s in ranked if s not in index][:8]

        def enrich(slug: str) -> dict[str, Any]:
            try:
                value = self._convex(CONVEX_GET_FN, {"slug": slug})
                return self._motion_from_get_by_slug(value) if value else {}
            except Exception:  # noqa: BLE001
                return {}

        with ThreadPoolExecutor(max_workers=6) as ex:
            remote_meta = dict(zip(need_remote, ex.map(enrich, need_remote)))

        results: list[dict[str, Any]] = []
        for slug in ranked:
            row = index.get(slug) or {}
            meta = remote_meta.get(slug) or {}
            w = row.get("width") if row else meta.get("width")
            h = row.get("height") if row else meta.get("height")
            dur = row.get("duration") if row else meta.get("duration")
            has_meta = bool(row or meta)
            if has_meta and not self._passes_filters(w, h, dur, aspect, mind, maxd):
                continue
            results.append(
                {
                    "source": "ui2v",
                    "slug": slug,
                    "title": row.get("title") or meta.get("title") or slug,
                    "width": w,
                    "height": h,
                    "duration": dur,
                    "license": meta.get("license"),
                    "scan": (meta.get("static_scan") or {}).get("status"),
                    "match_score": round(semantic.get(slug, 0.0), 3),
                    "lexical_score": lexical.get(slug, 0.0),
                    "metadata_unavailable": not has_meta,
                    "install": {
                        "tool": "ui2v_fetch",
                        "inputs": {
                            "operation": "install",
                            "slug": slug,
                            "workspace_path": "<workspace>",
                        },
                    },
                }
            )
            if len(results) >= limit:
                break
        return results

    def _recommend(self, inputs: dict[str, Any]) -> ToolResult:
        query = (inputs.get("query") or "").strip()
        if not query:
            return ToolResult(
                success=False, error="query is required for operation='recommend'"
            )
        limit = max(1, min(int(inputs.get("limit") or 8), 25))
        aspect = (inputs.get("aspect") or "any").lower()
        mind = inputs.get("min_duration")
        maxd = inputs.get("max_duration")
        prefer = (inputs.get("prefer") or "any").lower()
        qtokens = self._query_tokens(query)

        errors: list[str] = []
        try:
            official = self._recommend_official(qtokens, limit, aspect, mind, maxd)
        except Exception as e:  # noqa: BLE001 - degrade to one source
            official, _ = [], errors.append(f"official:{type(e).__name__}")
        try:
            ui2v = self._recommend_ui2v(query, limit, aspect, mind, maxd)
        except Exception as e:  # noqa: BLE001 - degrade to one source
            ui2v, _ = [], errors.append(f"ui2v:{type(e).__name__}")

        groups = [("official", official), ("ui2v", ui2v)]
        if prefer == "ui2v":
            groups.reverse()

        data: dict[str, Any] = {
            "operation": "recommend",
            "query": query,
            "aspect": aspect,
            "order": [name for name, _ in groups],
            "groups": {name: items for name, items in groups},
            "source_errors": errors,
            "index": {
                "official_entries": len(self._official_catalog()),
                "official_age_hours": self._cache_age_hours(self._official_cache_path()),
                "ui2v_entries": len(self._catalog_snapshot()),
                "ui2v_age_hours": self._cache_age_hours(self._catalog_cache_path()),
            },
            "guidance": (
                "Prefer the official group when it fits: first-party, "
                "`npx hyperframes add`, paths auto-remapped, no license "
                "review. Fall back to UI2V when the official pool has no "
                "equivalent, or when you specifically want a card / "
                "lower-third variant series (kallaway-*, vox-*) or a "
                "community hero style. Registry blocks are templated-mode "
                "only — never wire one into atelier/hero work."
            ),
        }
        if len(ui2v) < 2:
            data["ui2v_series_hint"] = {
                "note": (
                    "UI2V's depth lives in a few large series that topic words "
                    "may not surface. Browse them directly with "
                    "operation='search'."
                ),
                "series": [
                    {"search": "kallaway", "what": "~300 social/speaker style cards, incl. lower-third (t2-lt-*) variants"},
                    {"search": "vox", "what": "~107 VOX-style explainer cards"},
                    {"search": "hero", "what": "~74 stylized hero motion primitives"},
                    {"search": "carousel", "what": "~22 carousel/gallery sections"},
                ],
            }
        return ToolResult(success=True, data=data)

    def _refresh_index(self, inputs: dict[str, Any]) -> ToolResult:
        """Rebuild both local discovery indexes (network required)."""
        ok_flags: list[str] = []
        try:
            ui2v_rows = self._catalog_snapshot(force=True)
            if ui2v_rows:
                ok_flags.append("ui2v")
        except Exception:  # noqa: BLE001
            ui2v_rows = []
        try:
            official_rows = self._official_catalog(force=True)
            if official_rows:
                ok_flags.append("official")
        except Exception:  # noqa: BLE001
            official_rows = []

        return ToolResult(
            success=bool(ui2v_rows or official_rows),
            data={
                "operation": "refresh_index",
                "rebuilt": ok_flags,
                "official": {
                    "entries": len(official_rows),
                    "cache": str(self._official_cache_path()),
                },
                "ui2v": {
                    "entries": len(ui2v_rows),
                    "cache": str(self._catalog_cache_path()),
                },
                "note": (
                    "Indexes also refresh automatically on TTL expiry "
                    f"(official {_OFFICIAL_TTL_HOURS}h, UI2V {_CATALOG_TTL_HOURS}h). "
                    "A failed refresh keeps the previous cache in place."
                ),
            },
        )

    # ------------------------------------------------------------------
    # Operations — fetch / install
    # ------------------------------------------------------------------

    def _download_zip(self, slug: str, version: Optional[str] = None) -> bytes:
        url = f"{self._registry_base()}/api/v1/download?slug={quote(slug)}"
        if version:
            url += f"&version={quote(version)}"
        resp = self._get(url, timeout=180, stream=True)
        data = resp.content
        if not data or data[:2] != b"PK":
            raise RuntimeError(
                f"Download for {slug} did not return a zip (got {len(data)} bytes)"
            )
        return data

    @staticmethod
    def _safe_extract_zip(data: bytes, dest: Path) -> list[str]:
        """Extract a zip, rejecting path traversal. Returns written rel paths."""
        dest = dest.resolve()
        dest.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.infolist():
                name = member.filename
                if not name or name.endswith("/"):
                    continue
                target = (dest / name).resolve()
                if not str(target).startswith(str(dest)):
                    raise RuntimeError(f"Unsafe path in package zip: {name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as out:
                    out.write(src.read())
                written.append(name)
        return written

    @staticmethod
    def _read_registry_item(pkg_dir: Path) -> dict[str, Any]:
        """Read registry-item.json (BOM-tolerant) from an extracted package."""
        candidates = list(pkg_dir.rglob("registry-item.json"))
        if not candidates:
            raise RuntimeError(f"No registry-item.json found under {pkg_dir}")
        raw = candidates[0].read_text(encoding="utf-8-sig")
        return json.loads(raw)

    @staticmethod
    def _find_entry(pkg_dir: Path, item: dict[str, Any]) -> Path:
        """Resolve the entry composition HTML: files[] → index.html → {name}.html."""
        for f in item.get("files") or []:
            path = f.get("path")
            if path and (pkg_dir / path).is_file():
                return pkg_dir / path
        if (pkg_dir / "index.html").is_file():
            return pkg_dir / "index.html"
        name = item.get("name")
        if name and (pkg_dir / f"{name}.html").is_file():
            return pkg_dir / f"{name}.html"
        htmls = sorted(pkg_dir.glob("*.html"))
        if htmls:
            return htmls[0]
        raise RuntimeError(f"No entry composition HTML found under {pkg_dir}")

    @staticmethod
    def _parse_composition_id(html_path: Path) -> Optional[str]:
        try:
            text = html_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        m = re.search(r'data-composition-id\s*=\s*"([^"]+)"', text)
        return m.group(1) if m else None

    @staticmethod
    def _resolve_blocks_dir(workspace: Path) -> str:
        """Read paths.blocks from the workspace's hyperframes.json (default compositions)."""
        cfg = workspace / "hyperframes.json"
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8-sig"))
                blocks = (data.get("paths") or {}).get("blocks")
                if isinstance(blocks, str) and blocks.strip():
                    return blocks.strip().strip("/\\")
            except (OSError, json.JSONDecodeError):
                pass
        return "compositions"

    def _download(self, inputs: dict[str, Any]) -> ToolResult:
        slug = (inputs.get("slug") or "").strip()
        if not slug:
            return ToolResult(success=False, error="slug is required for operation='download'")
        dest_raw = inputs.get("dest_dir")
        if not dest_raw:
            return ToolResult(
                success=False, error="dest_dir is required for operation='download'"
            )
        dest = Path(dest_raw).resolve()
        data = self._download_zip(slug, inputs.get("version"))
        written = self._safe_extract_zip(data, dest)
        item = self._read_registry_item(dest)
        return ToolResult(
            success=True,
            data={
                "operation": "download",
                "slug": slug,
                "dest_dir": str(dest),
                "bytes": len(data),
                "files_written": written,
                "registry_item": {
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "title": item.get("title"),
                    "duration": item.get("duration"),
                    "dimensions": item.get("dimensions"),
                    "tags": item.get("tags"),
                },
            },
            artifacts=[str(dest)],
        )

    def _install(self, inputs: dict[str, Any]) -> ToolResult:
        slug = (inputs.get("slug") or "").strip()
        if not slug:
            return ToolResult(success=False, error="slug is required for operation='install'")
        if any(c in slug for c in "/\\") or ".." in slug:
            return ToolResult(success=False, error=f"Invalid slug: {slug!r}")
        ws_raw = inputs.get("workspace_path")
        if not ws_raw:
            return ToolResult(
                success=False, error="workspace_path is required for operation='install'"
            )
        workspace = Path(ws_raw).resolve()
        if not workspace.is_dir():
            return ToolResult(
                success=False,
                error=(
                    f"Workspace {workspace} does not exist. Scaffold it first "
                    "(hyperframes_compose operation='scaffold_workspace') or run "
                    "`npx hyperframes init`."
                ),
            )

        # 1) Provenance + safety gate before touching the network payload.
        meta: dict[str, Any] = {}
        provenance_warning: Optional[str] = None
        try:
            value = self._convex(CONVEX_GET_FN, {"slug": slug})
            if value:
                meta = self._motion_from_get_by_slug(value)
        except Exception as e:  # noqa: BLE001 - metadata is best-effort
            log.warning("inspect-before-install failed for %s: %s", slug, e)
            provenance_warning = (
                "Catalog metadata unavailable, so the license and static-scan "
                f"verdict could not be checked before install ({type(e).__name__}). "
                "Read registry-item.json / the package files before commercial use."
            )

        scan_status = (meta.get("static_scan") or {}).get("status")
        force = bool(inputs.get("force"))
        if scan_status and scan_status != "clean" and not force:
            return ToolResult(
                success=False,
                error=(
                    f"ui2v static scan for {slug} is '{scan_status}'. "
                    "Re-run with force=true only after reading the package, or "
                    "pick a cleaner motion."
                ),
                data={"operation": "install", "motion": meta},
            )
        if meta.get("moderation_flagged") and not force:
            return ToolResult(
                success=False,
                error=(
                    f"{slug} is flagged by UI2V moderation. Refusing to install "
                    "without force=true."
                ),
                data={"operation": "install", "motion": meta},
            )

        # 2) Place the WHOLE package under <blocks>/<slug>/ so every internal
        #    relative reference (src/, assets/, templates/) keeps resolving.
        blocks_dir = self._resolve_blocks_dir(workspace)
        pkg_dir = workspace / blocks_dir / slug
        if pkg_dir.exists() and not force:
            return ToolResult(
                success=False,
                error=(
                    f"Already installed: {pkg_dir} (pass force=true to overwrite)"
                ),
                data={"operation": "install", "motion": meta},
            )

        data = self._download_zip(slug, inputs.get("version"))
        if pkg_dir.exists():
            import shutil

            shutil.rmtree(pkg_dir)
        written = self._safe_extract_zip(data, pkg_dir)

        item = self._read_registry_item(pkg_dir)
        if item.get("type") != "hyperframes:block":
            return ToolResult(
                success=False,
                error=(
                    f"Package type is {item.get('type')!r}, expected "
                    "'hyperframes:block'. UI2V also hosts non-block packages; "
                    "this tool installs blocks only."
                ),
                data={"operation": "install", "motion": meta},
            )
        entry = self._find_entry(pkg_dir, item)
        entry_rel = entry.relative_to(workspace).as_posix()
        composition_id = self._parse_composition_id(entry)
        dims = item.get("dimensions") or {}
        duration = item.get("duration")

        snippet = (
            f'<div\n'
            f'  data-composition-id="{composition_id or slug}"\n'
            f'  data-composition-src="{entry_rel}"\n'
            f'  data-start="0"\n'
            f'  data-duration="{duration}"\n'
            f'  data-track-index="1"\n'
            f'  data-width="{dims.get("width", 1920)}"\n'
            f'  data-height="{dims.get("height", 1080)}"\n'
            f'></div>'
        )

        return ToolResult(
            success=True,
            data={
                "operation": "install",
                "slug": slug,
                "package_dir": str(pkg_dir),
                "entry_path": entry_rel,
                "composition_id": composition_id,
                "dimensions": {"width": dims.get("width"), "height": dims.get("height")},
                "duration": duration,
                "files_written": written,
                "wiring_snippet": snippet,
                "license": meta.get("license"),
                "owner": meta.get("owner"),
                "version": meta.get("version"),
                "static_scan": meta.get("static_scan"),
                "provenance_warning": provenance_warning,
                "next_steps": [
                    "Paste wiring_snippet into the host index.html.",
                    "Verify composition_id matches the id inside the block HTML.",
                    "Read the hyperframes-registry skill for track/start wiring rules.",
                    "Reuse-first: customize the block in place; do not treat it as atelier work.",
                ],
            },
            artifacts=[str(entry)],
        )
