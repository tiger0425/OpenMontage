# UI2V Community Blocks

UI2V (https://ui2v.com) is a **community registry** of finished HyperFrames
motion packages. It is the second source of blocks, alongside the official
registry that `hyperframes add` pulls from.

| | Official registry | UI2V |
| --- | --- | --- |
| Address | `raw.githubusercontent.com/heygen-com/hyperframes/main/registry` | `ui2v.com` (catalog on `convex.illli.cc`) |
| Size | ~394 items (blocks + components + examples) | ~1262 public motions |
| Install | `npx hyperframes add <name>` | `ui2v_fetch` tool → `install` |
| Path remap | automatic via `hyperframes.json#paths` | handled by the tool |
| Trust | first-party, curated | community; per-package license + static scan |

A UI2V motion has the **same contract** as an official block
(`registry-item.json`, `type: "hyperframes:block"`, entry HTML with
`data-composition-id` / `data-duration` / `data-width` / `data-height` and a
paused GSAP timeline on `window.__timelines`). Only the distribution differs.

For a dated, category-by-category coverage comparison (what the official
registry is deep in vs what only UI2V has), see
`docs/registry-coverage.md` at the repo root. Short version: official = composable
primitives + components; UI2V = finished segments, dominated by large card /
lower-third variant franchises (`kallaway-*`, `vox-*`).

## When to reach for UI2V — and when not

Reach for UI2V **only** when all of these hold:

1. `render_runtime` is **HyperFrames** (UI2V packages are HyperFrames blocks).
2. You are in **templated / reuse** mode — compose existing looks, don't invent.
3. The **official registry has no block** for the shot (`npx hyperframes catalog`
   comes up empty after a real search).
4. The block's baked-in art direction won't fight the piece (palette, type,
   pacing).
5. Its license and static-scan verdict are acceptable for the delivery.

Good fits: high-volume social/short-form series, quick proposal-stage demos,
filling a missing stock shot type, adapting a community look close to a
reference effect ("reuse = install + edit").

**Do NOT use UI2V for:**

- **Atelier / hero work.** `AGENT_GUIDE.md` marks registry blocks as
  off-limits frozen looks in `composition_mode: "atelier"`. UI2V blocks are
  even more "canned" than official ones — never wire one into an atelier piece.
- **Brand-locked pieces** that need a bespoke visual language.
- **Beats that must lock to this script's narration** — a third-party block's
  timing was authored for a different edit; retiming it is usually more work
  than authoring the beat.
- **Replacing the official registry.** If `hyperframes add <name>` covers it,
  use that: it's first-party, path-remapped, and never needs a license review.

Decision rule: **HyperFrames + templated + official-registry gap → UI2V.
Hero/atelier or precise timing → author it yourself.**

## The tool

`ui2v_fetch` (`tools/video/ui2v_fetch.py`, capability `motion_assets`,
provider `ui2v`). No API key. Operations:

```python
# ONE-CALL discovery across BOTH registries — start here
{"operation": "recommend", "query": "<scene description>",
 "aspect": "landscape", "max_duration": 8, "limit": 8}
#   → groups.official[] (install: npx hyperframes add <name>)
#   → groups.ui2v[]     (install: ui2v_fetch install <slug>)
#   → ui2v_series_hint  when UI2V has no strong match

# How many motions exist
{"operation": "count"}                       # → 1262 (live)

# Enumerate / browse the catalog
{"operation": "list", "sort": "popularity", "limit": 24}
{"operation": "list", "sort": "newest", "cursor": "<next_cursor>"}
{"operation": "list", "capability_tag": "logo", "non_suspicious_only": True}

# Semantic search (vector search, no exact match)
{"operation": "search", "query": "kinetic logo sting"}

# Metadata before committing (license, static scan, dims, owner)
{"operation": "inspect", "slug": "hero-stack-cards"}

# Install into a HyperFrames workspace
{"operation": "install", "slug": "hero-stack-cards",
 "workspace_path": "projects/<name>/hyperframes"}
```

`recommend` keeps local discovery indexes at `data/hf_catalog.json`
(official, 72h TTL) and `data/ui2v_catalog.json` (UI2V, 24h TTL) — both
gitignored. They make discovery fast and **work offline**: if `npx`, GitHub, or
Convex are unreachable, `recommend` still ranks from the last snapshot. Rebuild
them explicitly with `{"operation": "refresh_index"}`.

### Install one way: `hyperframes_compose.add_block`

The compose tool installs from either registry — use it instead of calling
`npx hyperframes add` by hand:

```python
hyperframes_compose.execute({"operation": "add_block", "block_name": "data-chart",
                             "workspace_path": "<ws>"})                    # official
hyperframes_compose.execute({"operation": "add_block", "block_name": "hero-stack-cards",
                             "source": "ui2v", "workspace_path": "<ws>"})  # UI2V
```

`install` returns a **wiring snippet** and the resolved paths. It also:

- reads the package's `registry-item.json` and refuses anything that is not a
  `hyperframes:block`;
- refuses malware-flagged packages, and suspicious ones unless `force=true`;
- surfaces the package **license** and **static-scan** verdict;
- extracts the **whole package** into `<blocks>/<slug>/` so internal
  references (`src/*.js`, `assets/*`, `templates/*`) keep resolving.

## Installed layout and wiring

```
<workspace>/
├── hyperframes.json
└── compositions/                 # = hyperframes.json#paths.blocks
    └── hero-stack-cards/
        ├── index.html            # entry composition
        ├── registry-item.json    # provenance
        └── assets/ src/ ...      # only if the package ships them
```

Paste the returned snippet into the host `index.html`:

```html
<div
  data-composition-id="main"
  data-composition-src="compositions/hero-stack-cards/index.html"
  data-start="0"
  data-duration="4.5"
  data-track-index="1"
  data-width="1920"
  data-height="1080"
></div>
```

Two gotchas:

- **`data-composition-id` must match the id *inside* the block**, which is not
  always the slug (this example is `"main"`). The tool reads it for you; trust
  the snippet over the slug.
- **`data-start` / `data-duration` are yours to set** — they place the block on
  the host timeline. The tool emits `data-start="0"` as a placeholder.

Then render through the normal path: `hyperframes_compose` (or `video_compose`
with `render_runtime: "hyperframes"`).

## Safety and license

- Each package carries its own `license` (e.g. `MIT-0`). The registry repo's
  own GPL-3.0 does **not** cover community packages. Check per package before
  commercial use.
- The registry runs a static scan (`staticScan.status`, `findings`).
  `install` refuses anything not `clean` unless `force=true`.
- Prefer `non_suspicious_only: true` (the default) when listing/searching.
