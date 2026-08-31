#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_cover.py — 自动生成 B 站视频封面（流程化，供 animated-explainer 等管线 publish 阶段调用）

默认模式（16:9 DSH 风格）:
  python bin/make_cover.py --project <name> \
      --series "DSH 插件系统" \
      --topic "组合模型" \
      --episode "第 1 节" \
      --title-main "改能力" \
      --title-accent "改组合" \
      --duration "3 分钟" \
      --subtitle "讲透 DSH 插件组合模型" \
      [--plugs "Profile,Bundle,Patch"] \
      [--ring "能力"]

  产出:
    projects/<name>/hyperframes-cover/        封面组合工作区
    projects/<name>/renders/cover_design.png  最终封面（1920x1080）

  流程:
    1. 从 templates/hyperframes-cover/index.template.html 渲染参数
    2. 写入 projects/<name>/hyperframes-cover/index.html
    3. npx hyperframes snapshot --at 1.8 捕获封面帧
    4. 复制到 projects/<name>/renders/cover_design.png
    5. （调用方）用视觉模型审封面后，作为 export_bundle 的 thumbnail_path

新模式 --frame-mode（9:16 原视频帧底图，用于 auto-dub 9:16 封面）:
  python bin/make_cover.py --frame-mode \
      --project <name> \
      --title "中文标题" \
      --channel "原频道" \
      [--frame-url https://i.ytimg.com/vi/.../maxresdefault.jpg] \
      [--video-url https://www.youtube.com/watch?v=...] \
      [--frame-source {thumbnail|auto|seek_time}] \
      [--seek-time 5.0] \
      [--cover-style {vlogger|frugal_red|hardcore_dark}]

  底图来源（按 --frame-source）:
    thumbnail   默认。--video-url 给定时用 yt-dlp --get-thumbnail 拿缩略图 URL（最稳，不下载视频）
    auto        thumbnail 失败时 fallback 到 ffmpeg 抽首帧
    seek_time   用 ffmpeg 在 --seek-time 秒处抽帧（需要本地视频路径）

  产出:
    projects/<name>/source-frame-cover/         工作区
    projects/<name>/renders/cover_9_16.png      最终封面（1080x1920）

向后兼容:
  - 未传 --frame-mode 时，旧行为完全不变（16:9 渲染 + cover_design.png）
"""
import argparse
import json
import shutil
import subprocess
import sys
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "templates" / "hyperframes-cover" / "index.template.html"
TEMPLATE_LIGHT = REPO / "templates" / "hyperframes-cover" / "index.light.template.html"

# 9:16 原视频帧封面模板（auto-dub 新增，向后兼容 cover_vertical.html 的视觉风格但底图改为外部传入）
SOURCE_FRAME_TEMPLATE = REPO / "apps" / "auto-dub" / "templates" / "covers" / "source-frame" / "cover.html"


def render(template_text: str, params: dict) -> str:
    """模板变量替换（{{KEY}} -> value）。"""
    out = template_text
    for key, val in params.items():
        out = out.replace("{{" + key + "}}", str(val))
    return out


def _npx_cmd() -> str:
    return "npx.cmd" if os.name == "nt" else "npx"


def resolve_frame_url(args) -> str:
    """根据 --frame-url / --video-url / --frame-source 解析底图 URL。

    优先级:
      1. --frame-url 显式给定 → 直接返回
      2. --video-url + frame-source=thumbnail → yt-dlp --get-thumbnail（最稳）
      3. --video-url + frame-source=auto → 先 thumbnail，失败则 ffmpeg 抽首帧
      4. --video-url + frame-source=seek_time → ffmpeg 在 --seek-time 秒抽帧到本地 tmp，file:// 返回
    """
    if args.frame_url:
        return args.frame_url

    if not args.video_url:
        raise SystemExit(
            "ERROR: --frame-mode 需要 --frame-url 或 --video-url 二选一"
        )

    source = args.frame_source

    if source in ("thumbnail", "auto"):
        try:
            proc = subprocess.run(
                ["yt-dlp", "--get-thumbnail", "--no-warnings", args.video_url],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                url = proc.stdout.strip().splitlines()[0]
                print(f"[make_cover] thumbnail URL resolved: {url}")
                return url
        except FileNotFoundError:
            print("      ⚠️ yt-dlp 未安装，无法取 thumbnail")
        except Exception as e:
            print(f"      ⚠️ yt-dlp 取 thumbnail 失败: {e}")

        if source == "auto":
            print("      ↘️ thumbnail 失败，fallback 到 ffmpeg 抽首帧")
            return _extract_frame_with_ffmpeg(args.video_url, seek_seconds=0.0)
        else:
            raise SystemExit(
                f"ERROR: 无法从 {args.video_url} 取得 thumbnail URL（可改用 --frame-source auto 或 --frame-url 显式指定）"
            )

    if source == "seek_time":
        return _extract_frame_with_ffmpeg(args.video_url, seek_seconds=args.seek_time)

    raise SystemExit(f"ERROR: 未知 --frame-source: {source}")


def _extract_frame_with_ffmpeg(video_url: str, seek_seconds: float) -> str:
    """ffmpeg 从视频（本地路径或可下载 URL）抽帧，输出到 tmp 文件并返回 file:// URL。

    注：video_url 是本地路径时直接读；是 URL 时 ffmpeg 支持 http(s) 输入协议。
    """
    tmp_dir = REPO / "projects" / "_tmp_cover_frames"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_jpg = tmp_dir / f"frame_at_{seek_seconds:.1f}s.jpg"
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seek_seconds:.2f}",
        "-i", video_url,
        "-frames:v", "1",
        "-q:v", "2",
        str(out_jpg),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0 or not out_jpg.exists():
        raise SystemExit(
            f"ERROR: ffmpeg 抽帧失败 (seek={seek_seconds}s): {proc.stderr[:300]}"
        )
    file_url = out_jpg.resolve().as_uri()
    print(f"[make_cover] ffmpeg extracted frame: {file_url}")
    return file_url


def render_source_frame(args) -> int:
    """9:16 原视频帧封面流程（--frame-mode）。"""
    if not SOURCE_FRAME_TEMPLATE.exists():
        print(f"ERROR: source-frame template not found: {SOURCE_FRAME_TEMPLATE}")
        return 1

    frame_url = resolve_frame_url(args)

    badges = [b.strip() for b in (args.author_badges or "").split(",") if b.strip()]
    variables = {
        "title": args.title or "视频标题",
        "channel": args.channel or "",
        "frame_url": frame_url,
        "cover_style": args.cover_style,
        "author_name": args.author_name or "",
        "author_title": args.author_title or "",
        "author_badges": badges,
    }

    cover_dir = REPO / "projects" / args.project / "source-frame-cover"
    cover_dir.mkdir(parents=True, exist_ok=True)
    index_path = cover_dir / "index.html"
    shutil.copy2(SOURCE_FRAME_TEMPLATE, index_path)
    var_json = json.dumps(variables, ensure_ascii=False)
    print(f"[make_cover] source-frame rendered -> {index_path}")
    print(f"[make_cover] frame source = {args.frame_source}, frame_url = {frame_url[:80]}...")

    tmp_mp4 = cover_dir / "out.mp4"
    proc = subprocess.run(
        [_npx_cmd(), "hyperframes", "render", str(cover_dir),
         "--output", str(tmp_mp4),
         "--quality", "high",
         "--variables", var_json],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        print(f"ERROR: hyperframes render failed:\n{proc.stdout}\n{proc.stderr}")
        return 1
    if not tmp_mp4.exists():
        print(f"ERROR: hyperframes render did not produce {tmp_mp4}\nstdout={proc.stdout[:500]}")
        return 1

    out_png = Path(args.out) if args.out else REPO / "projects" / args.project / "renders" / "cover_9_16.png"
    out_png.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_proc = subprocess.run([
        "ffmpeg", "-y", "-i", str(tmp_mp4), "-vframes", "1",
        "-q:v", "1", str(out_png),
    ], capture_output=True, text=True, encoding="utf-8")
    if ffmpeg_proc.returncode != 0 or not out_png.exists():
        print(f"ERROR: ffmpeg extract frame failed: {ffmpeg_proc.stderr[:300]}")
        return 1

    print(f"[make_cover] source-frame cover -> {out_png}  (1080x1920)")
    print("[make_cover] NEXT: 用视觉模型审封面（文字清晰/帧不被裁/无版权字），通过后作为 auto-dub 9:16 thumbnail_path")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a designed video cover via HyperFrames")
    ap.add_argument("--project", required=True, help="Project name, e.g. dsh-pilot-short")

    # ========== --frame-mode 模式专属参数 ==========
    ap.add_argument("--frame-mode", action="store_true",
                    help="启用 9:16 原视频帧封面模式（auto-dub 竖屏封面），"
                         "使用 apps/auto-dub/templates/covers/source-frame/cover.html 模板，"
                         "输出 cover_9_16.png（1080x1920）。默认模式完全不受影响。")
    ap.add_argument("--frame-url", default=None,
                    help="[--frame-mode] 直接给定底图 URL（http(s) 或 file://）。最稳定的路径，跳过 yt-dlp。")
    ap.add_argument("--video-url", default=None,
                    help="[--frame-mode] 视频 URL（YouTube 等），与 --frame-source 配合抽取底图")
    ap.add_argument("--frame-source", choices=["thumbnail", "auto", "seek_time"], default="thumbnail",
                    help="[--frame-mode] 底图来源: thumbnail=YouTube 缩略图(默认, 不下载视频), "
                         "auto=thumbnail 失败时 ffmpeg 抽首帧, seek_time=ffmpeg 在 --seek-time 秒抽帧")
    ap.add_argument("--seek-time", type=float, default=0.0,
                    help="[--frame-mode] --frame-source=seek_time 时的抽帧时刻(秒)")
    ap.add_argument("--title", default=None,
                    help="[--frame-mode] 封面中文大字（支持 \\n 分行）")
    ap.add_argument("--channel", default=None,
                    help="[--frame-mode] 原频道名")
    ap.add_argument("--cover-style", choices=["vlogger", "frugal_red", "hardcore_dark"], default="vlogger",
                    help="[--frame-mode] 主题风格 (vlogger/frugal_red/hardcore_dark)")
    ap.add_argument("--author-name", default=None,
                    help="[--frame-mode] 原视频作者名")
    ap.add_argument("--author-title", default=None,
                    help="[--frame-mode] 作者头衔/角色")
    ap.add_argument("--author-badges", default=None,
                    help="[--frame-mode] 标签列表，逗号分隔，如 'AI,科普,中文配音'")

    # ========== 默认 16:9 DSH 风格封面参数（保持向后兼容） ==========
    ap.add_argument("--series", default="DSH 插件系统", help="Series eyebrow text")
    ap.add_argument("--topic", default="组合模型", help="Series topic (bottom bar)")
    ap.add_argument("--episode", default="第 1 节", help="Episode label (bottom bar)")
    ap.add_argument("--title-main", required=False, default=None, help="Main title part before '=' (white)")
    ap.add_argument("--title-accent", required=False, default=None, help="Main title accent part after '=' (gradient purple)")
    ap.add_argument("--duration", default="3 分钟", help="Duration label, e.g. '3 分钟'")
    ap.add_argument("--subtitle", required=False, default=None, help="Subtitle text after duration")
    ap.add_argument("--plugs", default="Profile,Bundle,Patch", help="Comma-separated 3 plug labels")
    ap.add_argument("--ring", default="能力", help="Ring center label")
    ap.add_argument("--light", action="store_true", help="Use the light minimalist 详解版 cover template (浅底单红 + 3 plugs + 能力环), matching the deep-dive episodes' visual", )
    ap.add_argument("--out", default=None, help="Output cover PNG path (default: projects/<name>/renders/cover_design.png)")
    args = ap.parse_args()

    # ============== 分流：--frame-mode 走新流程 ==============
    if args.frame_mode:
        if not args.title:
            print("ERROR: --frame-mode 需要 --title")
            return 1
        return render_source_frame(args)

    # ============== 默认 16:9 流程（向后兼容） ==============
    if not args.title_main or not args.title_accent or not args.subtitle:
        print("ERROR: 默认模式需要 --title-main / --title-accent / --subtitle")
        return 1

    template_path = TEMPLATE_LIGHT if args.light else TEMPLATE
    if not template_path.exists():
        print(f"ERROR: template not found: {template_path}")
        return 1

    plugs = [p.strip() for p in args.plugs.split(",")]
    while len(plugs) < 3:
        plugs.append("")
    params = {
        "SERIES_NAME": args.series,
        "TITLE_FULL": f"{args.title_main} = {args.title_accent}",
        "TITLE_MAIN": args.title_main,
        "TITLE_ACCENT": args.title_accent,
        "DURATION_LABEL": args.duration,
        "SUBTITLE": args.subtitle,
        "PLUG_1": plugs[0],
        "PLUG_2": plugs[1],
        "PLUG_3": plugs[2],
        "RING_LABEL": args.ring,
        "SERIES_TOPIC": args.topic,
        "EPISODE_LABEL": args.episode,
    }

    cover_dir = REPO / "projects" / args.project / "hyperframes-cover"
    cover_dir.mkdir(parents=True, exist_ok=True)
    index_path = cover_dir / "index.html"
    index_path.write_text(render(template_path.read_text(encoding="utf-8"), params), encoding="utf-8")
    print(f"[make_cover] rendered -> {index_path}")

    # 清理旧 snapshot，跑捕获
    snap_dir = cover_dir / "snapshots"
    if snap_dir.exists():
        shutil.rmtree(snap_dir)
    proc = subprocess.run(
        [_npx_cmd(), "hyperframes", "snapshot", "--at", "1.8"],
        cwd=str(cover_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        print(f"ERROR: hyperframes snapshot failed:\n{proc.stdout}\n{proc.stderr}")
        return 1

    frames = sorted(snap_dir.glob("frame-*.png")) if snap_dir.exists() else []
    if not frames:
        print("ERROR: no snapshot frame produced")
        return 1

    out_path = Path(args.out) if args.out else REPO / "projects" / args.project / "renders" / "cover_design.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(frames[0], out_path)
    print(f"[make_cover] cover -> {out_path}")
    print("[make_cover] NEXT: 用视觉模型审封面（文字清晰/无裁切/吸睛），通过后作为 export_bundle thumbnail_path")
    return 0


if __name__ == "__main__":
    sys.exit(main())
