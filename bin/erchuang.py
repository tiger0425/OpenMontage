# -*- coding: utf-8 -*-
"""ErChuang (二创) 编排 CLI — auto-dub 成片 → 抖音横屏二创（去原作/换音色/抖音节奏/重点提示）。

试点验证（2026-09-03 Nissan B_PnlpsVtnw P1/P2 用户验收）固化的最小可复用编排。
轻量、无数据库、单视频串行，重算力环节内部走规范入口（indextts-bridge client / ffmpeg / hyperframes），
不写 ad-hoc 脚本直调底层。

子命令:
  zones   标注原作出镜禁区 → <proj>/zones.json     （YuNet 检测 + SFace 指纹，模型在 apps/erchuang/models/）
  synth   按 manifest 逐段合成配音 → narration.wav + timings.json（你音色 + 逐句原片 emo 参考 + 呼吸 gap）
  montage 按 cuts 从原片裁干净素材拼接 → input-video.mp4（可带 bed：从 no_vocals 同 cuts 裁引擎声床）
  mux     画面(含 overlay) + 配音 + 声床 → final.mp4

输入资产复用 auto-dub 工作目录 projects/auto-dub/auto-dub-<video_id>/ 的
source.mp4 / assets/vocals.wav / assets/no_vocals.wav / transcript.json。

示例:
  python bin/erchuang.py zones  --video-id B_PnlpsVtnw --ref-sec 35 --out-dir projects/erchuang-nissan
  python bin/erchuang.py synth  --manifest apps/erchuang/examples/nissan_p1.manifest.json --dry-run
  python bin/erchuang.py synth  --manifest apps/erchuang/examples/nissan_p1.manifest.json
  python bin/erchuang.py montage --source projects/auto-dub/auto-dub-B_PnlpsVtnw/source.mp4 \
      --bed  projects/auto-dub/auto-dub-B_PnlpsVtnw/assets/no_vocals.wav \
      --cuts "386-393.85;400-414.26;472-488.14;592-609.01;660-673.2;674-692.55;716-725" \
      --out input-video.mp4 --bed-out bed.wav
  python bin/erchuang.py mux --video input-video.mp4 --narration narration.wav --bed bed.wav --out P1.mp4

Overlay 卡片（talking-head-recut 三处改造）仍为作者编写 index.html + npx hyperframes render 的环节，
属创意步骤不在此固化；卡点时间用 synth 产出的 timings.json。
"""
from __future__ import annotations

import argparse, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
AUTODUB_DIR = ROOT / "projects" / "auto-dub"
FACE_MODELS = ROOT / "apps" / "erchuang" / "models"
FACE_ZONES_KEYS = {"yunet", "sface"}


def _ad_dir(video_id: str) -> Path:
    p = AUTODUB_DIR / f"auto-dub-{video_id}"
    if not p.is_dir():
        sys.exit(f"[erchuang] auto-dub 工作目录不存在: {p}（先跑 python bin/auto_dub.py process 生成）")
    return p


def _ff(args: list[str]) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- zones
def cmd_zones(a: argparse.Namespace) -> None:
    import cv2  # 延迟导入：无 GPU/opencv 时该命令报清晰错误，不影响其它子命令
    ad = _ad_dir(a.video_id)
    src = ad / "source.mp4"
    yunet = FACE_MODELS / "yunet.onnx"
    sface = FACE_MODELS / "sface.onnx"
    for m in (yunet, sface):
        if not m.exists():
            sys.exit(f"[erchuang] 缺人脸模型 {m}（拷贝 opencv_zoo yunet/sface onnx 到 apps/erchuang/models/）")
    out_dir = Path(a.out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    det = cv2.FaceDetectorYN_create(str(yunet), "", (320, 320))
    rec = cv2.FaceRecognizerSF_create(str(sface), "")
    def feat(frame, f):
        return rec.feature(rec.alignCrop(frame, f)).flatten()
    def cos(a, b):
        import numpy as np
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS); dur = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) / fps
    def frame_at(t):
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000); ok, f = cap.read(); return f if ok else None
    ref = frame_at(a.ref_sec)
    h, w = ref.shape[:2]; det.setInputSize((w, h))
    _, fs = det.detect(ref)
    fs = sorted(fs, key=lambda x: x[2] * x[3], reverse=True)
    if fs is None or len(fs) == 0:
        sys.exit(f"[erchuang] {a.ref_sec}s 未检出人脸（换 --ref-sec 或该画面无原作头像）")
    ref_feat = feat(ref, fs[0])
    print(f"[erchuang] 基准人脸 @ {a.ref_sec}s box={[round(v) for v in fs[0][:4]]}")
    hits, t = [], 0.0
    while t < dur:
        f = frame_at(t)
        if f is not None:
            h, w = f.shape[:2]; det.setInputSize((w, h))
            _, ffs = det.detect(f)
            if ffs is not None:
                for ff in ffs:
                    if ff[2] * ff[3] < 80 * 80:
                        continue
                    if cos(ref_feat, feat(f, ff)) >= a.threshold:
                        hits.append(round(t))
        t += a.step
    cap.release()
    hits = sorted(set(hits))
    # ±pad 并簇
    raw = sorted(set(x for x in hits))
    merged = []
    for x in raw:
        if merged and x - merged[-1][1] <= 2 * a.pad:
            merged[-1][1] = x
        else:
            merged.append([max(0, x - a.pad), x + a.pad])
    zones = [{"start": m[0], "end": m[1]} for m in merged]
    out = out_dir / "zones.json"
    out.write_text(json.dumps({"video_id": a.video_id, "ref_sec": a.ref_sec,
                               "zones": zones, "hits": raw}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[erchuang] {len(raw)} 处命中 → {len(zones)} 个禁区簇（±{a.pad}s 并簇）→ {out}")


# ---------------------------------------------------------------- synth
def cmd_synth(a: argparse.Namespace) -> None:
    m = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    out_dir = Path(a.out_dir or Path(a.manifest).resolve().parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_dir = out_dir / "seg"; wav_dir.mkdir(exist_ok=True)
    import importlib.util
    spec = importlib.util.spec_from_file_location("indextts_client", str(ROOT / "apps" / "indextts-bridge" / "client.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

    def resolve_emo(spec_str: str) -> Path | None:
        if not spec_str:
            return None
        if spec_str.startswith("vocal@"):
            ss, dd = spec_str[6:].split(":")
            v = m["_vocals"] if "_vocals" in m else _ad_dir(m.get("video_id", "") or a.video_id) / "assets" / "vocals.wav"
            refp = wav_dir / f"emo_{ss}_{dd}.wav"
            _ff(["ffmpeg", "-y", "-v", "error", "-ss", str(float(ss)), "-t", str(float(dd)),
                 "-i", str(v), "-ar", "22050", "-ac", "1", str(refp)])
            return refp
        return Path(spec_str)

    plan = []
    for i, c in enumerate(m["chunks"]):
        refp = resolve_emo(c.get("emo_audio"))
        plan.append((i, c["text"], refp, float(c.get("gap_ms", 250)), float(c.get("tempo", 1.0))))
    if a.dry_run:
        for i, text, refp, gap, tempo in plan:
            print(f"[{i}] gap={gap:.0f}ms tempo={tempo} emo={refp.name if refp else '纯净'} :: {text[:34]}")
        print(f"[erchuang] 共 {len(plan)} 段（dry-run，未合成）")
        return

    with mod.IndexTTSSession(voice_ref=m["voice_ref"], model_version=m.get("model_version", "2.5"),
                             lang=m.get("lang", "ZH"), emotion=m.get("emotion", "calm")) as tts:
        seg_paths = []
        for i, text, refp, gap, tempo in plan:
            seg = wav_dir / f"seg{i:02d}.wav"
            ok = tts.synthesize(text, str(seg), emo_audio_prompt=str(refp) if refp else None,
                                emo_alpha=float(m.get("emo_alpha", 0.6)))
            if not ok:
                sys.exit(f"[erchuang] 段 {i} 合成失败")
            if tempo != 1.0:
                tmp_ = seg.with_suffix(".tmp.wav")
                seg.rename(tmp_)
                _ff(["ffmpeg", "-y", "-v", "error", "-i", str(tmp_), "-filter:a", f"atempo={tempo:.4f}", str(seg)])
                tmp_.unlink()
            seg_paths.append(seg)
            print(f"[erchuang] seg{i:02d} ok tempo={tempo}")
    from pydub import AudioSegment  # 拼接放末尾导入，避免无 pydub 时其它子命令不可用
    track = AudioSegment.empty()
    timings = []
    for i, seg, (_, _, _, gap, _) in zip(range(len(seg_paths)), seg_paths, plan):
        segp = seg_paths[i]
        a_seg = AudioSegment.from_wav(str(segp))
        timings.append({"seg": i, "text": plan[i][1], "duration": round(len(a_seg) / 1000, 3),
                        "start": round(len(track) / 1000, 3), "gap_ms": int(gap)})
        track += a_seg + AudioSegment.silent(duration=int(gap))
    nar_out = out_dir / a.narration_out
    track.export(str(nar_out), format="wav")
    (out_dir / "timings.json").write_text(json.dumps(timings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[erchuang] narration: {len(track)/1000:.1f}s → {nar_out}")


# ---------------------------------------------------------------- montage
def cmd_montage(a: argparse.Namespace) -> None:
    cuts = []
    for part in a.cuts.split(";"):
        s, e = part.strip().split("-")
        cuts.append((float(s), float(e)))
    def run(src: str, out: str, want_audio: bool) -> None:
        cmd = ["ffmpeg", "-y", "-v", "error"]
        for _ in cuts:
            cmd += ["-i", src]
        flt = []
        for i, (s, e) in enumerate(cuts):
            src_label = f"[{i}:{'a' if want_audio else 'v'}]"
            if want_audio:
                flt.append(f"{src_label}atrim=start={s}:end={e},asetpts=PTS-STARTPTS,volume={a.bed_volume}[v{i}]")
            else:
                flt.append(f"{src_label}trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        flt.append("".join(f"[v{i}]" for i in range(len(cuts))) + f"concat=n={len(cuts)}:{'v=0:a=1' if want_audio else 'v=1:a=0'}[o]")
        cmd += ["-filter_complex", ";".join(flt), "-map", "[o]"]
        if not want_audio:
            cmd += ["-c:v", "libx264", "-crf", "18", "-g", "30", "-keyint_min", "30",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        else:
            cmd += ["-ar", "44100"]
        cmd += [out]
        _ff(cmd)
    out_v = a.out if a.out.endswith(".mp4") else f"{a.out}.mp4"
    run(a.source, out_v, want_audio=False)
    print(f"[erchuang] video → {out_v}")
    if a.bed and a.bed_out:
        run(a.bed, a.bed_out, want_audio=True)
        print(f"[erchuang] bed → {a.bed_out}")


# ---------------------------------------------------------------- mux
def cmd_mux(a: argparse.Namespace) -> None:
    inputs = [a.video]
    nxt = 1
    filters = []
    mix_ins = []
    nar_label, bed_label = None, None
    if a.narration:
        inputs.append(a.narration)
        filters.append(f"[{nxt}:a]volume=1.0,aresample=48000[nar]")
        nar_label = "[nar]"
        nxt += 1
    if a.bed and os.path.exists(a.bed):
        inputs.append(a.bed)
        # 原声床（no_vocals）普遍偏静；loudnorm 提到清晰可闻再混，避免被旁白盖没
        filters.append(f"[{nxt}:a]loudnorm=I=-25:TP=-2:LRA=13,aresample=48000[bed]")
        bed_label = "[bed]"
        nxt += 1
    mix_parts = [p for p in (nar_label, bed_label) if p]
    if len(mix_parts) >= 2:
        filters.append("".join(mix_parts) +
                       "amix=inputs=2:duration=first:normalize=0:dropout_transition=0[a];"
                       "[a]alimiter=limit=0.95[aout]")
        cmd = ["ffmpeg", "-y", "-v", "error"]
        for i in inputs:
            cmd += ["-i", i]
        cmd += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out]
    elif len(mix_parts) == 1:
        src_label = "[aout]" if False else ("[nar]" if nar_label else "[bed]")
        filters.append(f"{src_label}atrim=end_pts=8e9[aout]")
        cmd = ["ffmpeg", "-y", "-v", "error"]
        for i in inputs:
            cmd += ["-i", i]
        cmd += ["-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", a.out]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", a.video, "-c", "copy", a.out]
    subprocess.run(cmd, check=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", a.out], capture_output=True, text=True).stdout.strip()
    print(f"[erchuang] → {a.out} ({dur}s)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="erchuang.py", description="抖音横屏二创编排 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("zones", help="标注原作出镜禁区")
    p.add_argument("--video-id", required=True)
    p.add_argument("--ref-sec", type=float, default=35.0, help="原作头像基准秒点（用户指认处）")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--threshold", type=float, default=0.35, help="SFace 余弦相似度阈值")
    p.add_argument("--step", type=float, default=5.0, help="扫描步长（秒）")
    p.add_argument("--pad", type=float, default=5.0, help="每命中前后扩 pad 秒再并簇")
    p.set_defaults(fn=cmd_zones)

    p = sub.add_parser("synth", help="逐段合成配音（音色 + 逐句 emo 参考）")
    p.add_argument("--manifest", required=True)
    p.add_argument("--video-id", default="", help="emo 用 vocal@ 时的回退源")
    p.add_argument("--out-dir", default="", help="缺省用 manifest 同目录")
    p.add_argument("--narration-out", default="narration.wav")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_synth)

    p = sub.add_parser("montage", help="按 cuts 裁干净素材拼接")
    p.add_argument("--source", required=True)
    p.add_argument("--cuts", required=True, help="如 386-393.85;400-414.26")
    p.add_argument("--out", required=True)
    p.add_argument("--bed", default="", help="no_vocals 源，同 cuts 裁引擎声床")
    p.add_argument("--bed-out", default="")
    p.add_argument("--bed-volume", type=float, default=0.15, help="声床音量（默认 0.15）")
    p.set_defaults(fn=cmd_montage)

    p = sub.add_parser("mux", help="画面+配音+声床混流")
    p.add_argument("--video", required=True)
    p.add_argument("--narration", default="")
    p.add_argument("--bed", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_mux)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
