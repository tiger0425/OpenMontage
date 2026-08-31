#!/usr/bin/env python3
"""使用 MiniMax-M3 多模态模型分析图片和视频内容。

通过 OpenCode 内置的 minimax-cn-coding-plan provider 调用 MiniMax M3 模型，
对图片进行视觉分析，对视频进行帧提取后逐帧分析。

用法:
    # 分析单张图片
    python3 analyze_media.py image.jpg

    # 分析视频（自动提取帧）
    python3 analyze_media.py video.mp4

    # 多文件分析
    python3 analyze_media.py img1.jpg img2.jpg video.mp4

    # 自定义提示词
    python3 analyze_media.py image.jpg -p "详细描述构图、色彩和主体"
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


_quiet = False
AUTH_JSON_PATH = Path.home() / ".local" / "share" / "opencode" / "auth.json"
PROVIDER_NAME = "minimax-cn-coding-plan"
MODEL_NAME = "MiniMax-M3"
API_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MAX_FRAMES = 8


def log(msg):
    if not _quiet:
        print(f"[minimax-m3-vision] {msg}", file=sys.stderr)


def die(msg):
    print(json.dumps({"success": False, "error": msg}), file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    if not AUTH_JSON_PATH.is_file():
        die(f"OpenCode auth.json 未找到: {AUTH_JSON_PATH}")
    with open(AUTH_JSON_PATH) as f:
        auth = json.load(f)
    provider = auth.get(PROVIDER_NAME)
    if not provider:
        die(f"provider '{PROVIDER_NAME}' 未在 auth.json 中配置")
    key = provider.get("key", "")
    if not key:
        die(f"provider '{PROVIDER_NAME}' 的 API key 为空")
    return key


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _is_image(path: str) -> bool:
    mime, _ = mimetypes.guess_type(path)
    if mime and mime.startswith("image/"):
        return True
    ext = Path(path).suffix.lower()
    return ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")


def _is_video(path: str) -> bool:
    mime, _ = mimetypes.guess_type(path)
    if mime and mime.startswith("video/"):
        return True
    ext = Path(path).suffix.lower()
    return ext in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv")


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _image_content_block(path: str) -> dict:
    ext = Path(path).suffix.lower().lstrip(".")
    if ext == "jpg":
        ext = "jpeg"
    b64 = _encode_image(path)
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/{ext};base64,{b64}"},
    }


# ---------------------------------------------------------------------------
# Video frame extraction (via ffmpeg)
# ---------------------------------------------------------------------------

def _get_video_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _extract_frames_interval(path: str, max_frames: int, temp_dir: str) -> list[dict]:
    duration = _get_video_duration(path)
    if duration <= 0:
        log("警告: 无法获取视频时长，使用匀速采样")
        duration = 30
    interval = max(0.5, duration / max_frames)
    log(f"视频时长 {duration:.1f}s，每 {interval:.1f}s 提取一帧")

    output_pattern = os.path.join(temp_dir, "frame_%04d.jpg")
    cmd = [
        "ffmpeg", "-i", path, "-vf",
        f"fps=1/{interval},scale=iw*min(1080/iw,1080/ih):ih*min(1080/iw,1080/ih)",
        "-q:v", "5", "-y", output_pattern,
    ]
    subprocess.run(cmd, capture_output=True, timeout=300)

    frames = sorted(Path(temp_dir).glob("frame_*.jpg"))
    frames_selected = frames[:max_frames]
    log(f"提取了 {len(frames_selected)} 帧")

    result = []
    for i, fp in enumerate(frames_selected):
        ts = i * interval
        result.append({
            "path": str(fp),
            "timestamp": round(ts, 2),
            "timestamp_formatted": f"{int(ts//60):02d}:{int(ts%60):02d}",
        })
    return result


def _extract_frames_scene(path: str, max_frames: int, temp_dir: str) -> list[dict]:
    output_pattern = os.path.join(temp_dir, "scene_%04d.jpg")
    cmd = [
        "ffmpeg", "-i", path, "-vf",
        f"select='gt(scene,0.3)',scale=iw*min(1080/iw,1080/ih):ih*min(1080/iw,1080/ih)",
        "-vsync", "vfr", "-q:v", "5", "-y", output_pattern,
    ]
    subprocess.run(cmd, capture_output=True, timeout=300)

    frames = sorted(Path(temp_dir).glob("scene_*.jpg"))
    frames_selected = frames[:max_frames]
    log(f"场景检测提取了 {len(frames_selected)} 帧（上限 {max_frames}）")

    result = []
    for fp in frames_selected:
        match = re.search(r"_(\d+)\.jpg$", fp.name)
        ts = 0.0
        if match:
            idx = int(match.group(1))
            ts = round(idx / 30, 2) if idx else 0.0
        result.append({
            "path": str(fp),
            "timestamp": ts,
            "timestamp_formatted": f"{int(ts//60):02d}:{int(ts%60):02d}",
        })
    return result


# ---------------------------------------------------------------------------
# MiniMax-M3 API call
# ---------------------------------------------------------------------------

def call_minimax_m3(
    api_key: str,
    messages: list[dict],
    prompt: str = "",
    max_tokens: int = 4096,
) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }

    log(f"调用 MiniMax-M3 模型...")
    import requests
    start = time.time()
    try:
        resp = requests.post(
            f"{API_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        elapsed = round(time.time() - start, 2)
        log(f"API 响应耗时 {elapsed}s，状态码 {resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {
            "success": True,
            "content": content,
            "usage": usage,
            "elapsed_seconds": elapsed,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Analysis dispatcher
# ---------------------------------------------------------------------------

def analyze_images(paths: list[str], prompt: str) -> dict:
    content_blocks = [{"type": "text", "text": prompt}]
    files_info = []
    for p in paths:
        content_blocks.append(_image_content_block(p))
        files_info.append({"path": p, "type": "image"})

    messages = [
        {
            "role": "user",
            "content": content_blocks,
        }
    ]

    api_key = _get_api_key()
    result = call_minimax_m3(api_key, messages, prompt)

    if not result["success"]:
        return {"success": False, "error": result["error"]}

    raw = result["content"]
    parsed = _try_parse_json(raw)
    return {
        "success": True,
        "model": MODEL_NAME,
        "provider": PROVIDER_NAME,
        "media_type": "image",
        "files": files_info,
        "analysis": parsed if isinstance(parsed, dict) else {"text": raw},
        "usage": result.get("usage"),
        "elapsed_seconds": result.get("elapsed_seconds"),
    }


def analyze_video(path: str, prompt: str, max_frames: int, mode: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="minimax-m3-") as tmpdir:
        if mode == "scene":
            frames = _extract_frames_scene(path, max_frames, tmpdir)
        else:
            frames = _extract_frames_interval(path, max_frames, tmpdir)

        if not frames:
            return {"success": False, "error": "视频帧提取失败或视频为空"}

        content_blocks = [
            {
                "type": "text",
                "text": (
                    f"{prompt}\n\n"
                    f"以下是视频 '{os.path.basename(path)}' 的 {len(frames)} 个关键帧，"
                    f"按时间顺序排列。请分析每个帧的内容、场景变化和整体叙事。"
                ),
            }
        ]
        for f in frames:
            content_blocks.append(_image_content_block(f["path"]))

        messages = [{"role": "user", "content": content_blocks}]

        api_key = _get_api_key()
        result = call_minimax_m3(api_key, messages, prompt)

        if not result["success"]:
            return {"success": False, "error": result["error"]}

        raw = result["content"]
        parsed = _try_parse_json(raw)
        return {
            "success": True,
            "model": MODEL_NAME,
            "provider": PROVIDER_NAME,
            "media_type": "video",
            "file": {"path": path, "duration": _get_video_duration(path)},
            "frames": frames,
            "analysis": parsed if isinstance(parsed, dict) else {"text": raw},
            "usage": result.get("usage"),
            "elapsed_seconds": result.get("elapsed_seconds"),
        }


def _try_parse_json(text: str) -> dict | str:
    text = text.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    brace_start = text.find("{")
    if brace_start != -1:
        text = text[brace_start:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_prompt(paths: list[str], user_prompt: str) -> str:
    images = [p for p in paths if _is_image(p)]
    videos = [p for p in paths if _is_video(p)]
    parts = []

    if user_prompt:
        parts.append(user_prompt)
        # 自定义 prompt 已自带输出格式要求时，不再追加默认 JSON 格式，
        # 避免两个冲突的输出规范导致模型随机二选一（2026-08-28 setup-video 管线踩坑根因）。
        if "JSON" not in user_prompt and "json" not in user_prompt:
            parts.append('请以结构化JSON格式输出。')
    else:
        if images and not videos:
            parts.append("请分析这张图片的内容，包括：主体对象、场景环境、构图、色彩、文字内容（如有）。以结构化JSON格式输出。")
        elif videos and not images:
            parts.append("请分析这个视频的内容，包括：场景描述、时间线上的变化、关键视觉元素。以结构化JSON格式输出。")
        elif images and videos:
            parts.append("请分析这些图片和视频的内容，描述它们之间的关系和整体叙事。以结构化JSON格式输出。")
        parts.append(
            "请严格按照以下JSON格式输出（不要使用<think>标签，不要使用markdown代码块，直接输出纯JSON）：\n"
            '{"summary": "总体描述", '
            '"scenes": [{"timestamp": "时间戳或序号", "description": "描述", '
            '"elements": ["关键元素1", "关键元素2"]}], '
            '"details": {"composition": "构图分析", "colors": "色彩分析", '
            '"text_content": "文字内容（如有）", "objects": ["检测到的对象列表"]}}'
        )
    return "\n".join(parts)


def main():
    global _quiet
    parser = argparse.ArgumentParser(description="使用 MiniMax-M3 分析图片和视频")
    parser.add_argument("paths", nargs="+", help="图片或视频文件路径")
    parser.add_argument("-p", "--prompt", default="", help="自定义分析提示词")
    parser.add_argument("--max-frames", type=int, default=DEFAULT_MAX_FRAMES, help="视频最大帧数")
    parser.add_argument("--interval", action="store_true", help="视频帧使用等间隔模式（默认场景检测）")
    parser.add_argument("-o", "--output", help="输出到文件")
    parser.add_argument("-q", "--quiet", action="store_true", help="静默模式")
    args = parser.parse_args()

    if args.quiet:
        _quiet = True

    # Validate paths
    valid_paths = []
    for p in args.paths:
        if not os.path.isfile(p):
            die(f"文件不存在: {p}")
        if not _is_image(p) and not _is_video(p):
            die(f"不支持的文件格式（仅支持图片和视频）: {p}")
        valid_paths.append(p)

    images = [p for p in valid_paths if _is_image(p)]
    videos = [p for p in valid_paths if _is_video(p)]

    prompt = build_prompt(valid_paths, args.prompt)

    results = {}

    if images:
        log(f"分析 {len(images)} 张图片...")
        results["image"] = analyze_images(images, prompt)

    if videos:
        for vp in videos:
            log(f"分析视频: {vp}")
            mode = "scene" if not args.interval else "interval"
            results["video"] = analyze_video(vp, prompt, args.max_frames, mode)

    output = results.get("image") or results.get("video") or {"success": False, "error": "没有可分析的文件"}
    output_json = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        log(f"结果已写入: {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
