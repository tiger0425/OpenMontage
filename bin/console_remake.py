#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""console-remake · 深色控制台设计复刻管线 CLI（bin/console_remake.py）

规范来源：
  apps/console-remake/specs/design-system.md     （世界宪法：零件/色彩/动效/禁用）
  apps/console-remake/template/console.css/js    （零件库）
  apps/console-remake/template/generate_composition.py （装配器）

流程：
  new          创建项目 + 抓取源片（下载/转录/抽帧）
  script       校验创作契约 episode.json + 红线扫描 → 停在【脚本闸门】
  approve-script  人审放行（闸门）
  synth        IndexTTS 2.5 逐句克隆配音 + 实测时长（重·GPU）
  compose      装配 HyperFrames index.html + 烘焙音频（轻）
  render       渲染 1080P（重·CPU/GPU），可选 4K HEVC 压制
  package      成品包（成片/封面/发布文案模板）
  run          new + script（轻，直达闸门）
  run-heavy    synth + compose + render + package（重，派 Compute Worker）
  status       查看所有 console 项目状态

用法：
  python bin/console_remake.py new agent-harness --ref-url "https://www.youtube.com/watch?v=..."
  python bin/console_remake.py script console-agent-harness
  python bin/console_remake.py approve-script console-agent-harness
  python bin/console_remake.py synth console-agent-harness --json          # 重
  python bin/console_remake.py compose console-agent-harness
  python bin/console_remake.py render console-agent-harness --json         # 重
  python bin/console_remake.py package console-agent-harness
  python bin/console_remake.py run-heavy console-agent-harness --scenes s01,s02,s03 --json
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    _reconf = getattr(_stream, "reconfigure", None)
    if callable(_reconf):
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

OMO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OMO_ROOT))

PROJECTS_ROOT = OMO_ROOT / "projects"
TEMPLATE_DIR = OMO_ROOT / "apps" / "console-remake" / "template"
GEN_COMPOSE = TEMPLATE_DIR / "generate_composition.py"
REDLINE_SCAN = OMO_ROOT / "apps" / "ref-remake" / "scripts" / "redline_scan.py"
GSAP_SRC = OMO_ROOT / "background_library" / "vox" / "gsap.min.js"
DEFAULT_VOICE_REF = "D:/index-tts/my_voice.wav"

STATUS_FLOW = ["pending", "fetched", "scripting", "awaiting_script_review",
               "script_approved", "tts_done", "composed", "rendered", "packaged"]


# ---------------------------------------------------------------- helpers
def emit_json(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def sh(cmd, cwd=None, env=None, timeout=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    exe = shutil.which(cmd[0], path=e.get("PATH") or e.get("Path"))
    if exe:
        cmd = [exe, *cmd[1:]]
    return subprocess.run(cmd, cwd=cwd, env=e, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace")


def wav_duration(p: Path) -> float:
    with wave.open(str(p), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def sanitize_slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", name.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:48] or "episode"


def pid_of(slug: str) -> str:
    return slug if slug.startswith("console-") else f"console-{slug}"


def proj_dir(pid: str) -> Path:
    return PROJECTS_ROOT / pid


def state_path(pid: str) -> Path:
    return proj_dir(pid) / "state.json"


def load_state(pid: str):
    p = state_path(pid)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(pid: str, state: dict):
    state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    state_path(pid).write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def set_stage(pid: str, state: dict, stage: str, status: str, extra: dict | None = None):
    state.setdefault("stages", {})[stage] = {
        "status": status, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if extra:
        state["stages"][stage].update(extra)
    if status in ("done", "awaiting_human", "approved", "failed"):
        state["status"] = {
            "done": stage + "_done", "awaiting_human": stage + "_awaiting_human",
            "approved": stage + "_approved", "failed": stage + "_failed",
        }.get(status, state.get("status"))
    save_state(pid, state)


def load_episode(pid: str) -> dict | None:
    p = proj_dir(pid) / "artifacts" / "episode.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def iter_lines(episode: dict, subset=None):
    keep = set(subset) if subset else None
    for sc in episode.get("scenes", []):
        if keep and sc["id"] not in keep:
            continue
        for ln in sc.get("lines", []):
            yield sc, ln


# ---------------------------------------------------------------- new / fetch
def stage_new(slug: str, args) -> dict:
    pid = pid_of(slug)
    proj = proj_dir(pid)
    if proj.exists() and load_state(pid):
        return {"ok": True, "id": pid, "project_dir": str(proj), "note": "项目已存在（沿用）"}

    for d in ("artifacts", "assets/source", "assets/audio", "assets/music",
              "hyperframes", "renders", "package"):
        (proj / d).mkdir(parents=True, exist_ok=True)

    state = {"id": pid, "slug": slug, "title": "", "status": "pending",
             "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "stages": {}}
    save_state(pid, state)

    src = None
    if getattr(args, "ref_url", None):
        from tools.analysis.video_downloader import VideoDownloader
        r = VideoDownloader().execute({
            "url": args.ref_url, "output_dir": str(proj / "assets" / "source"),
            "format": "video", "max_resolution": "720p", "max_duration_seconds": 3600})
        if not r.success:
            set_stage(pid, state, "fetch", "failed", {"error": r.error})
            return {"ok": False, "error": f"下载失败: {r.error}"}
        src = Path(r.data["video_path"])
        state["source_url"] = args.ref_url
        state["source_meta"] = r.data.get("metadata", {})
    elif getattr(args, "ref_file", None):
        src = Path(args.ref_file)
        if not src.exists():
            return {"ok": False, "error": f"源文件不存在: {src}"}
        dst = proj / "assets" / "source" / ("ref" + src.suffix)
        shutil.copy2(src, dst)
        state["source_file"] = str(src)
        src = dst

    if src:
        set_stage(pid, state, "fetch", "in_progress")
        # 统一命名
        ref = proj / "assets" / "source" / ("ref" + src.suffix)
        if src.resolve() != ref.resolve():
            shutil.copy2(src, ref)
        # 转录
        from tools.analysis.transcriber import Transcriber
        r = Transcriber().execute({"input_path": str(ref),
                                   "output_dir": str(proj / "assets" / "source")})
        if not r.success:
            set_stage(pid, state, "fetch", "failed", {"error": r.error})
            return {"ok": False, "error": f"转录失败: {r.error}"}
        tsrc = proj / "assets" / "source" / (ref.stem + "_transcript.json")
        tdst = proj / "assets" / "source" / "transcript.json"
        if tsrc.exists() and tsrc != tdst:
            if tdst.exists():
                tdst.unlink()
            tsrc.rename(tdst)
        # 抽帧（每 25s 一帧，最多 24 帧）
        fdir = proj / "assets" / "source" / "frames"
        fdir.mkdir(parents=True, exist_ok=True)
        sh(["ffmpeg", "-y", "-i", str(ref), "-vf", "fps=1/25", "-frames:v", "24",
            str(fdir / "f_%03d.png")])
        report = {
            "source_url": state.get("source_url"),
            "source_file": state.get("source_file"),
            "video": str(ref), "transcript": str(tdst), "frames_dir": str(fdir),
            "meta": state.get("source_meta", {}),
        }
        (proj / "artifacts" / "fetch_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        state["title"] = state.get("source_meta", {}).get("title", "")
        set_stage(pid, state, "fetch", "done")
    else:
        set_stage(pid, state, "fetch", "done", {"note": "无源片（纯创作模式）"})

    return {"ok": True, "id": pid, "project_dir": str(proj)}


# ---------------------------------------------------------------- script
def _load_module(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_episode_module():
    return _load_module("cw_gen", GEN_COMPOSE)


def _flatten_lines(episode: dict) -> str:
    out = []
    for sc in episode.get("scenes", []):
        for ln in sc.get("lines", []):
            out.append(ln.get("text", ""))
    return "\n".join(out)


def collect_credits(ep: dict) -> list:
    """真实素材出处清单（image 零件 / registry 槽位 / footage / BGM）→ 发布文案【素材来源】段。"""
    rows = []
    aud = ep.get("audio") or {}
    bpv = aud.get("bgm_provenance") or {}
    if bpv.get("url"):
        rows.append(f"- [bgm] {bpv.get('credit') or bpv.get('url')} · "
                    f"{bpv.get('license', '?')} · {bpv.get('url')}")
    for sc in ep.get("scenes", []):
        ft = sc.get("footage") or {}
        pv = ft.get("provenance") or {}
        if pv.get("url"):
            rows.append(f"- [{sc['id']} footage] {pv.get('credit') or pv.get('url')} · "
                        f"{pv.get('license', '?')} · {pv.get('url')}")
        for sn, sdef in ((sc.get("registry") or {}).get("slots") or {}).items():
            pv = (sdef or {}).get("provenance") or {}
            if pv.get("url"):
                rows.append(f"- [{sc['id']} slot:{sn}] {pv.get('credit') or pv.get('url')} · "
                            f"{pv.get('license', '?')} · {pv.get('url')}")
        for ln in sc.get("lines", []):
            for e in ln.get("elements", []):
                if e.get("type") != "image":
                    continue
                pv = e.get("provenance") or {}
                if pv.get("url"):
                    rows.append(f"- [{e.get('id') or e.get('src')}] {pv.get('credit') or pv.get('url')} · "
                                f"{pv.get('license', '?')} · {pv.get('url')}")
    return rows


def stage_script(pid: str, args) -> dict:
    proj = proj_dir(pid)
    state = load_state(pid)
    if not state:
        return {"ok": False, "error": f"项目不存在: {pid}（先 new）"}
    ep = load_episode(pid)
    art = proj / "artifacts"

    if ep is None:
        example = _example_episode(state.get("title") or pid)
        (art / "episode.example.json").write_text(
            json.dumps(example, ensure_ascii=False, indent=1), encoding="utf-8")
        set_stage(pid, state, "script", "in_progress", {"note": "等待创作契约"})
        return {"ok": True, "id": pid, "status": "awaiting_episode",
                "hint": f"请由 Agent 撰写 {art / 'episode.json'}（参考 episode.example.json），"
                        f"完成后重新运行 script 校验。"}

    mod = _load_episode_module()
    mod.assign_ids(ep)
    errs, warns = mod.validate_episode(ep)

    # 能力侦察闸门（软性）：缺 capability_recon.json = 未做 HyperFrames 能力侦察
    recon = proj / "artifacts" / "capability_recon.json"
    if not recon.exists():
        warns.append("未做 HyperFrames 能力侦察：缺 artifacts/capability_recon.json（见 SKILL.md §8）")

    # 红线扫描（跨语言时天然低分，作为闸门附件保留）
    scan_info = None
    transcript = proj / "assets" / "source" / "transcript.json"
    if transcript.exists():
        try:
            td = json.loads(transcript.read_text(encoding="utf-8"))
            full = td.get("full_text") or td.get("text") or ""
            if not full:
                full = "".join(u.get("text", "") for u in td.get("utterances", []))
            (art / "source_transcript.txt").write_text(full, encoding="utf-8")
            (art / "script_flat.txt").write_text(_flatten_lines(ep), encoding="utf-8")
            r = sh([sys.executable, str(REDLINE_SCAN),
                    "--rewrite", str(art / "script_flat.txt"),
                    "--original", str(art / "source_transcript.txt"),
                    "--out", str(art / "redline_scan.json")])
            if (art / "redline_scan.json").exists():
                scan_info = json.loads((art / "redline_scan.json").read_text(encoding="utf-8"))
        except Exception as e:  # 扫描失败不阻塞闸门
            scan_info = {"error": str(e)}

    if errs:
        set_stage(pid, state, "script", "in_progress", {"errors": errs})
        return {"ok": False, "id": pid, "errors": errs, "warnings": warns}

    n_scenes = len(ep.get("scenes", []))
    n_lines = sum(len(sc.get("lines", [])) for sc in ep.get("scenes", []))
    est_chars = len(_flatten_lines(ep))
    set_stage(pid, state, "script", "awaiting_human",
              {"scenes": n_scenes, "lines": n_lines, "chars": est_chars})
    return {"ok": True, "id": pid, "status": "awaiting_script_review",
            "scenes": n_scenes, "lines": n_lines,
            "est_chars": est_chars, "est_minutes": round(est_chars / 4.6 / 60, 2),
            "warnings": warns,
            "capability_recon": recon.exists(),
            "real_assets": collect_credits(ep),
            "redline": (scan_info or {}).get("verdict") if scan_info else None,
            "gate": "人审闸门：请审阅 artifacts/episode.json 后运行 approve-script 放行"}


def stage_approve_script(pid: str, args) -> dict:
    state = load_state(pid)
    if not state:
        return {"ok": False, "error": f"项目不存在: {pid}"}
    ep = load_episode(pid)
    if ep is None:
        return {"ok": False, "error": "缺少 artifacts/episode.json"}
    mod = _load_episode_module()
    mod.assign_ids(ep)
    errs, _ = mod.validate_episode(ep)
    if errs:
        return {"ok": False, "errors": errs}
    set_stage(pid, state, "script", "approved")
    return {"ok": True, "id": pid, "status": "script_approved"}


# ---------------------------------------------------------------- synth (heavy)
def stage_synth(pid: str, args) -> dict:
    proj = proj_dir(pid)
    state = load_state(pid)
    if not state:
        return {"ok": False, "error": f"项目不存在: {pid}"}
    ep = load_episode(pid)
    if ep is None:
        return {"ok": False, "error": "缺少 artifacts/episode.json"}

    subset = [s.strip() for s in args.scenes.split(",")] if getattr(args, "scenes", None) else None
    voice = ep.get("voice", {}) or {}
    voice_ref = voice.get("voice_ref") or DEFAULT_VOICE_REF
    seed_base = int(voice.get("seed", 42))
    only_missing = bool(getattr(args, "only_missing", False))

    lines = list(iter_lines(ep, subset))
    if not lines:
        return {"ok": False, "error": "没有可合成的句子"}

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "indextts_client", str(OMO_ROOT / "apps" / "indextts-bridge" / "client.py"))
    if spec is None or spec.loader is None:
        return {"ok": False, "error": "无法加载 IndexTTS 客户端"}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    audio_dir = proj / "assets" / "audio"
    results = []
    t0 = time.time()
    with mod.IndexTTSSession(
            voice_ref=voice_ref, model_version=voice.get("model_version", "2.5"),
            lang=voice.get("lang", "ZH"), emotion=voice.get("emotion", "calm"),
            project_dir=str(proj)) as tts:
        for i, (sc, ln) in enumerate(lines):
            wav = audio_dir / f"{ln['id']}.wav"
            if only_missing and wav.exists() and wav.stat().st_size > 1000:
                results.append({"id": ln["id"], "scene": sc["id"], "text": ln["text"],
                                "wav": str(wav), "dur": round(wav_duration(wav), 3)})
                continue
            ok = tts.synthesize(ln["text"], wav, seed=seed_base + i)
            if not ok or not wav.exists():
                return {"ok": False, "error": f"合成失败: {ln['id']} ({ln['text'][:24]}…)"}
            dur = wav_duration(wav)
            if dur < 0.2:
                return {"ok": False, "error": f"静音/异常音频: {ln['id']} dur={dur:.3f}"}
            results.append({"id": ln["id"], "scene": sc["id"], "text": ln["text"],
                            "wav": str(wav), "dur": round(dur, 3)})
            if not getattr(args, "json", False):
                print(f">> synth [{i+1}/{len(lines)}] {ln['id']} {dur:.2f}s", flush=True)

    out = {"lines": results, "total": round(sum(r["dur"] for r in results), 2)}
    (proj / "artifacts" / "tts_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    set_stage(pid, state, "synth", "done", {"lines": len(results), "audio_seconds": out["total"]})
    return {"ok": True, "id": pid, "lines": len(results), "audio_total": out["total"],
            "elapsed_s": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- align (语音驱动)
def stage_align(pid: str, args) -> dict:
    """词级对齐：逐句 wav → whisper word timestamps → artifacts/line_words.json。
    之后 episode 元素可用 "at": "某个词" 锚定动作时刻（语音驱动）。"""
    proj = proj_dir(pid)
    state = load_state(pid)
    if not state:
        return {"ok": False, "error": f"项目不存在: {pid}"}
    tts_path = proj / "artifacts" / "tts_results.json"
    if not tts_path.exists():
        return {"ok": False, "error": "缺少 tts_results.json（先 synth）"}
    tts = json.loads(tts_path.read_text(encoding="utf-8"))
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"ok": False, "error": "缺少 faster_whisper（pip install faster-whisper）"}
    model = WhisperModel("small", device="cpu", compute_type="int8")
    audio_dir = proj / "assets" / "audio"
    out = {}
    t0 = time.time()
    for r in tts.get("lines", []):
        lid = r["id"]
        wav = Path(r.get("wav") or (audio_dir / f"{lid}.wav"))
        if not wav.exists():
            continue
        segs, _info = model.transcribe(str(wav), language="zh", word_timestamps=True)
        words = []
        for s in segs:
            for w in (s.words or []):
                t = w.word.strip()
                if t:
                    words.append({"w": t, "s": round(w.start, 3), "e": round(w.end, 3)})
        out[lid] = {"dur": r.get("dur"), "words": words}
        if not getattr(args, "json", False):
            print(f">> align [{len(out)}/{len(tts.get('lines', []))}] {lid}", flush=True)
    (proj / "artifacts" / "line_words.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    set_stage(pid, state, "align", "done", {"lines": len(out)})
    return {"ok": True, "id": pid, "lines": len(out), "elapsed_s": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- compose
def stage_compose(pid: str, args) -> dict:
    state = load_state(pid)
    if not state:
        return {"ok": False, "error": f"项目不存在: {pid}"}
    cmd = [sys.executable, str(GEN_COMPOSE), "--project", str(proj_dir(pid))]
    if getattr(args, "scenes", None):
        cmd += ["--scenes", args.scenes]
    if getattr(args, "no_audio", False):
        cmd += ["--no-audio"]
    cmd += ["--json"]
    r = sh(cmd)
    line = (r.stdout or "").strip().splitlines()
    result = None
    for ln in reversed(line):
        try:
            result = json.loads(ln)
            break
        except Exception:
            continue
    if result is None:
        return {"ok": False, "error": f"compose 输出异常: {r.stdout[-800:]}"}
    if result.get("ok"):
        set_stage(pid, state, "compose", "done",
                  {"total": result.get("total"), "scenes": result.get("scenes")})
    else:
        set_stage(pid, state, "compose", "failed", {"error": result.get("errors")})
    if not getattr(args, "json", False):
        print(f">> compose ok total={result.get('total')}s -> {result.get('index_html')}", flush=True)
    return result


# ---------------------------------------------------------------- render (heavy)
def stage_render(pid: str, args) -> dict:
    proj = proj_dir(pid)
    state = load_state(pid)
    if not state:
        return {"ok": False, "error": f"项目不存在: {pid}"}
    hf_dir = proj / "hyperframes"
    index = hf_dir / "index.html"
    if not index.exists():
        return {"ok": False, "error": "缺少 hyperframes/index.html（先 compose）"}

    # lint 先行（0 错误才渲染）；运行时统一 @latest（知识会漂移，运行时永远最新）
    env = dict(os.environ)
    env["npm_config_cache"] = str(OMO_ROOT / ".npm-cache")
    r = sh(["npx", "--yes", "hyperframes@latest", "lint", str(hf_dir)], env=env, timeout=600)
    if r.returncode != 0:
        tail = (r.stdout or "")[-1500:]
        set_stage(pid, state, "render", "failed", {"lint": tail[-300:]})
        return {"ok": False, "error": f"lint 失败: {tail}"}

    out = proj / "renders" / "final.mp4"
    t0 = time.time()
    # 长片渲染防护：低内存流式编码 + 临时目录/帧缓存挪到仓库盘（C 盘不足会 capture_disk 失败）
    hf_tmp = OMO_ROOT / ".hf-tmp"
    hf_cache = OMO_ROOT / ".hf-cache"
    hf_tmp.mkdir(exist_ok=True)
    hf_cache.mkdir(exist_ok=True)
    env["TEMP"] = str(hf_tmp)
    env["TMP"] = str(hf_tmp)
    env["HYPERFRAMES_EXTRACT_CACHE_DIR"] = str(hf_cache)
    env["PRODUCER_LOW_MEMORY_MODE"] = "1"
    env["PRODUCER_STREAMING_ENCODE_MAX_DURATION_SECONDS"] = "7200"
    cmd = ["npx", "--yes", "hyperframes@latest", "render", str(hf_dir), "-o", str(out),
           "--low-memory-mode"]
    r = sh(cmd, cwd=str(proj), env=env, timeout=7200)
    if r.returncode != 0 or not out.exists():
        set_stage(pid, state, "render", "failed", {"error": (r.stdout or "")[-400:]})
        return {"ok": False, "error": f"渲染失败: {(r.stdout or '')[-1500:]}"}

    out4k = None
    if getattr(args, "enable_4k", False):
        out4k = proj / "renders" / "final_4k.mp4"
        r4 = sh(["ffmpeg", "-y", "-i", str(out), "-vf", "scale=3840:2160:flags=lanczos",
                 "-c:v", "libx265", "-crf", "18", "-preset", "slow",
                 "-c:a", "aac", "-b:a", "320k", str(out4k)], timeout=5400)
        if not (r4.returncode == 0 and out4k.exists()):
            out4k = None

    set_stage(pid, state, "render", "done", {"output": str(out)})
    return {"ok": True, "id": pid, "video": str(out),
            "video_4k": str(out4k) if out4k else None,
            "elapsed_s": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- package
def stage_package(pid: str, args) -> dict:
    proj = proj_dir(pid)
    state = load_state(pid)
    if not state:
        return {"ok": False, "error": f"项目不存在: {pid}"}
    final = proj / "renders" / "final.mp4"
    if not final.exists():
        return {"ok": False, "error": "缺少 renders/final.mp4（先 render）"}
    pkg = proj / "package"
    pkg.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, pkg / "final.mp4")

    ep = load_episode(pid) or {}
    credits = collect_credits(ep)

    # 封面：AI 排版封面优先（package/cover_16x9.png 已存在则不覆盖）；否则截帧兜底
    cover = pkg / "cover_16x9.png"
    if not cover.exists():
        cover_at = float(ep.get("cover_at", 5.0))
        raw = pkg / "cover_frame.png"
        sh(["ffmpeg", "-y", "-ss", str(cover_at), "-i", str(final), "-frames:v", "1", str(raw)])
        title = ep.get("cover_title") or ep.get("title") or state.get("title") or pid
        try:
            from PIL import Image, ImageDraw, ImageFont
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:  # 老版本 Pillow：LANCZOS 常量为 1
                resample = 1
            img = Image.open(raw).convert("RGBA").resize((1146, 717), resample)

            # 底部渐变遮罩（压住字幕条，给标题留净空）
            scrim = Image.new("RGBA", (1146, 717), (0, 0, 0, 0))
            sd = ImageDraw.Draw(scrim)
            g0, g1 = 360, 717
            for yy in range(g0, g1):
                a = int(252 * ((yy - g0) / (g1 - g0)))
                sd.line([(0, yy), (1146, yy)], fill=(7, 9, 11, a))
            img = Image.alpha_composite(img, scrim)

            d = ImageDraw.Draw(img)
            font_path = "C:/Windows/Fonts/msyhbd.ttc"
            if not Path(font_path).exists():
                font_path = "C:/Windows/Fonts/msyh.ttc"
            f1 = ImageFont.truetype(font_path, 58)
            tag = ImageFont.truetype(font_path, 27)
            x, y = 64, 476
            d.rectangle([x, y - 6, x + 7, y + 132], fill=(229, 72, 77))
            d.multiline_text((x + 30, y), title, font=f1, fill=(240, 244, 248), spacing=14,
                             stroke_width=2, stroke_fill=(6, 8, 10))
            d.text((x + 32, y + 96), "中文版 · 控制台译制", font=tag, fill=(139, 148, 158))
            img.convert("RGB").save(cover, "PNG")
        except Exception:
            shutil.copy2(raw, cover)

    # 发布文案：agent 创作 publish_copy.json 优先；统一输出单文档 txt
    pc = proj / "artifacts" / "publish_copy.json"
    if pc.exists():
        data = json.loads(pc.read_text(encoding="utf-8"))
        (pkg / "publish_copy.txt").write_text(_publish_txt(data, credits=credits), encoding="utf-8")
    else:
        tpl = {
            "platform": "bilibili",
            "titles": ["（备选标题 1）", "（备选标题 2）"],
            "description": "（简介；含 AI 声明）",
            "tags": ["Agent Harness", "AI Agent", "大模型"],
            "ai_disclosure": "本视频使用 AI 语音合成与 AI 辅助画面制作。",
        }
        (pkg / "publish_copy.txt").write_text(_publish_txt(tpl, credits=credits), encoding="utf-8")

    note = []
    for f in sorted(pkg.glob("*")):
        note.append(f"- {f.name}")
    (pkg / "README.txt").write_text(
        "console-remake 成品包\n" + "\n".join(note) + "\n\n发布提醒：B站上传时勾选「AI 生成」声明。\n",
        encoding="utf-8")
    set_stage(pid, state, "package", "done", {"dir": str(pkg)})
    return {"ok": True, "id": pid, "package_dir": str(pkg)}


# ---------------------------------------------------------------- composites
def stage_run(slug: str, args) -> dict:
    r = stage_new(slug, args)
    if not r.get("ok"):
        return r
    pid = r["id"]
    rs = stage_script(pid, args)
    return {"ok": True, "id": pid, "project_dir": r["project_dir"],
            "next": "script 闸门", "script": rs}


def stage_run_heavy(pid: str, args) -> dict:
    steps = {}
    if getattr(args, "scenes", None) in (None, ""):
        pass
    rs = stage_synth(pid, args)
    steps["synth"] = rs
    if not rs.get("ok"):
        return {"ok": False, "id": pid, "failed": "synth", "detail": rs}
    ra = stage_align(pid, args)
    steps["align"] = ra
    rc = stage_compose(pid, args)
    steps["compose"] = rc
    if not rc.get("ok"):
        return {"ok": False, "id": pid, "failed": "compose", "detail": rc}
    rr = stage_render(pid, args)
    steps["render"] = rr
    if not rr.get("ok"):
        return {"ok": False, "id": pid, "failed": "render", "detail": rr}
    rp = stage_package(pid, args)
    steps["package"] = rp
    return {"ok": True, "id": pid,
            "video": rr.get("video"), "package_dir": rp.get("package_dir"),
            "compose_total": rc.get("total"),
            "steps": {k: v.get("ok") for k, v in steps.items()}}


# ---------------------------------------------------------------- publish txt
def _publish_txt(pc: dict, credits=None) -> str:
    """把 publish_copy.json 渲染成单文档一键复制 txt（B站发布用；credits=真实素材出处清单）。"""
    L = []
    L.append("=" * 44)
    L.append(" 发布文案（单文档 · 一键复制）")
    L.append("=" * 44)
    L.append("")
    titles = pc.get("titles") or []
    for i, t in enumerate(titles, 1):
        L.append(f"【标题·备选 {i}】")
        L.append(t)
        L.append("")
    L.append("【简介】")
    L.append(pc.get("description", ""))
    L.append("")
    tags = pc.get("tags") or []
    if tags:
        L.append("【标签】")
        L.append("，".join(tags) if pc.get("platform") != "bilibili" else ",".join(tags))
        L.append("")
    L.append("【AI 声明】")
    L.append(pc.get("ai_disclosure", "本视频由 AI 辅助制作。发布时勾选「AI 生成」声明。"))
    L.append("")
    if pc.get("credit"):
        L.append("【署名】")
        L.append(pc["credit"])
        L.append("")
    if credits:
        L.append("【素材来源】")
        L.extend(credits)
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- archive
def stage_archive(pid: str, args) -> dict:
    proj = proj_dir(pid)
    state = load_state(pid)
    if not state:
        return {"ok": False, "error": f"项目不存在: {pid}"}
    final = proj / "renders" / "final.mp4"
    if not final.exists():
        return {"ok": False, "error": "缺少 renders/final.mp4（先 render）"}

    exp = OMO_ROOT / "exports" / pid
    for d in ("video", "thumbnails", "metadata"):
        (exp / d).mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, exp / "video" / "final.mp4")

    for name in ("cover_16x9.png", "cover_4x3.png", "cover_frame.png"):
        src = proj / "package" / name
        if src.exists():
            shutil.copy2(src, exp / "thumbnails" / name)

    # 发布文案：单文档 txt（package 产物优先；缺失则由 json 现场渲染）
    txt_src = proj / "package" / "publish_copy.txt"
    if txt_src.exists():
        shutil.copy2(txt_src, exp / "metadata" / "publish_copy.txt")
    elif (proj / "artifacts" / "publish_copy.json").exists():
        data = json.loads((proj / "artifacts" / "publish_copy.json").read_text(encoding="utf-8"))
        (exp / "metadata" / "publish_copy.txt").write_text(
            _publish_txt(data, credits=collect_credits(load_episode(pid) or {})), encoding="utf-8")

    # 制作档案（可追溯）
    ep = load_episode(pid) or {}
    timing = {}
    tp = proj / "artifacts" / "timings.json"
    if tp.exists():
        timing = json.loads(tp.read_text(encoding="utf-8"))
    meta = {
        "project": pid,
        "title": ep.get("title"),
        "source": ep.get("source", {}),
        "voice": ep.get("voice", {}),
        "duration_seconds": timing.get("total"),
        "scenes": [
            {"id": s["id"], "label": next((sc.get("label") for sc in ep.get("scenes", []) if sc["id"] == s["id"]), ""),
             "start": s["start"], "end": s["end"]}
            for s in timing.get("scenes", [])
        ],
        "lines": len(timing.get("lines", [])),
        "render": {"file": "video/final.mp4", "width": 1920, "height": 1080, "fps": 30},
        "ai_disclosure": "本视频由 AI 辅助制作：AI 语音合成 + AI 辅助画面（程序化动态图形 + 真实素材，无 AI 生图）。",
        "credit": "改编自 Kai《Agent Harness explained in 8min..》· 中文重述与视觉重制",
        "credits": collect_credits(ep),
        "archived_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (exp / "metadata" / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.copy2(proj / "artifacts" / "episode.json", exp / "metadata" / "episode.json")

    # 章节时间轴（B站简介可直接用）
    lines = ["# 章节时间轴", ""]
    for s in timing.get("scenes", []):
        label = next((sc.get("label") for sc in ep.get("scenes", []) if sc["id"] == s["id"]), "")
        mm = int(s["start"] // 60)
        ss = int(s["start"] % 60)
        lines.append(f"{mm:02d}:{ss:02d} {label}")
    (exp / "metadata" / "chapters.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    set_stage(pid, state, "archive", "done", {"dir": str(exp)})
    state["status"] = "archived"
    save_state(pid, state)
    return {"ok": True, "id": pid, "export_dir": str(exp),
            "files": sorted(str(p.relative_to(exp)) for p in exp.rglob("*") if p.is_file())}


# ---------------------------------------------------------------- status
def stage_status(args) -> dict:
    rows = []
    for sp in sorted(PROJECTS_ROOT.glob("console-*")):
        stp = sp / "state.json"
        if not stp.exists():
            continue
        st = json.loads(stp.read_text(encoding="utf-8"))
        rows.append({"id": st.get("id"), "title": (st.get("title") or "")[:36],
                     "status": st.get("status"), "updated": st.get("updated_at")})
    return {"ok": True, "projects": rows}


# ---------------------------------------------------------------- example
def _example_episode(title: str) -> dict:
    return {
        "slug": "example",
        "title": title,
        "source": {"url": "", "title": "", "author": "", "duration": 0},
        "voice": {"voice_ref": DEFAULT_VOICE_REF, "model_version": "2.5",
                  "lang": "ZH", "seed": 42, "emotion": "calm"},
        "audio": {"bgm": None, "bgm_volume": 0.12},
        "timing": {"line_gap": 0.35, "scene_gap": 0.6, "scene_lead_in": 0.35, "tail": 2.2},
        "subtitles": True,
        "cover_at": 5.0,
        "scenes": [
            {
                "id": "s01", "label": "示例幕 · 空",
                "lines": [
                    {"id": "s01l01", "text": "这里是一句中文旁白，演示字幕条与元素入场。",
                     "elements": [
                         {"type": "text", "x": 760, "y": 500, "text": "AGENT HARNESS",
                          "size": 56, "mono": True},
                         {"type": "source", "x": 120, "y": 930,
                          "text": "example.com — 来源标注"},
                     ]},
                    {"id": "s01l02", "text": "第二句演示零件：格阵、胶囊、箭头与巨数。",
                     "elements": [
                         {"type": "grid", "x": 260, "y": 420, "rows": 3, "cols": 40,
                          "cell": 22, "fill": 0.68, "fill_color": "red",
                          "label_left": "系统提示", "label_right": "你的实际代码",
                          "divider": True},
                         {"type": "bignum", "x": 1500, "y": 300, "text": "15×",
                          "size": 220, "color": "red", "sub": "成本倍数", "count": True},
                     ]},
                ],
            },
        ],
    }


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="console-remake 管线 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("new", help="创建项目并抓取源片")
    p.add_argument("slug")
    p.add_argument("--ref-url", default=None)
    p.add_argument("--ref-file", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("script", help="校验创作契约 + 红线扫描 → 脚本闸门")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("approve-script", help="人审放行脚本")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("synth", help="逐句克隆配音（重）")
    p.add_argument("id")
    p.add_argument("--scenes", default=None)
    p.add_argument("--only-missing", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("align", help="词级对齐（语音驱动锚定用，轻）")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("compose", help="装配 HyperFrames（轻）")
    p.add_argument("id")
    p.add_argument("--scenes", default=None)
    p.add_argument("--no-audio", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("render", help="渲染成片（重）")
    p.add_argument("id")
    p.add_argument("--4k", dest="enable_4k", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("package", help="成品包")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("archive", help="归档到 exports/<id>/（成片/封面/文案/章节/制作档案）")
    p.add_argument("id")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("run", help="new + script（轻）")
    p.add_argument("slug")
    p.add_argument("--ref-url", default=None)
    p.add_argument("--ref-file", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("run-heavy", help="synth + compose + render + package（重）")
    p.add_argument("id")
    p.add_argument("--scenes", default=None)
    p.add_argument("--only-missing", action="store_true")
    p.add_argument("--4k", dest="enable_4k", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("status", help="查看项目状态")
    p.add_argument("--json", action="store_true")

    args = ap.parse_args()
    is_json = getattr(args, "json", False)

    if args.cmd == "new":
        r = stage_new(args.slug, args)
    elif args.cmd == "script":
        r = stage_script(args.id, args)
    elif args.cmd == "approve-script":
        r = stage_approve_script(args.id, args)
    elif args.cmd == "synth":
        r = stage_synth(args.id, args)
    elif args.cmd == "align":
        r = stage_align(args.id, args)
    elif args.cmd == "compose":
        r = stage_compose(args.id, args)
    elif args.cmd == "render":
        r = stage_render(args.id, args)
    elif args.cmd == "package":
        r = stage_package(args.id, args)
    elif args.cmd == "archive":
        r = stage_archive(args.id, args)
    elif args.cmd == "run":
        r = stage_run(args.slug, args)
    elif args.cmd == "run-heavy":
        r = stage_run_heavy(args.id, args)
    elif args.cmd == "status":
        r = stage_status(args)
    else:
        r = {"ok": False, "error": "未知命令"}

    if is_json:
        emit_json(r)
    elif not r.get("ok"):
        print(f"ERROR: {json.dumps(r, ensure_ascii=False)[:1500]}")
    else:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    sys.exit(0 if r.get("ok") else 1)


if __name__ == "__main__":
    main()
