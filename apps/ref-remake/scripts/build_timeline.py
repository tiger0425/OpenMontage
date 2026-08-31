# -*- coding: utf-8 -*-
"""ref-remake 时间轴构建模板：按 ffprobe 实测段长 + 字数比例分配画面时间轴。

用法（workdir 必须在 OpenMontage 根目录）：
    python apps/ref-remake/scripts/build_timeline.py --config projects/<slug>/artifacts/timeline_config.json

timeline_config.json 格式：
{
  "project": "projects/<slug>",
  "final_hold_s": 262.0,
  "segments": [
    {"name": "00_open", "duration_s": 27.7, "scenes": [
        {"file": "s0_0", "text": "旁白句1", "note": "书堆"},
        {"file": "s0_1", "text": "旁白句2", "note": "学士帽"}
    ]}
  ]
}
其中 duration_s 由 assets 阶段 ffprobe 实测回填；缺省时按文本字数比例在段内分摊。

产出：projects/<slug>/artifacts/timeline.json（供 build_index.py 使用）
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.getcwd())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="timeline_config.json 路径")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)

    project = cfg["project"]
    order = [s["name"] for s in cfg["segments"]]

    # 段起始时间（按段实测时长累计）
    start_map: dict[str, float] = {}
    t = 0.0
    for seg in cfg["segments"]:
        start_map[seg["name"]] = round(t, 2)
        t += seg.get("duration_s", 0.0)

    timeline = []
    for seg in cfg["segments"]:
        seg_start = start_map[seg["name"]]
        seg_dur = seg.get("duration_s", 0.0)
        scenes = seg["scenes"]
        if seg_dur <= 0:
            # 无实测时长：按字数比例在段内分摊（兜底，不常用）
            lens = [len(s["text"]) for s in scenes]
            total = sum(lens) or 1
            seg_dur = sum(lens) / 3.5  # ~250 字/分 => ~4.17 字/s，宽松按 3.5
        lens = [len(s["text"]) for s in scenes]
        total = sum(lens) or 1
        cur = 0.0
        for s, l in zip(scenes, lens):
            span = seg_dur * l / total if seg_dur > 0 else 0.0
            timeline.append({
                "file": s["file"],
                "start": round(seg_start + cur, 2),
                "end": round(seg_start + cur + span, 2),
                "duration": round(span, 2),
                "note": s.get("note", ""),
                "seg": seg["name"],
            })
            cur += span

    # 结尾加停留
    total_end = max(x["end"] for x in timeline) if timeline else 0.0
    final_hold = cfg.get("final_hold_s", total_end)
    if final_hold > total_end and timeline:
        last = timeline[-1]
        last["end"] = final_hold
        last["duration"] = round(last["end"] - last["start"], 2)
        total_end = final_hold

    for item in timeline:
        print(f"{item['file']:22s} {item['start']:7.2f} - {item['end']:7.2f}  ({item['duration']:5.2f}s)  {item['note']}")
    print(f"\nTOTAL: {total_end:.2f}s, scenes: {len(timeline)}")

    out = os.path.join(project, "artifacts", "timeline.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"timeline": timeline, "total": round(total_end, 2)}, f, ensure_ascii=False, indent=2)
    print("saved", out)


if __name__ == "__main__":
    main()
