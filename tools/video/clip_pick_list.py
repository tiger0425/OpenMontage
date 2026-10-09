"""Clip pick list: turn ranked corpus candidates into a reviewable page.

The retrieval tools answer "which candidates match this slot?" and stop
there. That answer is a list of ids, which is useless to a human: nobody
decides an edit from `wABhhQMZUrI_043` — they decide it by looking at the
frame. This tool closes that gap by rendering the ranking as a single
portable HTML page, with the thumbnails inlined, so the decision is made
by eye and the result leaves as a paste-ready `--cuts` string.

Why a page and not a JSON dump
------------------------------
Ranking is a *suggestion*, never a decision. Measured against a manual
annotation of 81 shots, CLIP's top-10 recall was only ~50%, and it was
0% for data-visualisation shots. A tool that emitted a final cut list
would therefore be confidently wrong exactly where it matters most. A
page that shows the top N frames side by side, ranked, lets the human
catch what the ranking missed. The tool's job is to make the pool finite
and ordered, not to be right.

Design notes
------------
- Thumbnails are inlined as base64 so the page is a single portable file
  you can hand to someone else. Downscaled to 320px to keep it small.
- Timecodes come from `manifest.json` written by `corpus_from_video`, so
  the exported `--cuts` string needs no lookup against the corpus index.
- Selection is a checkbox, not a ranking. Rank order is advice; the
  export follows the order the human ticked, which is the order they
  want in the edit.
- One row per candidate, with motion and duration shown next to the
  frame: a dead-still candidate and a 0.3 s flash look the same in a
  thumbnail grid, and they should not.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Optional

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

_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f6f7f3;color:#1b1e1a;
  font:14px/1.55 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:#fff;border-bottom:1px solid #dfe3dc;
  padding:14px 22px;display:flex;gap:18px;align-items:baseline;flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:650}
.meta{color:#6b7268;font-size:12px;font-family:ui-monospace,Consolas,monospace}
.out{margin-left:auto;display:flex;gap:10px;align-items:center}
button{font:inherit;padding:7px 15px;border:1px solid #1b1e1a;border-radius:5px;
  background:#1b1e1a;color:#fff;cursor:pointer}
button.ghost{background:#fff;color:#1b1e1a}
button:hover{opacity:.86}
#cuts{font:12px/1.4 ui-monospace,Consolas,monospace;background:#fff;
  border:1px solid #dfe3dc;border-radius:5px;padding:7px 11px;min-width:340px}
.slot{margin:0 0 34px;background:#fff;border:1px solid #dfe3dc;border-radius:8px;overflow:hidden}
.slot>header{position:static;background:#fbfcfa;border-bottom:1px solid #dfe3dc;padding:11px 18px}
.slot h2{font-size:14px;margin:0 0 3px;font-weight:620}
.q{color:#6b7268;font-size:12px;font-style:italic}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:12px;padding:16px 18px}
.card{border:1.5px solid #dfe3dc;border-radius:6px;overflow:hidden;cursor:pointer;background:#fff;
  transition:border-color .1s}
.card:hover{border-color:#8a9a80}
.card.on{border-color:#1b1e1a;box-shadow:0 0 0 2px #1b1e1a inset}
.card img{width:100%;display:block;aspect-ratio:16/9;object-fit:cover;background:#000}
.info{padding:7px 9px;font:11px/1.5 ui-monospace,Consolas,monospace;color:#3a4238}
.tc{font-weight:650;color:#1b1e1a}
.rank{float:right;color:#8a9a80}
.badge{display:inline-block;padding:0 5px;border-radius:3px;font-size:10px;background:#eef1ea}
.card.on .badge{background:#1b1e1a;color:#fff}
.warn{color:#a03c1a}
.picked{margin:0;padding:11px 18px;border-top:1px solid #dfe3dc;background:#fbfcfa;
  font:12px/1.7 ui-monospace,Consolas,monospace;color:#3a4238;min-height:38px}
.picked b{color:#1b1e1a}
.note{margin:0;padding:10px 18px;background:#fdf6ec;border-top:1px solid #e8d9bd;
  font-size:12px;color:#7a5a1e}
"""

_JS = """
const OUT = document.getElementById('cuts');
const N = document.querySelectorAll('.note').length;
function sel(slot){
  return [...slot.querySelectorAll('.card.on')].map(c=>c.dataset);
}
function sync(){
  const rows=[];
  document.querySelectorAll('.slot').forEach(s=>{
    const name=s.dataset.slot;
    sel(s).forEach(d=>rows.push(d.tc));
  });
  OUT.value = rows.length ? rows.join(';') : '';
  document.getElementById('cnt').textContent = rows.length + ' 段已选 / 共 ' + N + ' 段';
}
document.addEventListener('click',e=>{
  const c=e.target.closest('.card'); if(!c) return;
  c.classList.toggle('on'); sync();
});
document.getElementById('copy').onclick=()=>{
  OUT.select(); navigator.clipboard.writeText(OUT.value).then(()=>{
    const b=document.getElementById('copy'), t=b.textContent;
    b.textContent='已复制'; setTimeout(()=>b.textContent=t,1100);
  });
};
document.getElementById('clear').onclick=()=>{
  document.querySelectorAll('.card.on').forEach(c=>c.classList.remove('on')); sync();
};
sync();
"""


def _b64_jpeg(path: Path, width: int = 320) -> str:
    """Downscale a thumbnail and inline it as base64 JPEG."""
    try:
        from PIL import Image
    except ImportError:
        return ""
    try:
        with Image.open(path) as img:
            out = img.convert("RGB")
            if out.width > width:
                out = out.resize(
                    (width, max(1, round(out.height * width / out.width))),
                    Image.LANCZOS,
                )
            import io
            buf = io.BytesIO()
            out.save(buf, format="JPEG", quality=72, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def _esc(s: Any) -> str:
    return (
        str(s if s is not None else "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class ClipPickList(BaseTool):
    """Render a ranked candidate list as a reviewable HTML pick page."""

    name = "clip_pick_list"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "clip_retrieval"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["python:transformers", "python:torch", "python:numpy",
                    "python:pillow"]
    install_instructions = (
        "pip install numpy transformers torch pillow. Needs a corpus built by "
        "corpus_from_video (local source video) or corpus_builder (stock)."
    )
    agent_skills: list[str] = []

    capabilities = [
        "ranked_candidate_render",
        "inline_thumbnail_packing",
        "cut_list_export",
    ]
    supports = {
        "single_file_output": True,
        "timecode_export": True,
        "multi_slot": True,
    }
    best_for = [
        "reviewing ranked candidates by eye before committing to a cut list",
        "producing a paste-ready --cuts string for an edit step",
        "handing a reviewer a self-contained page with the source frames inlined",
    ]
    not_good_for = [
        "deciding the edit automatically (ranking recall is ~50% at 10)",
        "populating a corpus (use corpus_from_video / corpus_builder)",
        "ranking without rendering (use clip_search)",
    ]

    input_schema = {
        "type": "object",
        "required": ["corpus_dir", "queries"],
        "properties": {
            "corpus_dir": {
                "type": "string",
                "description": "Corpus directory containing manifest.json.",
            },
            "queries": {
                "type": "array",
                "minItems": 1,
                "description": "One entry per scene slot to source.",
                "items": {
                    "type": "object",
                    "required": ["query_text"],
                    "properties": {
                        "slot_id": {
                            "type": "string",
                            "description": "Short label for this slot, "
                                           "e.g. 'opener' or 'slot_03'.",
                        },
                        "query_text": {
                            "type": "string",
                            "description": "Scene description in English. "
                                           "CLIP is English-trained; Chinese "
                                           "queries rank poorly.",
                        },
                    },
                },
            },
            "k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 30,
                  "description": "Candidates shown per slot."},
            "tag_weight": {"type": "number", "default": 0.0, "minimum": 0.0,
                           "maximum": 1.0,
                           "description": "Blend of visual vs source-tag "
                                          "channels. 0 = pure visual."},
            "motion_min": {"type": "number",
                           "description": "Reject candidates below this "
                                          "motion score."},
            "exclude_ids": {
                "type": "array", "items": {"type": "string"},
                "description": "clip_ids to omit (already used).",
            },
            "out_html": {
                "type": "string",
                "description": "Output path. Defaults to "
                               "<corpus_dir>/pick.html.",
            },
            "thumb_width": {"type": "integer", "default": 320, "minimum": 160,
                            "maximum": 640},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=2048, vram_mb=0, disk_mb=20, network_required=False
    )
    side_effects = ["writes the pick page to <corpus_dir>/pick.html"]
    user_visible_verification = [
        "Open the page and confirm the frames under each slot match its "
        "query description.",
        "After ticking candidates, confirm the exported --cuts timecodes "
        "match the shots you ticked.",
    ]

    # ------------------------------------------------------------------

    def get_status(self) -> ToolStatus:
        try:
            import numpy  # noqa: F401
            import torch  # noqa: F401
            import transformers  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    # ------------------------------------------------------------------

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        corpus_dir = Path(inputs["corpus_dir"])
        manifest_path = corpus_dir / "manifest.json"
        if not manifest_path.exists():
            return ToolResult(
                success=False,
                error=f"no manifest.json in {corpus_dir}; build the corpus "
                      "with corpus_from_video first",
                data={"corpus_dir": str(corpus_dir)},
            )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        timecodes: dict[str, dict[str, Any]] = {}
        for row in manifest.get("candidates", []):
            cid = row.get("clip_id")
            if cid:
                timecodes[cid] = row

        src = manifest.get("source", {})
        queries = inputs["queries"]
        k = int(inputs.get("k", 8))
        tag_weight = float(inputs.get("tag_weight", 0.0))
        motion_min = inputs.get("motion_min")
        exclude = set(inputs.get("exclude_ids", []) or [])
        thumb_w = int(inputs.get("thumb_width", 320))
        out_html = Path(inputs.get("out_html") or (corpus_dir / "pick.html"))

        from lib.corpus import Corpus

        corp = Corpus(corpus_dir)
        corp.load()
        if not len(corp):
            return ToolResult(
                success=False, error=f"corpus at {corpus_dir} is empty",
                data={"corpus_dir": str(corpus_dir)},
            )

        # One CLIP load, then embed every slot query in a single batch.
        from lib.clip_embedder import embed_texts

        texts = [str(q["query_text"]) for q in queries]
        qvecs = embed_texts(texts)

        blocks: list[str] = []
        total_shown = 0
        for i, q in enumerate(queries):
            params: dict[str, Any] = {
                "operation": "rank_for_slot",
                "corpus_dir": str(corpus_dir),
                "query_text": str(q["query_text"]),
                "k": k,
                "tag_weight": tag_weight,
            }
            if motion_min is not None:
                params["motion_min"] = float(motion_min)
            if exclude:
                params["exclude_ids"] = list(exclude)

            from tools.video.clip_search import ClipSearch
            r = ClipSearch().execute(params)
            if not r.success:
                blocks.append(
                    f'<section class="slot"><header><h2>{_esc(q.get("slot_id"))}'
                    f'</h2><div class="q">{_esc(q["query_text"])}</div></header>'
                    f'<p class="note">排序失败：{_esc(r.error)}</p></section>'
                )
                continue

            cards: list[str] = []
            for rank_i, hit in enumerate(r.data.get("results", []), 1):
                rec = hit["record"]
                cid = rec["clip_id"]
                tc = timecodes.get(cid, {})
                start = tc.get("start")
                end = tc.get("end")
                if start is None or end is None:
                    continue
                tdir = corpus_dir / (rec.get("thumb_dir") or f"thumbnails/{cid}")
                mid = _pick_mid(tdir)
                b64 = _b64_jpeg(mid, thumb_w) if mid else ""
                img = (
                    f'<img src="data:image/jpeg;base64,{b64}" alt="{_esc(cid)}">'
                    if b64 else
                    '<img alt="no thumbnail">'
                )
                warn = ""
                if float(rec.get("motion_score", 0)) < 1.0:
                    warn = ' <span class="warn">近静</span>'
                cards.append(
                    f'<div class="card" data-tc="{start}-{end}" '
                    f'data-id="{_esc(cid)}">{img}'
                    f'<div class="info"><span class="rank">#{rank_i}</span>'
                    f'<span class="tc">{start:.2f}–{end:.2f}s</span>'
                    f'<br>{float(rec.get("duration", 0)):.2f}s · '
                    f'motion {float(rec.get("motion_score", 0)):.1f}{warn}'
                    f'<br><span class="badge">{_esc(cid.rsplit("_", 1)[-1])}</span>'
                    f'</div></div>'
                )
                total_shown += 1

            blocks.append(
                f'<section class="slot" data-slot="{_esc(q.get("slot_id", i))}">'
                f'<header><h2>{_esc(q.get("slot_id", f"slot_{i}"))}</h2>'
                f'<div class="q">{_esc(q["query_text"])}</div></header>'
                f'<div class="grid">{"".join(cards) or "<p>无候选</p>"}</div>'
                f'<p class="picked"></p>'
                f'<p class="note">排序仅供参考，请看图确认。CLIP 对数据图/字卡类'
                f'图形召回极低，源片里的图表字幕卡基本不会被自动选中。</p>'
                f'</section>'
            )

        html = _render_page(
            title=str(src.get("source_id", "corpus")),
            meta=(
                f'{src.get("width", "?")}×{src.get("height", "?")} · '
                f'{src.get("fps", "?")} fps · {src.get("duration_seconds", "?")}s · '
                f'{len(corp)} 候选'
            ),
            blocks=blocks,
        )
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(html, encoding="utf-8")

        return ToolResult(
            success=True,
            data={
                "out_html": str(out_html),
                "size_kb": round(out_html.stat().st_size / 1024, 1),
                "slots": len(queries),
                "candidates_shown": total_shown,
                "k_per_slot": k,
                "tag_weight": tag_weight,
                "motion_min": motion_min,
                "excluded": len(exclude),
                "next_step": "tick candidates in the page, then pass the "
                             "exported --cuts string to your edit step",
                "elapsed_seconds": round(time.time() - started, 1),
            },
        )


def _pick_mid(tdir: Path) -> Optional[Path]:
    """The middle thumbnail of a candidate, if any exist."""
    if not tdir.is_dir():
        return None
    frames = sorted(tdir.glob("frame_*.jpg"))
    if not frames:
        return None
    return frames[len(frames) // 2]


def _render_page(title: str, meta: str, blocks: list[str]) -> str:
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} · 选片段</title>
<style>{_CSS}</style></head><body>
<header>
  <h1>{_esc(title)} · 选片段</h1>
  <span class="meta">{_esc(meta)}</span>
  <div class="out">
    <span class="meta" id="cnt"></span>
    <input id="cuts" readonly>
    <button id="copy">复制 --cuts</button>
    <button id="clear" class="ghost">清空</button>
  </div>
</header>
{"".join(blocks)}
<script>{_JS}</script>
</body></html>"""
