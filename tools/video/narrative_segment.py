"""Narrative segment: align narration, shots and silence into candidate units.

The problem this solves
-----------------------
Splitting a long explainer into episodes is a *structural* decision, and
structure lives in the narration — not in the frames. Shot boundaries say
where the editor cut; they say nothing about where the argument turns.
So this tool refuses to pretend it can decide anything, and instead
assembles the evidence a decision needs:

- **Utterance x shot alignment.** Every spoken line is matched to the
  shots it plays over, so a line about the rear window carries the
  rear-window shots with it. This is why CLIP similarity is not needed:
  the narration already localises its own visuals.
- **Silence before each line.** A long gap is the speaker changing
  subject, or the edit passing a chapter. Cheap, mechanical, often right.
- **Semantic shift between adjacent windows.** Adjacent utterance
  embeddings are compared with a sliding window; a drop in similarity is
  where the argument moved. Weak on its own — CLIP text similarity is a
  blunt instrument for topic boundaries — so it is reported as a score,
  never applied.
- **Visual redundancy.** Shot keyframes are hashed and clustered, so
  "81 shots, 17 distinct looks" is a number rather than an opinion. Two
  episodes both leaning on the same cluster will read as repetitive.
- **Per-unit motion and duration**, so a unit that is 40 s of one static
  render is visible as such before anyone watches it.

Design notes
------------
- Boundaries are *proposed*, never applied. `min_gap_seconds` only
  decides which utterances become candidate boundaries at all; the
  grouping into episodes is the agent's call, made against the HTML view
  and recorded in a skill.
- Deliberately no ad/CTA detection. A word list for "subscribe" is a
  decision wearing a tool's clothes, and it silently misses every
  language and every euphemism. The aligned transcript is surfaced in
  full so a reader can spot promotional passages; `agents` flags them.
"""

from __future__ import annotations

import hashlib
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

_HASH_N = 8


def _avg_hash(path: Path, n: int = _HASH_N) -> Optional[str]:
    """Average-hash a frame. Cheap, deterministic, good enough to tell
    'the same render again' from 'a different angle'."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            small = img.convert("L").resize((n, n), Image.LANCZOS)
            px = list(small.getdata())
        avg = sum(px) / len(px)
        return "".join("1" if p > avg else "0" for p in px)
    except Exception:
        return None


def _hamming(a: str, b: str) -> int:
    return sum(1 for x, y in zip(a, b) if x != y)


def cluster_shots(manifest: dict, corpus_dir: Path,
                  threshold: float) -> dict[str, int]:
    """Group shots by visual similarity. Returns clip_id -> cluster index."""
    rows = [r for r in manifest.get("candidates", []) if r.get("clip_id")]
    hashes: list[tuple[str, str]] = []
    for r in rows:
        tdir = corpus_dir / (r.get("thumb_dir") or f"thumbnails/{r['clip_id']}")
        frames = sorted(tdir.glob("frame_*.jpg")) if tdir.is_dir() else []
        if not frames:
            continue
        h = _avg_hash(frames[len(frames) // 2])
        if h:
            hashes.append((r["clip_id"], h))

    clusters: list[dict[str, Any]] = []
    assign: dict[str, int] = {}
    for cid, h in hashes:
        for c in clusters:
            if _hamming(c["rep"], h) <= threshold:
                c["members"].append(cid)
                assign[cid] = c["index"]
                break
        else:
            c = {"index": len(clusters), "rep": h, "members": [cid]}
            clusters.append(c)
            assign[cid] = c["index"]
    return assign


def semantic_shifts(texts: list[str], window: int = 2) -> list[float]:
    """Cosine similarity drop between adjacent sliding windows.

    Returns one score per utterance: the similarity of the window ending
    here against the window starting here. Lower means the narration moved.
    A blunt signal — reported, not acted on.
    """
    n = len(texts)
    if n < 2 * window + 1:
        return [1.0] * n
    from lib.clip_embedder import embed_texts

    vecs = embed_texts(texts)
    out = [1.0] * n
    for i in range(window, n - window):
        a = vecs[i - window:i].mean(axis=0)
        b = vecs[i:i + window].mean(axis=0)
        na = float((a * a).sum() ** 0.5) or 1.0
        nb = float((b * b).sum() ** 0.5) or 1.0
        out[i] = round(float((a * b).sum()) / (na * nb), 4)
    return out


def render_html(title: str, meta: str, units: list[dict],
                plan_path: str) -> str:
    rows = []
    for u in units:
        shots = " ".join(
            f'<span class="s">{_esc(s["clip_id"].rsplit("_", 1)[-1])}</span>'
            for s in u["shots"]
        ) or '<span class="s none">—</span>'
        gap = u["gap_before"]
        gap_cls = "gap big" if gap >= 1.0 else "gap"
        shift = u["semantic_shift"]
        shift_cls = "shift low" if shift < 0.75 else "shift"
        rows.append(
            f'<tr class="{"cand" if u["boundary_candidate"] else ""}">'
            f'<td class="tc">{u["start"]:.1f}–{u["end"]:.1f}</td>'
            f'<td class="dur">{u["duration"]:.1f}s</td>'
            f'<td class="{gap_cls}">{gap:.2f}</td>'
            f'<td class="{shift_cls}">{shift:.3f}</td>'
            f'<td class="text">{_esc(u["text"])}</td>'
            f'<td class="shots">{shots}</td>'
            f'<td class="mo">{u["mean_motion"]:.2f}</td>'
            f'<td class="cl">{u["clusters"] or "—"}</td>'
            f'</tr>'
        )

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} · 叙事分段</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f6f7f3;color:#1b1e1a;
 font:13px/1.5 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}}
header{{position:sticky;top:0;background:#fff;border-bottom:1px solid #dfe3dc;
 padding:13px 20px;display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}}
h1{{font-size:15px;margin:0;font-weight:650}}
.meta{{color:#6b7268;font:11px/1.4 ui-monospace,Consolas,monospace}}
.lg{{margin-left:auto;color:#6b7268;font-size:11px;display:flex;gap:14px}}
.lg i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px;
 vertical-align:-1px}}
table{{width:100%;border-collapse:collapse;background:#fff}}
th{{position:sticky;top:47px;background:#fbfcfa;text-align:left;padding:8px 10px;
 font-size:11px;color:#6b7268;border-bottom:1px solid #dfe3dc;font-weight:600}}
td{{padding:8px 10px;border-bottom:1px solid #eef0ea;vertical-align:top}}
tr.cand td{{background:#fffdf5}}
tr.cand td:first-child{{box-shadow:inset 3px 0 0 #d9a441}}
.tc{{font:11px/1.4 ui-monospace,Consolas,monospace;white-space:nowrap;font-weight:600}}
.dur,.mo,.cl,.gap,.shift{{font:11px/1.4 ui-monospace,Consolas,monospace;white-space:nowrap}}
.gap.big{{color:#a03c1a;font-weight:700}}
.shift.low{{color:#a03c1a;font-weight:700}}
.text{{min-width:340px}}
.shots{{white-space:nowrap}}
.s{{display:inline-block;padding:0 5px;margin:1px;border:1px solid #cfd6c8;
 border-radius:3px;font:10px/1.6 ui-monospace,Consolas,monospace;color:#4a5344}}
.s.none{{border:0;color:#b0b6a8}}
.note{{margin:0;padding:10px 20px;background:#fdf6ec;border-top:1px solid #e8d9bd;
 font-size:12px;color:#7a5a1e}}
code{{font:11px ui-monospace,Consolas,monospace;background:#eef1ea;padding:1px 4px;
 border-radius:3px}}
</style></head><body>
<header>
  <h1>{_esc(title)} · 叙事分段候选</h1>
  <span class="meta">{_esc(meta)}</span>
  <span class="lg">
    <span><i style="background:#d9a441"></i>候选切点</span>
    <span>gap=静音间隔 · shift=前后语义相似度(越低越像转折) · cl=视觉重复组</span>
  </span>
</header>
<table>
<tr><th>时间码</th><th>时长</th><th>gap</th><th>shift</th><th>解说原文</th>
    <th>覆盖镜头</th><th>motion</th><th>cl</th></tr>
{"".join(rows)}
</table>
<p class="note">这些只是<b>信号</b>，不是结论。切集是创作决策 —— 由 agent 读这份对齐表
和 <code>{_esc(plan_path)}</code> 里的原文，判断"一集能不能说清一个完整内容"，
再写进 episode 计划。shift 是 CLIP 文本相似度，对话题边界很钝，别单独信它。</p>
</body></html>"""


def _esc(s: Any) -> str:
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


class NarrativeSegment(BaseTool):
    """Align narration to shots and surface candidate episode boundaries."""

    name = "narrative_segment"
    version = "0.1.0"
    tier = ToolTier.ANALYZE
    capability = "analysis"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["python:transformers", "python:torch", "python:numpy",
                    "python:pillow"]
    install_instructions = "pip install numpy transformers torch pillow"
    agent_skills: list[str] = []

    capabilities = [
        "narration_shot_alignment",
        "silence_gap_detection",
        "semantic_shift_scoring",
        "visual_redundancy_clustering",
    ]
    supports = {
        "word_level_timestamps": True,
        "visual_cluster_ids": True,
        "boundary_candidates_only": True,
    }
    best_for = [
        "finding where an explainer changes subject",
        "aligning a rewritten script back to source footage",
        "seeing which shots play under which spoken line",
    ]
    not_good_for = [
        "deciding the episode split (that is an editorial judgement)",
        "detecting ad breaks or sponsor reads (read the transcript)",
        "transcribing (use transcriber)",
    ]

    input_schema = {
        "type": "object",
        "required": ["transcript", "corpus_dir"],
        "properties": {
            "transcript": {
                "type": "string",
                "description": "Path to the transcript JSON written by "
                               "transcriber (has a top-level 'utterances').",
            },
            "corpus_dir": {
                "type": "string",
                "description": "Corpus directory from corpus_from_video; "
                               "supplies manifest.json and the keyframes.",
            },
            "out_dir": {"type": "string",
                        "description": "Defaults to <corpus_dir>/segments"},
            "min_gap_seconds": {
                "type": "number", "default": 0.8, "minimum": 0.0,
                "description": "Silence in front of a line at or above this "
                               "makes it a boundary candidate.",
            },
            "shift_window": {
                "type": "integer", "default": 2, "minimum": 1, "maximum": 6,
                "description": "Utterances per side when scoring semantic shift.",
            },
            "shift_threshold": {
                "type": "number", "default": 0.75, "minimum": 0.0, "maximum": 1.5,
                "description": "Similarity at or below this also marks a boundary.",
            },
            "cluster_threshold": {
                "type": "number", "default": 18.0, "minimum": 1.0, "maximum": 64.0,
                "description": "Hamming distance (of 64 bits) below which two "
                               "keyframes count as the same look.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=2048, vram_mb=0, disk_mb=20, network_required=False
    )
    side_effects = ["writes plan.json and plan.html to <out_dir>"]
    user_visible_verification = [
        "Open plan.html and confirm the highlighted rows are where you "
        "would actually start a new episode.",
        "Check that the shots listed under a line are the ones playing "
        "while it is spoken.",
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
        tpath = Path(inputs["transcript"])
        corpus_dir = Path(inputs["corpus_dir"])
        manifest_path = corpus_dir / "manifest.json"
        out_dir = Path(inputs.get("out_dir") or (corpus_dir / "segments"))
        min_gap = float(inputs.get("min_gap_seconds", 0.8))
        win = int(inputs.get("shift_window", 2))
        shift_th = float(inputs.get("shift_threshold", 0.75))
        clus_th = int(inputs.get("cluster_threshold", 18))

        if not tpath.exists():
            return ToolResult(success=False, error=f"no transcript at {tpath}",
                              data={"transcript": str(tpath)})
        if not manifest_path.exists():
            return ToolResult(
                success=False,
                error=f"no manifest.json in {corpus_dir}; build it with "
                      "corpus_from_video first",
                data={"corpus_dir": str(corpus_dir)})

        tr = json.loads(tpath.read_text(encoding="utf-8"))
        utts = tr.get("utterances") or []
        if not utts:
            segs = tr.get("segments") or []
            utts = [{"id": i + 1, "start": s["start"], "end": s["end"],
                     "text": s.get("text", "")} for i, s in enumerate(segs)]
        if not utts:
            return ToolResult(success=False, error="transcript has no utterances",
                              data={"transcript": str(tpath)})

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        shots = [r for r in manifest.get("candidates", []) if r.get("clip_id")]
        clusters = cluster_shots(manifest, corpus_dir, clus_th)

        shifts = semantic_shifts([u.get("text", "") for u in utts], win)

        units: list[dict[str, Any]] = []
        prev_end = 0.0
        for i, u in enumerate(utts):
            start = float(u["start"])
            end = float(u["end"])
            covered = [
                {"clip_id": s["clip_id"], "start": s.get("start"),
                 "end": s.get("end"), "motion": s.get("motion", 0.0),
                 "thumb_dir": s.get("thumb_dir", "")}
                for s in shots
                if float(s.get("end", 0)) > start and float(s.get("start", 0)) < end
            ]
            gap = round(max(0.0, start - prev_end), 2)
            cl = sorted({clusters[c["clip_id"]] for c in covered
                         if c["clip_id"] in clusters})
            units.append({
                "id": u.get("id", i + 1),
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(end - start, 2),
                "gap_before": gap,
                "semantic_shift": shifts[i] if i < len(shifts) else 1.0,
                "boundary_candidate": bool(
                    gap >= min_gap or shifts[i] <= shift_th
                ),
                "text": (u.get("text") or "").strip(),
                "shots": covered,
                "shot_ids": [c["clip_id"] for c in covered],
                "mean_motion": round(
                    sum(c["motion"] for c in covered) / len(covered), 2
                ) if covered else 0.0,
                "clusters": cl,
            })
            prev_end = end

        speech = round(sum(u["duration"] for u in units), 2)
        total = float(manifest.get("source", {}).get("duration_seconds", 0.0))
        n_clusters = len(set(clusters.values()))

        plan = {
            "source": manifest.get("source", {}),
            "transcript": str(tpath),
            "coverage": {
                "duration_seconds": total,
                "speech_seconds": speech,
                "speech_ratio": round(speech / total, 3) if total else 0.0,
                "utterances": len(units),
                "shots": len(shots),
                "visual_clusters": n_clusters,
                "shots_per_visual": round(len(shots) / n_clusters, 2) if n_clusters else 0.0,
            },
            "params": {
                "min_gap_seconds": min_gap,
                "shift_window": win,
                "shift_threshold": shift_th,
                "cluster_threshold": clus_th,
            },
            "units": units,
        }

        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path = out_dir / "plan.json"
        plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False),
                             encoding="utf-8")
        html_path = out_dir / "plan.html"
        html_path.write_text(render_html(
            str(manifest.get("source", {}).get("source_id", "source")),
            f"{len(units)} 句解说 · {len(shots)} 镜 · {n_clusters} 种视觉 · "
            f"解说占 {plan['coverage']['speech_ratio']:.0%}",
            units, str(plan_path),
        ), encoding="utf-8")

        cands = [u for u in units if u["boundary_candidate"]]
        return ToolResult(
            success=True,
            data={
                "plan_json": str(plan_path),
                "plan_html": str(html_path),
                "units": len(units),
                "boundary_candidates": len(cands),
                "by_silence": sum(1 for u in units
                                  if u["gap_before"] >= min_gap),
                "by_semantic_shift": sum(1 for u in units
                                         if u["semantic_shift"] <= shift_th),
                "shots": len(shots),
                "visual_clusters": n_clusters,
                "shots_per_visual": plan["coverage"]["shots_per_visual"],
                "speech_ratio": plan["coverage"]["speech_ratio"],
                "next_step": "read plan.html, decide the episode split "
                             "(one complete thought per episode), then align "
                             "episodes to these units",
                "elapsed_seconds": round(time.time() - started, 1),
            },
        )
