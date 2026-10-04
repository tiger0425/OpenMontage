# -*- coding: utf-8 -*-
"""cmd_motion 的 ASMR 保护与 --only 作用域回归测试。

背景（两件事都实测过）：

1. `asmr-*.m4a` 可能已被人工加工（例如用 Demucs 去过人声）。完整跑一次 motion 会重建
   所有 hero 幕的 asmr 并静默覆盖它们，本项目已踩过 —— 所以覆盖前必须先备份。
2. 交接文档曾判定「motion 的 asmr 抽取忽略 --only」，实测证伪：`--only` 在 hero 循环前
   过滤，asmr 抽取在循环内。本测试把这个结论固定下来，防止将来真的退化。

测试用 stub 替掉 ComfyUI，不碰 GPU、不碰真实项目目录。
"""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

import pytest

OMO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(OMO_ROOT) not in sys.path:
    sys.path.insert(0, str(OMO_ROOT))

VOX = OMO_ROOT / "bin" / "vox_collage.py"

# 6 幕：hero_motion = i==1 或 i%3==0  ->  01 / 03 / 06
SCENES = [
    {
        "id": f"{i:02d}",
        "order": i,
        "motion_type": "hero_motion" if (i == 1 or i % 3 == 0) else "drift_only",
        "visual": {},
        "voiceover": {"text": "x"},
        "timing": {"media_start_sec": 1.0},
    }
    for i in range(1, 7)
]


def _load_vox():
    spec = importlib.util.spec_from_file_location("vox_collage_under_test", VOX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_silent_audio(path: Path) -> bool:
    """造一个 1 秒静音音频当 H3 产物替身（无视频流 -> 走 copy2 兜底，asmr 抽取仍成功）。"""
    r = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "anullsrc=r=44100:cl=stereo", "-t", "1", "-c:a", "aac", str(path)],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and path.exists()


@pytest.fixture()
def motion_env(tmp_path, monkeypatch):
    """搭一个隔离的项目根 + stub ComfyUI，返回 (mod, proj_dir, video_dir)。"""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")

    fixture = tmp_path / "fixture.m4a"
    if not _make_silent_audio(fixture):
        pytest.skip("could not build the silent-audio fixture")

    mod = _load_vox()
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(mod, "set_status", lambda *a, **k: None)

    pid = "probe-only"
    proj = projects / pid
    video_dir = proj / ".media" / "video"
    (proj / ".media" / "assets").mkdir(parents=True)
    video_dir.mkdir(parents=True)

    (proj / "episode.json").write_text(
        json.dumps({"id": pid, "ratio": "9:16", "scenes": SCENES}), encoding="utf-8")
    (proj / ".media" / "voice-manifest.json").write_text(
        json.dumps({"lines": [{"frame": s["id"], "seconds": 3.0} for s in SCENES]}),
        encoding="utf-8")

    # 1x1 PNG，避免被「缺参考图」守卫跳过
    import base64
    (proj / ".media" / "assets" / "gen-scene-03.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="))

    class FakeComfy:
        def is_up(self): return True
        def free_memory(self): pass
        def upload_image(self, ref, name): return name
        def queue_prompt(self, wf): return "qid"
        def wait_prompt(self, qid, timeout=0): return {}
        def outputs_of(self, hist): return [{"filename": "x.mp4", "subfolder": ""}]
        def download_output(self, o, dst): shutil.copy2(fixture, dst)

    monkeypatch.setattr(mod, "comfyui_client", FakeComfy())
    return mod, proj, video_dir


def test_only_scopes_asmr_to_selected_scene(motion_env):
    """--only 03 只应重建 03 的 asmr，不得触碰 01/06（交接文档的证伪结论）。"""
    mod, proj, video_dir = motion_env
    sentinels = {}
    for sid in ("01", "06"):
        p = video_dir / f"asmr-{sid}.m4a"
        p.write_bytes(f"SENTINEL-{sid}".encode())
        sentinels[sid] = p.read_bytes()

    mod.cmd_motion(Namespace(id="probe-only", only="03", json=True))

    for sid, before in sentinels.items():
        assert (video_dir / f"asmr-{sid}.m4a").read_bytes() == before, (
            f"asmr-{sid}.m4a 被 --only 03 的运行改动了 —— --only 作用域已退化")


def test_existing_asmr_is_backed_up_before_overwrite(motion_env):
    """覆盖已有 asmr 前必须先备份，使人工加工版（如 Demucs 去人声）可恢复。"""
    mod, proj, video_dir = motion_env
    original = b"DEMUCS-DE-VOCALED-HUMAN-WORK"
    (video_dir / "asmr-03.m4a").write_bytes(original)

    mod.cmd_motion(Namespace(id="probe-only", only="03", json=True))

    backups = list((video_dir / "_asmr_backup").glob("*/asmr-03.m4a"))
    assert backups, "覆盖 asmr-03.m4a 前没有生成任何备份"
    assert backups[0].read_bytes() == original, "备份内容不是被覆盖前的那一份"

    # 备份目录不得被 generate_composition 的 asmr-*.m4a 非递归 glob 收进去
    assert not list(video_dir.glob("asmr-*.m4a.bak")), "备份命名会污染 asmr-*.m4a 的匹配"
