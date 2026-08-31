#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原理特辑字幕生成：按幕生成 subtitles.srt（阿拉伯数字版，用户定案）。

用法:
  python apps/setup-video/template/srt_explainer.py <episode.json> <timings.json> <out.srt>

timings.json 由 instantiate_explainer.py --meta 输出（starts/durs）。
字幕 = episode.subtitles[k]（阿拉伯数字），时间 = 幕 start 到 口播结束（start+dur）。
"""
import json
import sys
from pathlib import Path


def srt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    ep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    timing = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    out = Path(sys.argv[3])
    keys = ["s1", "s2", "s3", "s4", "s5", "s6"]
    subs = ep["subtitles"]
    starts, durs = timing["starts"], timing["durs"]
    lines = []
    idx = 1
    for k in keys:
        t0, t1 = starts[k], starts[k] + durs[k]
        lines.append(f"{idx}")
        lines.append(f"{srt_ts(t0)} --> {srt_ts(t1)}")
        lines.append(subs[k])
        lines.append("")
        idx += 1
    out.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"ok": True, "srt": str(out), "blocks": idx - 1}, ensure_ascii=False))


if __name__ == "__main__":
    main()
