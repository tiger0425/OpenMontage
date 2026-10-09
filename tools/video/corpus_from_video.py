"""Corpus from video: index one local source video as a shot-level clip corpus.

This is the ingestion gap that sits between `corpus_builder` and
`clip_search`. `corpus_builder` only fans out to stock providers
(Pexels, archive.org, ...) — it cannot take a video you already
downloaded and turn it into retrievable candidates. Every re-creation
pipeline (`erchuang`, `wrc`, `auto-dub`) starts from exactly such a
local file, so without this tool `clip_search` can only ever rank stock
footage, never the user's own source.

What it does
------------
1. **Shot-level segmentation** via ffmpeg scene detection. One candidate
   clip = one shot, so a candidate never straddles a cut and CLIP is
   never asked to average two unrelated scenes into one vector.
2. **Motion measurement** per shot via a 5 Hz frame-difference curve,
   taking the *median* with both ends trimmed. The median is what makes
   the number meaningful: a shot's motion is read from its interior, so
   the spike at each cut point cannot inflate it.
3. **Thumbnail extraction** (3 frames per shot by default) and CLIP
   embedding, frame-pooled into one 512-d vector per shot.
4. **A manifest** recording exact `start` / `end` for every candidate, so
   downstream edit steps can cut from the original by timecode instead of
   re-encoding materialised copies. Clip files are optional.

Design notes
------------
- The segmentation is deliberately *not* a semantic merge. Cuts closer
  than `min_shot_seconds` are dropped so a dissolve cannot shatter into
  three candidates; everything else is taken as detected. A semantic
  merge is a judgement call, and judgements do not belong in a
  deterministic tool.
- `shot_type` is left empty on purpose. It is a `ClipRecord` field, but
  filling it means looking at the shot, which is the annotator's job —
  not the indexer's. Leave it empty rather than guess.
- Candidates are *candidates*. Nothing here decides what goes in the
  edit; it only makes the search space finite and rankable.

Cost: zero. Everything runs locally (ffmpeg + CLIP), so this is
`ToolRuntime.LOCAL` with no network and no spend.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
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

# ----------------------------------------------------------------------
# ffmpeg primitives
# ----------------------------------------------------------------------


def _run(args: list[str], timeout: int = 3600) -> str:
    """Run a command, return stdout as text. Raises on non-zero exit."""
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-4:]
        raise RuntimeError(
            f"{args[0]} failed (rc={proc.returncode}): " + " | ".join(tail)
        )
    return proc.stdout


def probe(video: Path) -> dict[str, Any]:
    """ffprobe the container: duration, fps, resolution."""
    out = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-show_entries", "format=duration",
        "-of", "json", str(video),
    ])
    data = json.loads(out)
    if not data.get("streams"):
        raise RuntimeError(f"no video stream in {video}")
    s = data["streams"][0]
    num, _, den = (s.get("r_frame_rate") or "0/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return {
        "duration_seconds": round(float(data.get("format", {}).get("duration", 0.0)), 2),
        "width": int(s.get("width", 0)),
        "height": int(s.get("height", 0)),
        "fps": round(fps, 3),
        "codec": s.get("codec_name", ""),
    }


def detect_cuts(video: Path, threshold: float) -> list[float]:
    """Scene-change timestamps, via ffmpeg's `scene` score.

    `select='gt(scene,T)'` emits a frame whenever the frame-to-frame
    change score exceeds T; `metadata=print` surfaces the pts. Working
    on a 320px-wide copy is enough to score a cut and keeps the pass
    cheap on long sources.
    """
    out = _run([
        "ffmpeg", "-v", "error", "-i", str(video), "-an",
        "-vf", f"scale=320:-2,select='gt(scene,{threshold})',metadata=print:file=-",
        "-f", "null", "-",
    ])
    cuts: list[float] = []
    for line in out.splitlines():
        marker = "pts_time:"
        i = line.find(marker)
        if i == -1:
            continue
        try:
            cuts.append(round(float(line[i + len(marker):].strip()), 2))
        except ValueError:
            continue
    return cuts


def motion_track(video: Path, hz: float) -> tuple[float, list[float]]:
    """Per-frame-difference curve at `hz`, one mean luma value per sample.

    `tblend=all_mode=difference` turns each frame pair into its
    absolute difference, and `signalstats` reports the mean of that.
    Downscaling to 64x36 first keeps the cost flat regardless of source
    resolution.
    """
    out = _run([
        "ffmpeg", "-v", "error", "-i", str(video), "-an",
        "-vf",
        f"fps={hz},scale=64:36,tblend=all_mode=difference,"
        "signalstats,metadata=print:file=-:key=lavfi.signalstats.YAVG",
        "-f", "null", "-",
    ])
    values: list[float] = []
    for line in out.splitlines():
        marker = "signalstats.YAVG="
        i = line.find(marker)
        if i == -1:
            continue
        try:
            values.append(round(float(line[i + len(marker):].strip()), 1))
        except ValueError:
            continue
    return hz, values


def median_motion(
    hz: float, values: list[float], start: float, end: float
) -> float:
    """Median motion inside a shot, with both ends trimmed.

    Trimming matters more than it looks: a cut produces a large frame
    difference, so an untrimmed mean or even a naive median over the
    whole shot can be dominated by the transition rather than by what
    the shot actually contains. The edge is 15% of the span, clamped to
    [0.1s, 0.4s] so short shots keep most of their samples.
    """
    span = end - start
    if not (span > 0) or not values:
        return 0.0
    edge = min(0.4, max(0.1, span * 0.15))
    lo = max(0, int((start + edge) * hz))
    hi = min(len(values) - 1, int((end - edge) * hz))
    slice_ = [v for v in values[lo:hi + 1] if v == v]
    if not slice_:
        return 0.0
    slice_.sort()
    mid = len(slice_) >> 1
    if len(slice_) % 2:
        return round(slice_[mid], 2)
    return round((slice_[mid - 1] + slice_[mid]) / 2, 2)


def to_shots(
    cuts: list[float], total: float, min_shot_seconds: float
) -> tuple[list[float], list[dict[str, Any]]]:
    """Turn raw cut timestamps into shot spans.

    The only filter applied is a minimum span: a cut landing within
    `min_shot_seconds` of the previous boundary is discarded, so a
    dissolve or a flash cannot shatter into near-zero-length candidates.
    """
    raw = sorted({t for t in cuts if 0 < t < total})
    bounds = [0.0]
    for t in raw:
        if t - bounds[-1] >= min_shot_seconds:
            bounds.append(t)
    if total - bounds[-1] < min_shot_seconds and len(bounds) > 1:
        bounds.pop()
    bounds.append(total)

    shots = []
    for i in range(len(bounds) - 1):
        start = round(bounds[i], 2)
        end = round(bounds[i + 1], 2)
        shots.append({
            "index": i + 1,
            "start": start,
            "end": end,
            "seconds": round(end - start, 2),
        })
    return raw, shots


def extract_thumbs(
    video: Path, start: float, end: float, out_dir: Path, count: int
) -> list[Path]:
    """Grab `count` frames spread across the shot's interior.

    Sampled between 15% and 85% of the span so no frame lands on the
    transition itself, which would label the shot with its neighbour.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    span = end - start
    lo, hi = (0.15, 0.85) if count > 1 else (0.5, 0.5)
    made: list[Path] = []
    for k in range(count):
        frac = lo + (hi - lo) * (k / max(1, count - 1)) if count > 1 else lo
        at = start + span * frac
        dst = out_dir / f"frame_{k + 1:02d}.jpg"
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", str(video),
             "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "3", str(dst)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
            made.append(dst)
    return made


def dominant_colors(thumb: Path, k: int = 3) -> list[list[int]]:
    """A few dominant RGB triples, coarse-quantised for speed."""
    try:
        from PIL import Image
    except ImportError:
        return []
    try:
        with Image.open(thumb) as img:
            small = img.convert("RGB").resize((32, 32))
            quant = small.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
            palette: list[int] = list(quant.getpalette() or [])
            raw_colors: list = list(quant.getcolors() or [])
            raw_colors.sort(key=lambda c: c[0], reverse=True)
            out: list[list[int]] = []
            for entry in raw_colors[:k]:
                base = int(entry[1]) * 3
                if base + 2 < len(palette):
                    out.append([palette[base], palette[base + 1], palette[base + 2]])
            return out
    except Exception:
        return []


_SLUG = re.compile(r"[^A-Za-z0-9_.-]+")


def slugify(text: str, fallback: str = "src") -> str:
    out = _SLUG.sub("-", str(text)).strip("-")
    return out[:48] or fallback


# ----------------------------------------------------------------------
# Tool
# ----------------------------------------------------------------------


class CorpusFromVideo(BaseTool):
    """Index one local source video as a shot-level clip corpus."""

    name = "corpus_from_video"
    version = "0.1.0"
    tier = ToolTier.SOURCE
    capability = "corpus_population"
    provider = "openmontage"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = [
        "bin:ffmpeg",
        "bin:ffprobe",
        "python:numpy",
        "python:transformers",
        "python:torch",
        "python:pillow",
    ]
    install_instructions = (
        "ffmpeg + ffprobe on PATH; pip install numpy transformers torch pillow.\n"
        "CLIP weights are loaded via lib.clip_embedder. Set "
        "OPENMONTAGE_CLIP_MODEL to a local directory if the default "
        "openai/clip-vit-base-patch32 checkpoint is unreachable."
    )
    agent_skills: list[str] = []

    capabilities = [
        "shot_level_segmentation",
        "clip_indexing",
        "clip_embedding",
        "motion_scoring",
        "timecode_manifest",
    ]
    supports = {
        "local_source_video": True,
        "shot_aligned_candidates": True,
        "timecode_manifest": True,
        "optional_clip_materialisation": True,
    }
    best_for = [
        "making a downloaded source video searchable by scene description",
        "producing a ranked candidate list before a re-creation edit",
        "turning a long source into a finite, rankable candidate set",
    ]
    not_good_for = [
        "stock footage search (use corpus_builder)",
        "semantic ranking itself (use clip_search)",
        "cutting or composing video (use video_compose)",
    ]

    input_schema = {
        "type": "object",
        "required": ["video", "corpus_dir"],
        "properties": {
            "video": {
                "type": "string",
                "description": "Path to the local source video to index.",
            },
            "corpus_dir": {
                "type": "string",
                "description": "Corpus directory to populate, e.g. "
                               "projects/foo/corpus",
            },
            "source_id": {
                "type": "string",
                "description": "Stable id for this source (e.g. the "
                               "YouTube id). Used in clip ids. Defaults "
                               "to the video filename stem.",
            },
            "scene_threshold": {
                "type": "number",
                "default": 0.15,
                "minimum": 0.02,
                "maximum": 0.9,
                "description": "ffmpeg scene-score cut threshold. Lower "
                               "catches more cuts. 0.15 suits technical "
                               "3D/CG content where cuts are low "
                               "contrast; 0.3+ suits live action.",
            },
            "min_shot_seconds": {
                "type": "number",
                "default": 0.3,
                "minimum": 0.05,
                "description": "Cuts closer together than this are "
                               "merged away, so a dissolve yields one "
                               "candidate rather than several.",
            },
            "thumbs_per_shot": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "maximum": 9,
                "description": "Frames sampled per shot and pooled into "
                               "the shot's CLIP vector.",
            },
            "motion_hz": {
                "type": "number",
                "default": 5.0,
                "description": "Sampling rate of the motion curve.",
            },
            "materialize_clips": {
                "type": "boolean",
                "default": False,
                "description": "Also write one cut file per shot into "
                               "<corpus_dir>/clips/. Off by default: most "
                               "edit steps can cut from the original by "
                               "timecode, so re-encoding is wasted work.",
            },
            "min_seconds": {
                "type": "number",
                "default": 0.0,
                "description": "Skip candidates shorter than this.",
            },
            "max_seconds": {
                "type": "number",
                "default": 0.0,
                "description": "Skip candidates longer than this. 0 = no cap.",
            },
            "source_tags": {
                "type": "string",
                "description": "Free text describing the source as a "
                               "whole. Embedded into the tag channel, so "
                               "every candidate inherits it.",
            },
            "dry_run_limit": {
                "type": "integer",
                "default": 0,
                "description": "Only index the first N candidates. Use "
                               "to sanity-check segmentation cheaply.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=2048, vram_mb=0, disk_mb=500, network_required=False
    )
    side_effects = [
        "writes thumbnails to <corpus_dir>/thumbnails/<clip_id>/",
        "writes <corpus_dir>/manifest.json with per-shot timecodes",
        "writes corpus index/embedding files via Corpus.save()",
    ]
    user_visible_verification = [
        "Open <corpus_dir>/manifest.json and confirm the shot count and "
        "timecodes match what you see in the source.",
        "Look at a few <corpus_dir>/thumbnails/<clip_id>/frame_02.jpg to "
        "confirm the candidate boundaries land on real cuts.",
    ]

    # ------------------------------------------------------------------

    def get_status(self) -> ToolStatus:
        if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            return ToolStatus.UNAVAILABLE
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

        video = Path(inputs["video"])
        corpus_dir = Path(inputs["corpus_dir"])
        threshold = float(inputs.get("scene_threshold", 0.15))
        min_shot = float(inputs.get("min_shot_seconds", 0.3))
        thumbs_n = int(inputs.get("thumbs_per_shot", 3))
        motion_hz = float(inputs.get("motion_hz", 5.0))
        materialize = bool(inputs.get("materialize_clips", False))
        min_s = float(inputs.get("min_seconds", 0.0))
        max_s = float(inputs.get("max_seconds", 0.0))
        source_tags = str(inputs.get("source_tags", "") or "")
        limit = int(inputs.get("dry_run_limit", 0) or 0)

        if not video.exists():
            return ToolResult(
                success=False, error=f"video not found: {video}",
                data={"video": str(video)},
            )

        source_id = slugify(
            str(inputs.get("source_id") or video.stem), fallback="src"
        )

        # --- 1. segment -------------------------------------------------
        meta = probe(video)
        total = float(meta["duration_seconds"])
        if total <= 0:
            return ToolResult(
                success=False, error=f"could not read duration of {video}",
                data={"video": str(video)},
            )

        raw_cuts = detect_cuts(video, threshold)
        cuts, shots = to_shots(raw_cuts, total, min_shot)

        kept = [
            s for s in shots
            if s["seconds"] >= min_s and (max_s <= 0 or s["seconds"] <= max_s)
        ]
        if limit > 0:
            kept = kept[:limit]

        if not kept:
            return ToolResult(
                success=False,
                error="segmentation produced no candidates; lower "
                      "scene_threshold or min_shot_seconds",
                data={
                    "raw_cuts": len(cuts),
                    "shots_detected": len(shots),
                    "duration_seconds": total,
                },
            )

        # --- 2. motion --------------------------------------------------
        hz, curve = motion_track(video, motion_hz)
        for s in kept:
            s["motion"] = median_motion(hz, curve, s["start"], s["end"])

        # --- 3. thumbnails + CLIP ---------------------------------------
        from lib.clip_embedder import embed_images, embed_texts, pool_frames
        from lib.corpus import Corpus, ClipRecord

        corpus_dir.mkdir(parents=True, exist_ok=True)
        corp = Corpus(corpus_dir)
        corp.load()

        source_rel = f"source/{video.name}"
        src_dst = corpus_dir / "source" / video.name
        src_dst.parent.mkdir(parents=True, exist_ok=True)
        if not src_dst.exists():
            try:
                shutil.copy2(video, src_dst)
            except OSError:
                pass  # provenance only; never fail the index on a copy

        tag_vec = embed_texts([source_tags])[0] if source_tags.strip() else None

        rows: list[dict[str, Any]] = []
        added = 0
        thumbs_failed = 0
        pending: list[tuple[str, dict, list[Path], list[list[int]]]] = []
        BATCH = 32

        def flush(pending: list) -> None:
            """Embed one batch of accumulated shots and append their rows."""
            nonlocal added
            if not pending:
                return
            flat = [p for _, _, thumbs, _ in pending for p in thumbs]
            vecs = embed_images(flat)
            cursor = 0
            for clip_id, shot, thumbs, colors in pending:
                n = len(thumbs)
                vec = pool_frames(vecs[cursor: cursor + n])
                cursor += n
                record = ClipRecord(
                    clip_id=clip_id,
                    source=source_id,
                    source_id=f"{source_id}#{shot['index']:03d}",
                    source_url="",
                    local_path=shot.get("local_path", source_rel),
                    kind="video",
                    thumb_dir=shot["thumb_dir"],
                    query=source_tags,
                    duration=shot["seconds"],
                    width=meta["width"],
                    height=meta["height"],
                    motion_score=float(shot.get("motion", 0.0)),
                    dominant_colors=colors,
                    source_tags=source_tags,
                )
                corp.add(record, vec, tag_vec if tag_vec is not None else vec)
                added += 1

        for shot in kept:
            clip_id = f"{source_id}_{shot['index']:03d}"
            if corp.has(clip_id):
                rows.append({"clip_id": clip_id, "index": shot["index"],
                             "start": shot["start"], "end": shot["end"],
                             "seconds": shot["seconds"],
                             "indexed": False, "reason": "already in corpus"})
                continue

            tdir_rel = f"thumbnails/{clip_id}"
            tdir = corpus_dir / "thumbnails" / clip_id
            thumbs = extract_thumbs(
                video, shot["start"], shot["end"], tdir, thumbs_n
            )
            if not thumbs:
                thumbs_failed += 1
                continue

            shot["local_path"] = source_rel
            if materialize:
                clips_rel = f"clips/{clip_id}.mp4"
                clips_dst = corpus_dir / "clips" / f"{clip_id}.mp4"
                clips_dst.parent.mkdir(parents=True, exist_ok=True)
                proc = subprocess.run(
                    ["ffmpeg", "-v", "error", "-y",
                     "-ss", f"{shot['start']:.2f}", "-t",
                     f"{shot['seconds']:.2f}", "-i", str(video),
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                     "-c:a", "aac", "-b:a", "128k", str(clips_dst)],
                    capture_output=True, text=True, timeout=300,
                )
                if proc.returncode == 0 and clips_dst.exists():
                    shot["local_path"] = clips_rel

            shot["clip_id"] = clip_id
            shot["thumb_dir"] = tdir_rel
            shot["thumbs"] = [f"{tdir_rel}/{p.name}" for p in thumbs]
            shot["indexed"] = True
            rows.append(shot)
            pending.append((clip_id, shot, thumbs, dominant_colors(thumbs[len(thumbs) // 2])))

            if len(pending) >= BATCH:
                flush(pending)
                pending = []

        flush(pending)
        corp.save()

        # --- 4. manifest -----------------------------------------------
        manifest = {
            "source": {
                "source_id": source_id,
                "video": str(video),
                "local_path": source_rel,
                **meta,
            },
            "segmentation": {
                "scene_threshold": threshold,
                "min_shot_seconds": min_shot,
                "raw_cuts": len(cuts),
                "shots_detected": len(shots),
                "candidates_kept": len(kept),
                "candidates_indexed": added,
            },
            "motion": {"hz": motion_hz, "samples": len(curve)},
            "candidates": rows,
        }
        manifest_path = corpus_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return ToolResult(
            success=True,
            data={
                "corpus_dir": str(corpus_dir),
                "source_id": source_id,
                "duration_seconds": total,
                "raw_cuts": len(cuts),
                "shots_detected": len(shots),
                "candidates_kept": len(kept),
                "candidates_added": added,
                "already_present": len(kept) - added,
                "thumbs_failed": thumbs_failed,
                "manifest_path": str(manifest_path),
                "thumbnails_dir": str(corpus_dir / "thumbnails"),
                "materialized_clips": materialize,
                "next_tool": "clip_search(operation='rank_for_slot', "
                             "corpus_dir=..., query_text=...)",
                "elapsed_seconds": round(time.time() - started, 1),
            },
        )
