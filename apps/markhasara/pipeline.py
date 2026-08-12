"""MarkHasara 二创解说流水线核心逻辑。

轻/重任务拆分（对齐 auto-dub 多智能体编排）：
- process_light（轻）：下载 -> 转录 -> 二创文案生成（LLM，主 Agent 可跑）
- render_assets（重）：TTS 合成用户声音（GPU，派发 Compute Worker）
- render_video（重）：头像框替换 + 字幕 + 压制（FFmpeg，派发 Compute Worker）
"""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_DIR = "projects/markhasara"


def _map_voice_lang(target_language: str) -> str:
    """把 target_language（如 zh-CN）映射为 IndexTTS 2.5 lang 标签（默认 ZH）。"""
    base = target_language.split("-")[0].strip().lower()
    return {"zh": "ZH", "en": "EN", "ja": "JA", "es": "ES",
            "ko": "KO", "fr": "FR", "de": "DE"}.get(base, "ZH")


def _ensure_dirs(base: Path):
    for d in ["source", "transcripts", "scripts", "audio", "renders", "covers", "published"]:
        (base / d).mkdir(parents=True, exist_ok=True)


def _video_workdir(base: Path, video_id: str) -> dict:
    """返回单条视频的工作目录。"""
    return {
        "base": base,
        "source": base / "source",
        "transcripts": base / "transcripts",
        "scripts": base / "scripts",
        "audio": base / "audio",
        "renders": base / "renders",
    }


# ---------------------------------------------------------------------------
# process_light：下载 -> 转录 -> 二创文案
# ---------------------------------------------------------------------------

def process_light(config: dict, db) -> dict:
    """轻任务：对 SAFE 队列中未处理的视频做 下载->转录->二创文案。

    复用 auto-dub 的 Transcriber（BaseTool）+ 自研 CommentaryGenerator（LLM）。
    不触碰 GPU TTS / FFmpeg（重算力交 render-assets / render-video）。
    """
    project_root = Path(config["output"]["base_dir"])
    if not project_root.is_absolute():
        project_root = Path(__file__).resolve().parent.parent.parent / project_root
    _ensure_dirs(project_root)
    workdirs = _video_workdir(project_root, "")

    # 读合规清单，取 SAFE 子集
    safe_ids = _load_safe_ids(config)
    if not safe_ids:
        return {"command": "process", "success": False, "error": "合规清单为空或 SAFE 子集为空，请先 classify"}

    # 取 DB 中已扫描但未处理（status=discovered）且属于 SAFE 的视频。
    # 预筛：DB duration 明确 >60s 的直接跳过（非 Shorts，不下载）；未知(0) 或 <=60 才下载验证
    candidates = []
    for v in db.get_by_status("discovered"):
        if v["video_id"] not in safe_ids:
            continue
        dur = v.get("duration_seconds") or 0
        if dur > 60:
            db.update_status(v["video_id"], "not_short", error_msg="DB 时长>60s，非 Shorts")
            continue
        candidates.append(v)
        if len(candidates) >= 5:
            break
    if not candidates:
        return {"command": "process", "success": False, "note": "无可处理候选（SAFE 子集已全部处理或清单为空）", "count": 0}

    from tools.analysis.transcriber import Transcriber
    from apps.markhasara.commentary_gen import CommentaryGenerator, load_transcript_text

    transcriber = Transcriber()
    gen = CommentaryGenerator(config)
    cfg = config.get("transcription", {})

    processed = 0
    for v in candidates[:5]:  # 每轮最多 5 条（轻任务）
        vid = v["video_id"]
        db.update_status(vid, "processing")
        try:
            source_path = _download_video(vid, workdirs["source"])
            if not source_path:
                db.update_status(vid, "failed", error_msg="下载失败")
                continue

            # 时长守卫：只处理真正的 Shorts（<60s）。部分 /shorts/ URL 会解析成长视频
            if _is_long_video(source_path):
                db.update_status(vid, "not_short", error_msg="时长>60s，非 Shorts，跳过")
                logger.info("[MarkHasara] %s 时长>60s 非 Shorts，跳过", vid)
                continue

            # 转录
            trans_dir = workdirs["transcripts"]
            trans_res = transcriber.execute({
                "input_path": str(source_path),
                "output_dir": str(trans_dir),
                "model_size": cfg.get("whisper_model", "base"),
                "language": cfg.get("language", "en"),
                "diarize": False,
            })
            if not trans_res.success:
                db.update_status(vid, "failed", error_msg=f"转录失败: {trans_res.error}")
                continue

            transcript_path = trans_res.artifacts[0] if trans_res.artifacts else \
                (trans_dir / f"{source_path.stem}_transcript.json")
            text = load_transcript_text(Path(transcript_path))

            # 无解说视频（转录为空）：跳过二创文案/TTS，但流程继续（画面处理 + 保留原声）
            if not text.strip():
                db.update_status(vid, "no_speech",
                                 error_msg="原视频无解说（转录为空），跳过二创解说，保留原声走画面处理")
                logger.info("[MarkHasara] %s 无解说（转录为空），保留原声", vid)
                continue

            # 二创文案生成（按视频时长动态算字数预算，覆盖全程）
            video_dur = _probe_video_duration(source_path)
            commentary = gen.generate(v["title"], text, duration_seconds=video_dur)
            if not commentary:
                db.update_status(vid, "failed", error_msg="二创文案生成失败（LLM）")
                continue

            script_path = workdirs["scripts"] / f"{vid}_commentary.json"
            script_path.write_text(json.dumps({
                "video_id": vid,
                "title": v["title"],
                "transcript_text": text,
                "commentary": commentary,
                "style": config.get("commentary", {}).get("style"),
            }, ensure_ascii=False, indent=2), encoding="utf-8")

            db.update_status(vid, "script_ready", output_path=str(script_path))
            processed += 1
            logger.info("[MarkHasara] %s 二创文案完成: %s", vid, commentary[:50])
        except Exception as e:
            logger.exception("处理 %s 失败", vid)
            db.update_status(vid, "failed", error_msg=str(e))

    return {"command": "process", "success": True, "processed": processed, "note": "轻任务完成，重算力请派发 render-assets"}


def _load_safe_ids(config: dict) -> set:
    """读合规清单，返回 SAFE 子集 video_id。"""
    list_path = Path(config["compliance"]["list_path"])
    if not list_path.is_absolute():
        list_path = Path(__file__).resolve().parent.parent.parent / list_path
    if not list_path.exists():
        return set()
    data = json.loads(list_path.read_text(encoding="utf-8"))
    return {item["video_id"] for item in data.get("SAFE", [])}


def _is_long_video(video_path: Path, max_seconds: int = 60) -> bool:
    """用 ffprobe 检查视频时长是否超过阈值（非 Shorts）。"""
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        duration = float(res.stdout.strip().split(",")[0])
        return duration > max_seconds
    except (ValueError, IndexError):
        return False


def _download_video(video_id: str, out_dir: Path) -> Optional[Path]:
    """下载 Shorts 到 out_dir。返回下载的 mp4 路径。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{video_id}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out
    url = f"https://www.youtube.com/shorts/{video_id}"
    cmd = [
        "yt-dlp", "-f", "best[height<=720][ext=mp4]/best[height<=720]/best",
        "--merge-output-format", "mp4", "-o", str(out),
        "--no-playlist", "--no-progress", url,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        logger.error("下载 %s 失败: %s", video_id, res.stderr[-300:])
        return None
    return out if out.exists() else None


# ---------------------------------------------------------------------------
# render_assets：TTS 合成用户声音（GPU 重算力）
# ---------------------------------------------------------------------------

def render_assets(config: dict, db, video_id: str) -> dict:
    """TTS 合成二创解说音频（用户声音克隆）。GPU 重算力，派发 Compute Worker。

    no_speech 视频（无解说）跳过：无二创文案可合成。
    """
    video = db.get_by_id(video_id)
    if not video:
        return {"command": "render-assets", "success": False, "error": f"视频 {video_id} 不存在"}

    # 无解说视频：跳过 TTS（render-video 会保留原声处理）
    if video.get("status") == "no_speech":
        return {"command": "render-assets", "success": True, "video_id": video_id,
                "note": "无解说视频，跳过 TTS，render-video 将保留原声"}

    project_root = Path(config["output"]["base_dir"])
    if not project_root.is_absolute():
        project_root = Path(__file__).resolve().parent.parent.parent / project_root
    _ensure_dirs(project_root)
    workdirs = _video_workdir(project_root, video_id)

    # 读取二创文案
    script_path = workdirs["scripts"] / f"{video_id}_commentary.json"
    if not script_path.exists():
        return {"command": "render-assets", "success": False, "error": f"未找到二创文案 {script_path}，先跑 process"}
    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    commentary = script_data.get("commentary", "")
    if not commentary:
        return {"command": "render-assets", "success": False, "error": "二创文案为空"}

    # 用户声音参考（用户录音，IndexTTS2 voice_ref 克隆）
    voice_cfg = config.get("voice", {})
    user_ref_raw = voice_cfg.get("user_voice_ref", "")
    user_ref = None
    if user_ref_raw:
        ref = Path(user_ref_raw)
        if not ref.is_absolute():
            ref = Path(__file__).resolve().parent.parent.parent / ref
        if ref.exists():
            user_ref = ref

    emotion = voice_cfg.get("tts_emotion", "calm")
    model_version = voice_cfg.get("tts_model_version", "2.5")
    tts_lang = voice_cfg.get("tts_lang", "") or _map_voice_lang(
        str(voice_cfg.get("tts_target_language", "zh-CN")))
    use_qwen_emo = bool(voice_cfg.get("tts_use_qwen_emo", False))
    out_wav = workdirs["audio"] / f"{video_id}_commentary.wav"

    # IndexTTS2 常驻服务桥（与 auto-dub 一致：GpuLockHandle + 常驻服务 + voice_ref 克隆）
    from apps.markhasara.index_tts import IndexTTS2Bridge
    with IndexTTS2Bridge(project_dir=workdirs["base"], voice_ref=user_ref, emotion=emotion,
                         model_version=model_version, lang=tts_lang,
                         use_qwen_emo=use_qwen_emo) as tts:
        if not tts.synthesize(commentary, out_wav, seed=42):
            db.update_status(video_id, "failed", error_msg="IndexTTS2 合成失败")
            return {"command": "render-assets", "success": False, "error": "IndexTTS2 合成失败"}

    db.update_status(video_id, "audio_ready", output_path=str(out_wav))
    return {"command": "render-assets", "success": True, "video_id": video_id, "audio": str(out_wav)}


# ---------------------------------------------------------------------------
# render_video：画幅转换 + 头像框替换 + 压制（FFmpeg 重算力）
# ---------------------------------------------------------------------------

def _probe_resolution(video_path: Path) -> tuple[int, int]:
    """读取视频分辨率 (w, h)。"""
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        w, h = res.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except (ValueError, IndexError):
        return 0, 0


def _probe_video_duration(video_path: Path) -> float:
    """读取视频时长（秒）。"""
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(res.stdout.strip().split(",")[0])
    except (ValueError, IndexError):
        return 0.0


def _convert_to_portrait(input_path: Path, output_path: Path) -> bool:
    """横屏转 9:16 竖屏：中心裁切到 9:16 比例。

    竖屏(宽<高)原样保留；横屏裁切成 9:16。保持内容主体居中。
    """
    w, h = _probe_resolution(input_path)
    if w <= 0 or h <= 0:
        return False
    if w <= h:  # 已是竖屏
        return True

    # 目标 9:16：宽 = h * 9/16
    target_w = int(h * 9 / 16)
    if target_w >= w:  # 源已接近 9:16，直接缩放
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(input_path),
            "-vf", "scale=-2:1080",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            str(output_path),
        ]
    else:
        # 中心裁切到 9:16 再放大到 1080 高
        crop_x = (w - target_w) // 2
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(input_path),
            "-vf", f"crop={target_w}:{h}:{crop_x}:0,scale=-2:1080",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            str(output_path),
        ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return res.returncode == 0


def render_video(config: dict, db, video_id: str) -> dict:
    """画幅转换 + 头像框替换 + 音频处理 + 压制合成最终竖屏视频。FFmpeg 重算力。

    音频处理（用户决策）：
    - 有解说视频：demucs 分离原音频 → 保留环境音(no_vocals) + 叠加二创中文人声
    - 无解说视频：保留原声（本来就是环境音）
    """
    video = db.get_by_id(video_id)
    if not video:
        return {"command": "render-video", "success": False, "error": f"视频 {video_id} 不存在"}

    project_root = Path(config["output"]["base_dir"])
    if not project_root.is_absolute():
        project_root = Path(__file__).resolve().parent.parent.parent / project_root
    _ensure_dirs(project_root)
    workdirs = _video_workdir(project_root, video_id)

    source = workdirs["source"] / f"{video_id}.mp4"
    if not source.exists():
        return {"command": "render-video", "success": False, "error": f"源视频不存在 {source}"}

    is_no_speech = video.get("status") == "no_speech"
    audio = workdirs["audio"] / f"{video_id}_commentary.wav"
    if not is_no_speech and not audio.exists():
        return {"command": "render-video", "success": False, "error": f"解说音频不存在 {audio}，先跑 render-assets"}

    avatar_cfg = config.get("avatar", {})

    # 1) 画幅转换：横屏 → 9:16 竖屏（抖音/小红书基本要求）
    portrait_path = workdirs["renders"] / f"{video_id}_portrait.mp4"
    w, h = _probe_resolution(source)
    if w > h and w > 0:
        if not _convert_to_portrait(source, portrait_path):
            return {"command": "render-video", "success": False, "error": "画幅转换失败"}
        video_input = portrait_path
    else:
        video_input = source

    # 2) 头像框替换（box_replacer，先检测是否有头像框，无则跳过）
    boxed_path = workdirs["renders"] / f"{video_id}_boxed.mp4"
    if avatar_cfg.get("replace_enabled", True) and avatar_cfg.get("image_path"):
        from tools.avatar.box_replacer import BoxReplacer
        replacer = BoxReplacer()
        box_res = replacer.execute({
            "input_path": str(video_input),
            "image_path": avatar_cfg["image_path"],
            "output_path": str(boxed_path),
            "box_hint": avatar_cfg.get("box_hint", "lower_left"),
            "skip_if_no_face": True,
        })
        if not box_res.success:
            return {"command": "render-video", "success": False, "error": f"头像框替换失败: {box_res.error}"}
        # 只有确实替换了（检测到头像框）才用 boxed_path；无头像框跳过替换
        if box_res.data.get("replaced", False):
            video_input = boxed_path

    # 3) 音频处理
    if is_no_speech:
        # 无解说视频：保留原声（环境音/引擎声），直接压制
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_input),
            "-map", "0:v", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            str(workdirs["renders"] / f"{video_id}_final.mp4"),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            return {"command": "render-video", "success": False, "error": f"压制失败: {res.stderr[-500:]}"}
        out_path = workdirs["renders"] / f"{video_id}_final.mp4"
    else:
        # 有解说视频：demucs 分离环境音 → 叠加二创人声 → 压制
        from apps.markhasara.vocal_sep import separate_vocals, mix_commentary_with_ambience
        # 提取原视频音频
        raw_audio = workdirs["audio"] / f"{video_id}_raw.wav"
        extract_cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_input),
            "-vn", "-ar", "44100", "-ac", "2",
            str(raw_audio),
        ]
        if subprocess.run(extract_cmd, capture_output=True, text=True, timeout=120).returncode != 0:
            return {"command": "render-video", "success": False, "error": "原音频提取失败"}

        # demucs 分离（vocals 丢弃，保留 no_vocals 环境音）
        sep_dir = workdirs["audio"] / "separated"
        separated = separate_vocals(raw_audio, sep_dir)
        if separated is None:
            # 分离失败：降级为直接替换整轨（仅人声）
            logger.warning("[MarkHasara] %s demucs 分离失败，降级整轨替换", video_id)
            mix_audio = audio
        else:
            _, no_vocals = separated
            # 环境音 + 二创人声混音
            mix_audio = workdirs["audio"] / f"{video_id}_mixed.wav"
            if not mix_commentary_with_ambience(audio, no_vocals, mix_audio):
                logger.warning("[MarkHasara] %s 混音失败，降级整轨替换", video_id)
                mix_audio = audio

        # 压制（替换音轨）
        out_path = workdirs["renders"] / f"{video_id}_final.mp4"
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(video_input),
            "-i", str(mix_audio),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            return {"command": "render-video", "success": False, "error": f"压制失败: {res.stderr[-500:]}"}

    db.update_status(video_id, "render_ready", output_path=str(out_path))
    return {"command": "render-video", "success": True, "video_id": video_id, "output": str(out_path)}
