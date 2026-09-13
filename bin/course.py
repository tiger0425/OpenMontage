#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VOX 科技/硬核课程自动化生产独立管线 CLI（bin/course.py）

规范来源：
  apps/vox-course/specs/LESSONS.md               (实战经验与四大铁律)
  apps/vox-course/specs/course_episode.schema.json (单集契约)
  apps/vox-course/specs/script-spec.md            (剧本规范与去AI化)
  apps/vox-course/specs/visual-spec.md            (视觉组件与动效)
  apps/vox-course/specs/package-spec.md           (成品包规范)
  apps/vox-course/template/generate_composition.py (HyperFrames 模板生成器)

核心铁律：
  1. 文案必须严格去AI化：短句（≤25字+300ms气口），年份数字全汉字化（二零二五年、三百亿美金、百分之九十五）。
  2. IndexTTS2 纯净克隆：版本 2.5，纯净通道（use_emo_text=False, emo_vector=None），稳态参数（0.65/0.75/30/5.0）。
  3. 音画卡片 100% 咬合：画面大字、终端日志、印章与台词核心词一字不差对齐。
  4. 高对比度同步字幕条 + 片尾 4.0 秒视觉与音乐优雅留白。

用法：
  python bin/course.py new <topic> [--script-file <path>]    # 轻：创建课程项目与资产结构
  python bin/course.py script <id>                          # 轻：生成/转换去AI化剧本，停在闸门
  python bin/course.py approve-script <id>                  # 轻：校验合法性并放行
  python bin/course.py synth <id> [--json]                  # 重：IndexTTS2 纯净克隆逐幕配音与字幕对齐
  python bin/course.py compose <id>                         # 轻：调用模板生成器装配 HyperFrames
  python bin/course.py render <id> [--json] [--4k]          # 重：渲染 1080P FHD，可选 4K HEVC 压制
  python bin/course.py package <id>                         # 轻：生成最终发布成品包
  python bin/course.py run <topic> [--script-file <path>]   # 轻：new + script，停在脚本闸门
  python bin/course.py run-heavy <id> [--json] [--4k]       # 重：synth + compose + render + package
  python bin/course.py status                               # 查看所有课程状态
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OMO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OMO_ROOT))

DB_PATH = OMO_ROOT / "projects" / "course" / "tracking.db"
PROJECTS_ROOT = OMO_ROOT / "projects"
GEN_COMPOSE = OMO_ROOT / "apps" / "vox-course" / "template" / "generate_composition.py"
SCHEMA_PATH = OMO_ROOT / "apps" / "vox-course" / "specs" / "course_episode.schema.json"
VOX_BG_LIB = OMO_ROOT / "background_library" / "vox"

STATUS_FLOW = [
    "pending", "scripting", "awaiting_script_review", "script_approved",
    "tts", "tts_done", "composing", "composed", "rendering", "rendered",
    "packaged", "published"
]

DEFAULT_VOICE_REF = "D:/index-tts/my_voice.wav"


# ---------------------------------------------------------------- helpers
def emit_json(obj: dict):
    print(json.dumps(obj, ensure_ascii=False))


def sh(cmd, cwd=None, env=None, timeout=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(
        cmd, cwd=cwd, env=e, timeout=timeout,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace"
    )


def run_cmd(cmd, cwd=None, env=None, timeout=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, env=e, timeout=timeout)


def get_wav_duration(p: Path) -> float:
    try:
        with wave.open(str(p), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        return 20.0


# ---------------------------------------------------------------- DB
def db_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.execute("""CREATE TABLE IF NOT EXISTS courses(
        course_id TEXT PRIMARY KEY, topic TEXT, title TEXT, status TEXT,
        project_dir TEXT, created_at TEXT, updated_at TEXT)""")
    return c


def set_status(course_id: str, status: str):
    c = db_conn()
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    c.execute("UPDATE courses SET status=?, updated_at=? WHERE course_id=?", (status, now, course_id))
    c.commit()
    c.close()


def get_course(course_id: str):
    c = db_conn()
    row = c.execute("SELECT * FROM courses WHERE course_id=?", (course_id,)).fetchone()
    c.close()
    if not row:
        return None
    cols = ["course_id", "topic", "title", "status", "project_dir", "created_at", "updated_at"]
    return dict(zip(cols, row))


def list_courses():
    c = db_conn()
    rows = c.execute("SELECT course_id, topic, status, updated_at FROM courses ORDER BY created_at DESC").fetchall()
    c.close()
    return rows


def sanitize_slug(name: str) -> str:
    s = re.sub(r"[^\w\-_]+", "-", name.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:40] or "course"


# ---------------------------------------------------------------- Stages

def stage_new(topic: str, args):
    """初始化课程项目目录结构与共享资产"""
    slug = sanitize_slug(topic)
    course_id = f"course-{slug}"
    proj = PROJECTS_ROOT / course_id
    if proj.exists() and get_course(course_id):
        return {"ok": True, "course_id": course_id, "project_dir": str(proj), "note": "项目已存在"}

    (proj / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "images").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "music").mkdir(parents=True, exist_ok=True)
    (proj / "assets" / "sfx").mkdir(parents=True, exist_ok=True)
    (proj / "artifacts").mkdir(parents=True, exist_ok=True)
    (proj / "hyperframes" / "assets").mkdir(parents=True, exist_ok=True)
    (proj / "renders").mkdir(parents=True, exist_ok=True)
    (proj / "package").mkdir(parents=True, exist_ok=True)

    # 复制公共音效与 BGM
    if VOX_BG_LIB.exists():
        for sfx_f in (VOX_BG_LIB / "sfx").glob("*.wav"):
            shutil.copy2(sfx_f, proj / "assets" / "sfx" / sfx_f.name)
        bgm_lib = VOX_BG_LIB / "music" / "bgm_tech.mp3"
        if bgm_lib.exists():
            shutil.copy2(bgm_lib, proj / "assets" / "music" / "bgm_tech.mp3")
        gsap_lib = VOX_BG_LIB / "gsap.min.js"
        if gsap_lib.exists():
            shutil.copy2(gsap_lib, proj / "assets" / "gsap.min.js")

    # 如果提供了输入文案文件，保存为原始材料
    if hasattr(args, "script_file") and args.script_file:
        src_script = Path(args.script_file)
        if src_script.exists():
            shutil.copy2(src_script, proj / "artifacts" / "raw_course.md")

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    c = db_conn()
    c.execute(
        "INSERT OR REPLACE INTO courses VALUES(?,?,?,?,?,?,?)",
        (course_id, topic, topic, "pending", str(proj), now, now)
    )
    c.commit()
    c.close()

    return {"ok": True, "course_id": course_id, "project_dir": str(proj)}


def stage_script(course_id: str, args):
    """生成或准备去AI化剧本，输出 course_episode.json 并停在脚本人审闸门"""
    v = get_course(course_id)
    if not v:
        return {"ok": False, "error": f"未找到课程项目: {course_id}"}

    proj = Path(v["project_dir"])
    ep_json_path = proj / "artifacts" / "course_episode.json"

    set_status(course_id, "scripting")

    # 如果用户没有预置 course_episode.json，自动生成一份标准的 7 幕模板
    if not ep_json_path.exists():
        topic = v["topic"]
        mock_episode = {
            "course_id": course_id,
            "episode_index": 1,
            "title": f"{topic} · 核心深度解析",
            "title_hook": f"绝大多数人都搞错了！{topic} 的真正底层秘密",
            "description": f"深度拆解 {topic} 的技术原理与生产级落地实践。",
            "voice_config": {
                "voice_ref": DEFAULT_VOICE_REF,
                "model_version": "2.5",
                "use_emo_text": False,
                "emo_vector": None,
                "temperature": 0.65,
                "top_p": 0.75,
                "top_k": 30,
                "repetition_penalty": 5.0
            },
            "scenes": [
                {
                    "id": "s01",
                    "topic_tag": "REALITY CHECK",
                    "narration": f"很多团队以为只要堆算力和参数就能解决问题，但二零二五年麻省理工的重磅报告扯下了遮羞布。全球企业砸了三百亿美金，结果百分之九十五的项目回报率干脆是零！",
                    "audio_file": "assets/audio/sec_01.wav",
                    "display": {
                        "headline": {"zh": "撕下行业遮羞布", "en": "REALITY CHECK"},
                        "cards": [
                            {
                                "title": "MIT 2025 调查报告",
                                "badge": "AUDIT",
                                "list_items": [
                                    "全球投入：$30,000,000,000 (三百亿美金)",
                                    "惨淡现实：95% 项目回报率为零",
                                    "核心问题：连第 3 轮上下文都撑不过去"
                                ]
                            }
                        ],
                        "stamps": [{"text": "95% 回报为零", "color": "red", "rotate": -10}]
                    }
                },
                {
                    "id": "s02",
                    "topic_tag": "THE CORE",
                    "narration": f"说白了，大模型只是个预测概率的引擎，它自己根本没有系统权限，读不了工程目录，更跑不了单测。真正干脏活累活的，是套在模型外面的装具底盘！",
                    "audio_file": "assets/audio/sec_02.wav",
                    "display": {
                        "headline": {"zh": "模型只是引擎，底盘才是核心", "en": "ENGINE VS HARNESS"},
                        "cards": [
                            {
                                "title": "HARNESS 装具底盘",
                                "badge": "PRODUCTION RUNTIME",
                                "list_items": [
                                    "沙箱隔离 (Sandbox)",
                                    "工具权限代理 (Tool Broker)",
                                    "工程单测执行 (Test Runner)"
                                ]
                            }
                        ],
                        "stamps": [{"text": "真正干脏活的底盘", "color": "orange", "rotate": -6}]
                    }
                },
                {
                    "id": "s03",
                    "topic_tag": "CATASTROPHE",
                    "narration": f"来看看传统装具是怎么翻车的。像早期助手直接把上下文当水桶用，满了就死命压缩，这就叫上下文腐烂。跑了两个小时，AI 就在自己的压缩垃圾里反复兜圈，修一个 bug 引出五个新 bug，彻底脑死亡！",
                    "audio_file": "assets/audio/sec_03.wav",
                    "display": {
                        "headline": {"zh": "传统装具翻车实录", "en": "CONTEXT ROT"},
                        "cards": [
                            {
                                "title": "上下文死循环崩溃",
                                "badge": "FAILURE ANALYSIS",
                                "list_items": [
                                    "拿幻觉概括上一轮日志",
                                    "核心架构约束被彻底抹平",
                                    "修 1 个 bug 引出 5 个新 bug"
                                ]
                            }
                        ],
                        "stamps": [{"text": "彻底脑死亡", "color": "red", "rotate": -8}]
                    }
                },
                {
                    "id": "s04",
                    "topic_tag": "RECONSTRUCTION",
                    "narration": f"但真正聪明的工程底盘，完全换了个打法。它在后台挂了一个常驻的 IPython 终端。利用前缀缓存，瞬间跳过了一万八千多个重复输入的 Token！生成的几十兆调试数据留在内存池，头脑始终清清爽爽！",
                    "audio_file": "assets/audio/sec_04.wav",
                    "display": {
                        "headline": {"zh": "常驻终端与前缀缓存破局", "en": "IPYTHON SANDBOX"},
                        "terminal": {
                            "title": "IPython Sandbox Runtime",
                            "logs": [
                                "$ agent-harness --task '重构核心模块'",
                                "[SYSTEM] 挂载常驻 IPython 终端成功",
                                "[CACHE HIT] 瞬间跳过 18,432 个重复 Token",
                                "[STATUS] 跑上一整天，头脑清清爽爽"
                            ]
                        },
                        "stamps": [{"text": "头脑清清爽爽", "color": "green", "rotate": -5}]
                    }
                },
                {
                    "id": "s05",
                    "topic_tag": "MANIFESTO & HOOK",
                    "narration": f"别再盲目迷信模型参数了。在二零二六年，装具的工程质量，才是区分玩具和工业工具的唯一标准！那么生产级底盘到底怎么写？下一集咱们直接撕开底层沙箱，带你从零手搓一套工业级执行底盘！赶紧关注我，咱们下期见！",
                    "audio_file": "assets/audio/sec_05.wav",
                    "display": {
                        "headline": {"zh": "底盘决定上限，工程主宰未来", "en": "MANIFESTO"},
                        "cards": [
                            {
                                "title": "2026 AI AGENT 工程宣言",
                                "badge": "FINAL VERDICT",
                                "list_items": [
                                    "装具质量是区分玩具与工具的唯一标准",
                                    "底盘决定上限，工程主宰未来"
                                ]
                            }
                        ],
                        "stamps": [{"text": "HARNESS > MODEL", "color": "green", "rotate": -3}]
                    }
                }
            ],
            "next_episode_hook": {
                "headline": "从零手搓生产级执行沙箱与底盘",
                "narration": "下一集带你直接撕开底层沙箱，实战状态外挂与智能缓存！",
                "stamp": "EPISODE 02: 敬请期待"
            }
        }
        with open(ep_json_path, "w", encoding="utf-8") as f:
            json.dump(mock_episode, f, ensure_ascii=False, indent=2)

    set_status(course_id, "awaiting_script_review")
    return {
        "ok": True,
        "course_id": course_id,
        "episode_json": str(ep_json_path),
        "next": "请人工审查或优化 artifacts/course_episode.json 中的台词与卡片词汇（确保100%咬合并严格去AI化），然后运行: python bin/course.py approve-script " + course_id
    }


def stage_approve_script(course_id: str, args):
    """校验剧本合法性（去AI口播规范、年份汉字化、音画词汇咬合、下集钩子）"""
    v = get_course(course_id)
    if not v:
        return {"ok": False, "error": f"未找到课程项目: {course_id}"}

    proj = Path(v["project_dir"])
    ep_json_path = proj / "artifacts" / "course_episode.json"
    if not ep_json_path.exists():
        return {"ok": False, "error": "缺 course_episode.json，请先运行 script"}

    with open(ep_json_path, "r", encoding="utf-8") as f:
        d = json.load(f)

    scenes = d.get("scenes", [])
    if not scenes or len(scenes) < 3:
        return {"ok": False, "error": "scenes 数量不足（至少需 3 幕）"}

    problems = []

    # 规则检查
    for i, sc in enumerate(scenes, 1):
        narr = sc.get("narration", "")
        if not narr:
            problems.append(f"幕 {i} ({sc.get('id')}) 缺 narration")

        # 去除 <字|读音> 标注以进行纯文本检查
        clean_narr = re.sub(r"<([^|>]+)\|[^>]+>", r"\1", narr)

        # 检查是否包含未汉字化的年份（如 2025、2026）与阿拉伯数字百分比/大数
        year_matches = re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", clean_narr)
        if year_matches:
            problems.append(f"幕 {i} 台词包含阿拉伯数字年份: {year_matches}，请必须转换为纯汉字（如'二零二五年'）")

        pct_matches = re.findall(r"(?<!\d)\d+%", clean_narr)
        if pct_matches:
            problems.append(f"幕 {i} 台词包含百分比符号: {pct_matches}，请转换为纯汉字（如'百分之九十五'）")

        # 检查长句是否未粉碎（单句无标点连续超过35字）
        clauses = re.split(r"[，。！？；\n]", clean_narr)
        for cl in clauses:
            if len(cl.strip()) > 35:
                problems.append(f"幕 {i} 存在单句超长语句（{len(cl.strip())}字）: '{cl.strip()[:20]}...'，请增加逗号呼吸气口")

        disp = sc.get("display", {})
        if not disp:
            problems.append(f"幕 {i} 缺 display 视觉块")

    hook = d.get("next_episode_hook")
    if not hook or not hook.get("headline"):
        problems.append("最后一幕缺 next_episode_hook（必须有下集预告与钩子）")

    if problems:
        return {"ok": False, "error": "剧本去AI化校验未通过", "problems": problems}

    set_status(course_id, "script_approved")
    return {"ok": True, "course_id": course_id, "scenes": len(scenes), "status": "script_approved"}


def auto_align_subtitles(narration: str, total_dur: float) -> list:
    """按标点智能切分句子并按字数比例分配起止时间戳"""
    # 切分句子并保留有效文字
    raw_parts = re.split(r"([，。！？；\n]+)", narration)
    chunks = []
    current_clause = ""
    for p in raw_parts:
        current_clause += p
        if any(punct in p for punct in "，。！？；\n"):
            c_clean = current_clause.strip()
            if c_clean:
                chunks.append(c_clean)
            current_clause = ""
    if current_clause.strip():
        chunks.append(current_clause.strip())

    if not chunks:
        return [{"start": 0.2, "end": max(1.0, total_dur - 0.5), "text": narration, "hl": False}]

    total_chars = sum(len(c) for c in chunks)
    subs = []
    curr_t = 0.2
    # 分配持续时间（留 0.3s 尾部）
    usable_dur = max(total_dur - 0.5, 1.0)

    for c in chunks:
        ratio = len(c) / float(total_chars)
        dur = max(1.2, usable_dur * ratio)
        start_t = round(curr_t, 2)
        end_t = round(min(total_dur - 0.2, curr_t + dur), 2)
        # 高亮技术关键词
        hl = any(w in c for w in ["零", "Harness", "装具", "底盘", "腐烂", "脑死亡", "前缀缓存", "清清爽爽", "十六分", "复印机", "烧电费"])
        subs.append({
            "start": start_t,
            "end": end_t,
            "text": c,
            "hl": hl
        })
        curr_t = end_t + 0.1

    return subs


def stage_synth(course_id: str, args):
    """重：IndexTTS2 纯净克隆逐幕配音并生成字幕时间轴"""
    v = get_course(course_id)
    if not v:
        return {"ok": False, "error": f"未找到课程项目: {course_id}"}

    proj = Path(v["project_dir"])
    ep_json_path = proj / "artifacts" / "course_episode.json"
    if not ep_json_path.exists():
        return {"ok": False, "error": "缺 course_episode.json"}

    with open(ep_json_path, "r", encoding="utf-8") as f:
        ep = json.load(f)

    scenes = ep.get("scenes", [])
    voice_cfg = ep.get("voice_config", {})
    voice_ref = voice_cfg.get("voice_ref") or os.environ.get("INDEXTTS_VOICE_REF") or DEFAULT_VOICE_REF

    from tools.audio.indextts_tts import IndexTTS2TTS
    from lib.gpu_lock import gpu_lock

    tool = IndexTTS2TTS()
    audio_dir = proj / "assets" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    hf_audio = proj / "hyperframes" / "assets" / "audio"
    hf_audio.mkdir(parents=True, exist_ok=True)

    set_status(course_id, "tts")

    with gpu_lock(label=f"course-tts-{course_id}", timeout=1800, heartbeat=30):
        for i, sc in enumerate(scenes, 1):
            out_wav = audio_dir / f"sec_{i:02d}.wav"
            # 增量合成：已存在则复用
            if not out_wav.exists():
                print(f">> [synth] 合成第 {i}/{len(scenes)} 幕语音: {sc['narration'][:25]}...", flush=True)
                res = tool.execute({
                    "text": sc["narration"],
                    "output_path": str(out_wav),
                    "spk_audio_prompt": voice_ref,
                    "speed": 1.0,
                    "use_emo_text": False,
                    "emo_vector": None,
                    "seed": 42 + i,
                    "temperature": voice_cfg.get("temperature", 0.65),
                    "top_p": voice_cfg.get("top_p", 0.75),
                    "top_k": voice_cfg.get("top_k", 30),
                    "repetition_penalty": voice_cfg.get("repetition_penalty", 5.0)
                })
                if not res.success:
                    return {"ok": False, "error": f"第 {i} 幕 TTS 失败: {res.error}"}

            dur = get_wav_duration(out_wav)
            sc["duration"] = round(dur, 2)
            sc["audio_file"] = f"assets/audio/{out_wav.name}"
            # 自动生成精确字幕时间轴（剥离发音标注）
            clean_narr = re.sub(r"<([^|>]+)\|[^>]+>", r"\1", sc["narration"])
            sc["subtitles"] = auto_align_subtitles(clean_narr, dur)
            # 同步到 hyperframes 目录
            shutil.copy2(out_wav, hf_audio / out_wav.name)

    # 写回更新后的 episode JSON
    with open(ep_json_path, "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)

    set_status(course_id, "tts_done")
    return {"ok": True, "course_id": course_id, "synthesized_scenes": len(scenes)}


def stage_compose(course_id: str, args):
    """轻：调用模板生成器装配 HyperFrames"""
    v = get_course(course_id)
    if not v:
        return {"ok": False, "error": f"未找到课程项目: {course_id}"}

    proj = Path(v["project_dir"])
    ep_json_path = proj / "artifacts" / "course_episode.json"
    assets_dir = proj / "assets"
    out_html = proj / "hyperframes" / "index.html"

    # 同步 SFX 与 BGM 到 hyperframes/assets
    hf_assets = proj / "hyperframes" / "assets"
    (hf_assets / "sfx").mkdir(parents=True, exist_ok=True)
    (hf_assets / "music").mkdir(parents=True, exist_ok=True)
    for f in (assets_dir / "sfx").glob("*.wav"):
        shutil.copy2(f, hf_assets / "sfx" / f.name)
    for f in (assets_dir / "music").glob("*.mp3"):
        shutil.copy2(f, hf_assets / "music" / f.name)
    if (assets_dir / "gsap.min.js").exists():
        shutil.copy2(assets_dir / "gsap.min.js", hf_assets / "gsap.min.js")

    cmd = [
        sys.executable, str(GEN_COMPOSE),
        str(ep_json_path), str(assets_dir), str(out_html)
    ]
    r = sh(cmd, cwd=str(proj), timeout=120)
    if r.returncode != 0:
        return {"ok": False, "error": f"模板生成失败: {r.stdout}"}

    set_status(course_id, "composed")
    return {"ok": True, "course_id": course_id, "html": str(out_html)}


def stage_render(course_id: str, args):
    """重：调用 hyperframes render 渲染 1080P FHD，并可选进行 4K HEVC 压制"""
    v = get_course(course_id)
    if not v:
        return {"ok": False, "error": f"未找到课程项目: {course_id}"}

    proj = Path(v["project_dir"])
    index_html = proj / "hyperframes" / "index.html"
    if not index_html.exists():
        return {"ok": False, "error": "缺 hyperframes/index.html，请先运行 compose"}

    render_out_1080p = proj / "renders" / "final_1080p.mp4"
    set_status(course_id, "rendering")

    print(f">> [render] 正在调用 hyperframes 渲染 1080P FHD 视频...", flush=True)
    npx_bin = shutil.which("npx") or "npx"
    # hyperframes 渲染指令
    cmd_render = [
        npx_bin, "hyperframes", "render",
        str(index_html.parent),
        "-o", str(render_out_1080p)
    ]
    env = dict(os.environ)
    npm_cache = OMO_ROOT / ".npm-cache"
    npm_cache.mkdir(parents=True, exist_ok=True)
    env["npm_config_cache"] = str(npm_cache)

    r = sh(cmd_render, cwd=str(proj), env=env, timeout=1800)
    if r.returncode != 0 or not render_out_1080p.exists():
        return {"ok": False, "error": f"HyperFrames 渲染失败: {r.stdout}"}

    render_out_4k = None
    if getattr(args, "enable_4k", False) or getattr(args, "is_4k", True):
        render_out_4k = proj / "renders" / "final_4k.mp4"
        print(f">> [render] 正在使用 Lanczos 算法重采样压制 4K UHD HEVC 视频...", flush=True)
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        cmd_4k = [
            ffmpeg_bin, "-y", "-i", str(render_out_1080p),
            "-vf", "scale=3840:2160:flags=lanczos",
            "-c:v", "libx265", "-crf", "18", "-preset", "slow",
            "-c:a", "aac", "-b:a", "320k",
            str(render_out_4k)
        ]
        r4 = sh(cmd_4k, cwd=str(proj), timeout=1800)
        if r4.returncode != 0 or not render_out_4k.exists():
            print(f">> [warning] 4K 压制出现告警，已保留 1080P: {r4.stdout}", flush=True)

    set_status(course_id, "rendered")
    return {
        "ok": True,
        "course_id": course_id,
        "video_1080p": str(render_out_1080p),
        "video_4k": str(render_out_4k) if render_out_4k and render_out_4k.exists() else None
    }


def stage_package(course_id: str, args):
    """轻：组装交付发布包（视频、封面、双标题、简介）"""
    v = get_course(course_id)
    if not v:
        return {"ok": False, "error": f"未找到课程项目: {course_id}"}

    proj = Path(v["project_dir"])
    pkg_dir = proj / "package"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    ep_json_path = proj / "artifacts" / "course_episode.json"
    ep_title = v.get("title") or v.get("topic") or course_id
    ep_hook = f"绝大多数人都搞错了！{ep_title} 的底层秘密"
    ep_desc = f"深度拆解 {ep_title} 的技术原理与生产级落地实践。"

    # 1. 复制成片
    v1080 = proj / "renders" / "final_1080p.mp4"
    if v1080.exists():
        shutil.copy2(v1080, pkg_dir / "video_1080p.mp4")
    v4k = proj / "renders" / "final_4k.mp4"
    if v4k.exists():
        shutil.copy2(v4k, pkg_dir / "video_4k.mp4")

    # 动态解析分幕时间戳
    chapters_str = ""
    if ep_json_path.exists():
        with open(ep_json_path, "r", encoding="utf-8") as f:
            d = json.load(f)
            ep_title = d.get("title", ep_title)
            ep_hook = d.get("title_hook", ep_hook)
            ep_desc = d.get("description", ep_desc)
            next_hook = d.get("next_episode_hook", {})
            hook_hl = next_hook.get("headline", "从 884k 暴降至 1,160：SkillWeaver 终结工具过载灾难")
            hook_narr = next_hook.get("narration", "当工具库膨胀到两千多个，加载一次烧掉八十八万 Token？下一集揭秘 OKF 确定性知识图谱！")
            
            curr_time_s = 0.0
            for idx, sc in enumerate(d.get("scenes", []), 1):
                m = int(curr_time_s // 60)
                s = int(curr_time_s % 60)
                topic_tag = sc.get("topic_tag", f"第{idx}幕")
                headline_zh = sc.get("display", {}).get("headline", {}).get("zh", sc.get("narration", "")[:16])
                chapters_str += f"{m:02d}:{s:02d} {topic_tag}：{headline_zh}\n"
                curr_time_s += float(sc.get("duration", 25.0)) + 0.5

    is_bilibili = "bilibili" in course_id or "deepseek" in course_id
    if is_bilibili:
        tags_str = "DeepSeek,ClaudeCode,AI编程,Harness,开源,大模型,软件工程,人工智能,前端开发,极客,代码生成"
        alt_title_2 = "【深度硬操】不花一分钱！DeepSeek 开源 AI 编程管家 Harness v0.1.5 实操测评"
        alt_title_3 = "告别缓存崩溃！DeepSeek Harness v0.1.5 现场实操：看图写代码 + 97% 缓存复用"
        call_to_action_str = """🎯 讨论互动：
欢迎把你的实测体验打在评论区！喜欢本期内容别忘了点赞、投币、收藏一键三连，下期带大家手把手搭建多 Agent 协同团队！"""
    else:
        tags_str = "Agent工程化,大模型,ContextRot,前缀缓存,PrimeAgent,DeepSeek,Mem0,软件工程,人工智能,架构设计"
        alt_title_2 = "深度拆解：为什么绝大多数 AI Agent 长任务都会变成电子痴呆？Context Rot 与前缀缓存破局"
        alt_title_3 = "从 200k 记忆诅咒到 120 倍降本暴击！PrimeAgent 与 DeepSeek 终结上下文腐化"
        call_to_action_str = """🎯 课件与高清架构图获取：
欢迎关注【AI工程前线】，在评论区留言「Harness」，获取本期全部系统架构蓝图与长程评测数据集。"""

    if not chapters_str.strip():
        chapters_str = """00:00 黄金3秒：别等内测了！开源全家桶直接用
00:14 架构对比：系统指令后置追加与 97% 缓存命中
00:39 实操演示：看图写代码与内嵌侧边栏实时预览
00:58 动态控制：实时打断插队与 Headless 自动化单测
01:18 极速性能：260+ Tokens/s 吞吐与一行命令本地部署
01:33 结尾互动：欢迎点赞、投币、收藏一键三连"""

    unified_publish_doc = f"""================================================================================
【B 站视频发布全套物料 · 一键复制专用单文档】
项目名称：{ep_title}
归档目录：{pkg_dir}
================================================================================

--------------------------------------------------------------------------------
一、 视频标题（投稿时填入“标题”框，任选其一）
--------------------------------------------------------------------------------

【首选推荐·高点击冲突型】
{ep_hook}

【备选 1·专业陈述型】
{ep_title}

【备选 2·硬核架构型】
{alt_title_2}

【备选 3·悬念吸睛型】
{alt_title_3}


--------------------------------------------------------------------------------
二、 视频标签（投稿时填入“标签/Tag”框，整行全选复制粘贴）
--------------------------------------------------------------------------------

{tags_str}


--------------------------------------------------------------------------------
三、 视频简介（投稿时填入“简介”框，直接全选下方内容复制粘贴）
--------------------------------------------------------------------------------

【硬核实操】{ep_title}
{ep_desc}

📌 视频内容分幕时间轴（点击精准跳转）：
{chapters_str.strip()}

🔥 下集预告：
{hook_hl}
{hook_narr}

{call_to_action_str}

⚙️ 制作说明：
• 配音：采用创作者专属音色克隆（IndexTTS2 纯净克隆模型合成）
• 视觉：硬核极客科技风与暗黑高对比动态 UI，由 HyperFrames 确定性渲染引擎驱动
• 字幕：毫秒级全屏动态同步高对比度字幕条

#人工智能 #AI智能体 #大模型落地 #软件工程 #极客 #DeepSeek
"""
    (pkg_dir / "bilibili.txt").write_text(unified_publish_doc, encoding="utf-8")

    # 3. 封面图提取与全平台 5 比例封面矩阵自动生成（优先使用专用设计封面，杜绝随意抽帧）
    covers_dir = pkg_dir / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    raw_16x9 = covers_dir / "cover_16x9.png"

    designed_cover = proj / "renders" / "cover_design.png"
    if designed_cover.exists():
        shutil.copy2(designed_cover, raw_16x9)
        shutil.copy2(designed_cover, pkg_dir / "cover.png")
    elif v1080.exists():
        # 兜底：若无设计封面，方截取视频帧
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        cmd_thumb = [
            ffmpeg_bin, "-y", "-ss", "12.0", "-i", str(v1080),
            "-frames:v", "1", "-q:v", "2", str(raw_16x9)
        ]
        sh(cmd_thumb, timeout=60)
        if raw_16x9.exists():
            shutil.copy2(raw_16x9, pkg_dir / "cover.png")

        try:
            from PIL import Image
            with Image.open(raw_16x9) as im:
                im_rgb = im.convert("RGB")
                w, h = im_rgb.size

                # 4:3 (1440x1080)
                l43 = (w - 1440) // 2
                im_rgb.crop((l43, 0, l43 + 1440, h)).save(covers_dir / "cover_4x3.png")

                # 1:1 (1080x1080)
                l11 = (w - 1080) // 2
                im_rgb.crop((l11, 0, l11 + 1080, h)).save(covers_dir / "cover_1x1.png")

                # 3:4 (1080x1440)
                dark_bg = (18, 19, 22)
                c34 = Image.new("RGB", (1080, 1440), dark_bg)
                sc_h = int(1080 * h / w)
                im_sc = im_rgb.resize((1080, sc_h), Image.Resampling.LANCZOS)
                c34.paste(im_sc, (0, (1440 - sc_h) // 2))
                c34.save(covers_dir / "cover_3x4.png")

                # 9:16 (1080x1920)
                c916 = Image.new("RGB", (1080, 1920), dark_bg)
                c916.paste(im_sc, (0, (1920 - sc_h) // 2))
                c916.save(covers_dir / "cover_9x16.png")
        except Exception as ex:
            print(f">> [warning] 封面多比例生成异常: {ex}")

    set_status(course_id, "packaged")
    return {
        "ok": True,
        "course_id": course_id,
        "package_dir": str(pkg_dir),
        "files": [f.name for f in pkg_dir.glob("*")]
    }


def stage_run(topic: str, args):
    """轻量全自动运行：new + script，停在脚本人审闸门"""
    r_new = stage_new(topic, args)
    if not r_new.get("ok"):
        return r_new
    course_id = r_new["course_id"]
    return stage_script(course_id, args)


def stage_run_heavy(course_id: str, args):
    """重量全自动串联：synth + compose + render + package"""
    r1 = stage_synth(course_id, args)
    if not r1.get("ok"):
        return r1
    r2 = stage_compose(course_id, args)
    if not r2.get("ok"):
        return r2
    r3 = stage_render(course_id, args)
    if not r3.get("ok"):
        return r3
    return stage_package(course_id, args)


def stage_status(args):
    """查看所有课程项目的状态列表"""
    courses = list_courses()
    if not courses:
        print("当前没有任何课程项目记录。")
        return {"ok": True, "count": 0}
    print("-" * 75)
    print(f"{'Course ID':<26} | {'Status':<18} | {'Topic':<24}")
    print("-" * 75)
    for cid, top, st, upd in courses:
        print(f"{cid:<26} | {st:<18} | {top:<24}")
    print("-" * 75)
    return {"ok": True, "count": len(courses)}


# ---------------------------------------------------------------- CLI Parser
def main():
    parser = argparse.ArgumentParser(description="VOX 科技/硬核课程自动化生产独立管线 CLI")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # new
    p_new = subparsers.add_parser("new", help="新建课程项目")
    p_new.add_argument("topic", help="课程主题或名称")
    p_new.add_argument("--script-file", help="原始课程文案/大纲路径")

    # script
    p_script = subparsers.add_parser("script", help="生成去AI化剧本")
    p_script.add_argument("id", help="课程 ID")

    # approve-script
    p_app = subparsers.add_parser("approve-script", help="审批放行剧本")
    p_app.add_argument("id", help="课程 ID")

    # synth
    p_synth = subparsers.add_parser("synth", help="IndexTTS2 语音合成与字幕对齐")
    p_synth.add_argument("id", help="课程 ID")
    p_synth.add_argument("--json", action="store_true", help="单行 JSON 回报")

    # compose
    p_comp = subparsers.add_parser("compose", help="模板引擎装配 HyperFrames")
    p_comp.add_argument("id", help="课程 ID")

    # render
    p_ren = subparsers.add_parser("render", help="执行渲染")
    p_ren.add_argument("id", help="课程 ID")
    p_ren.add_argument("--4k", dest="is_4k", action="store_true", default=True, help="压制 4K HEVC")
    p_ren.add_argument("--no-4k", dest="is_4k", action="store_false", help="仅渲染 1080P")
    p_ren.add_argument("--json", action="store_true", help="单行 JSON 回报")

    # package
    p_pkg = subparsers.add_parser("package", help="组装成品交付包")
    p_pkg.add_argument("id", help="课程 ID")

    # run
    p_run = subparsers.add_parser("run", help="轻量全自动运行至脚本闸门")
    p_run.add_argument("topic", help="课程主题或名称")
    p_run.add_argument("--script-file", help="原始课程文案/大纲路径")

    # run-heavy
    p_rh = subparsers.add_parser("run-heavy", help="人审后一键完成配音、合成、渲染与打包")
    p_rh.add_argument("id", help="课程 ID")
    p_rh.add_argument("--4k", dest="is_4k", action="store_true", default=True, help="压制 4K HEVC")
    p_rh.add_argument("--no-4k", dest="is_4k", action="store_false", help="仅渲染 1080P")
    p_rh.add_argument("--json", action="store_true", help="单行 JSON 回报")

    # status
    subparsers.add_parser("status", help="查看所有课程项目状态")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    want_json = getattr(args, "json", False)

    res = {"ok": False, "error": "未知命令"}
    if args.command == "new":
        res = stage_new(args.topic, args)
    elif args.command == "script":
        res = stage_script(args.id, args)
    elif args.command == "approve-script":
        res = stage_approve_script(args.id, args)
    elif args.command == "synth":
        res = stage_synth(args.id, args)
    elif args.command == "compose":
        res = stage_compose(args.id, args)
    elif args.command == "render":
        res = stage_render(args.id, args)
    elif args.command == "package":
        res = stage_package(args.id, args)
    elif args.command == "run":
        res = stage_run(args.topic, args)
    elif args.command == "run-heavy":
        res = stage_run_heavy(args.id, args)
    elif args.command == "status":
        res = stage_status(args)

    if want_json:
        emit_json(res)
    else:
        if not res.get("ok"):
            print(f">> [ERROR] {res.get('error')}")
            if "problems" in res:
                for p in res["problems"]:
                    print(f"   - {p}")
            sys.exit(1)
        else:
            print(f">> [OK] 操作成功: {res}")


if __name__ == "__main__":
    main()
