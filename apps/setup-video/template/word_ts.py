#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原理特辑 v3：whisper 字级时间戳（word_ts.json）——卡片高亮精确对口播。

用法:
  python apps/setup-video/template/word_ts.py <assets_dir> <out_word_ts.json>

对 compose/assets/s1..s6.wav 用 faster-whisper（small, cpu, int8）提取逐字时间戳。
输出 {k: [{"w": 字, "t": 秒}, ...]}——模板生成器据此把卡片元素高亮对齐到口播词。
"""
import json
import sys
from pathlib import Path


def main():
    assets_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    from faster_whisper import WhisperModel
    m = WhisperModel("small", device="cpu", compute_type="int8")
    result = {}
    for k in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        wav = assets_dir / f"{k}.wav"
        segs, _ = m.transcribe(str(wav), language="zh", word_timestamps=True)
        words = []
        for seg in segs:
            for w in (seg.words or []):
                words.append({"w": w.word.strip(), "t": round(w.start, 2)})
        result[k] = words
        print(f"[word_ts] {k}: {len(words)} words", flush=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
