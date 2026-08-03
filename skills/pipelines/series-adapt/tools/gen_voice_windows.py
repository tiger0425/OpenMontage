#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_voice_windows.py — series-adapt 语音边界窗口生成器（L-049 / K-01）

分镜窗口必须来自 whisper 转写（语音句边界），禁止词数均分——
否则切点落在句子中间（"语音没说完画面就切走"）。本工具：
  1. 对每幕 _clean.wav 转写（whisper medium, cuda）
  2. 按语音 seg 边界生成 L-009 连续窗口：
     start_i = max(prev_end - 0.5, voice_start_i - 0.4)
     end_i   = voice_end_i + 0.6（幕末 +1.0）
  3. 写出 {sid}_windows.json（时间已含 +OFFSET 偏移，默认 2.6）
  4. 同步生成 {sid}_design.json（构成族/机位按窗口轮换，相邻不同）

用法:
  python tools/gen_voice_windows.py <episode_dir> [--offset 2.6]

前置: 必须先跑 trim_audio_lead.py（时间戳基于 clean 音频）
"""
import subprocess, sys, os, json

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    ep = args[0]
    offset = 2.6
    if '--offset' in args:
        offset = float(args[args.index('--offset') + 1])

    adir = os.path.join(ep, 'assets', 'audio')
    # 与 build_episode_parts.py 共用同一 TMP 目录（必须是 Temp/opencode）
    tmp = r'C:\Users\tiger\AppData\Local\Temp\opencode'
    os.makedirs(tmp, exist_ok=True)

    from faster_whisper import WhisperModel
    model = WhisperModel('medium', device='cuda', compute_type='float16')

    sids = []
    for f in sorted(os.listdir(adir)):
        if f.endswith('_clean.wav'):
            sids.append(f.replace('_clean.wav', ''))
    if not sids:
        # fallback: 用原 wav（未裁前导——会警告）
        sids = [f.replace('.wav', '') for f in sorted(os.listdir(adir)) if f.endswith('.wav')]
        print('WARNING: no _clean.wav found — run trim_audio_lead.py first (L-050/K-02)')

    FAMS = ['full-bleed', 'letterbox', 'top-title-cascade', 'blueprint-draw', 'diagonal-split', 'diagonal-split-rev']
    CAMS = ['push_in', 'pan', 'pull_out', 'tilt', 'parallax', 'element', 'static']

    for idx, sid in enumerate(sids):
        wav = os.path.join(adir, '%s_clean.wav' % sid) if os.path.exists(os.path.join(adir, '%s_clean.wav' % sid)) else os.path.join(adir, '%s.wav' % sid)
        segments, info = model.transcribe(wav, language='en', word_timestamps=False)
        segs = [(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments]
        windows = []
        prev_end = -999
        for i, (vs, ve, txt) in enumerate(segs):
            # L-009 连续窗口：start 永远与上一窗重叠 0.5s（句间停顿并入窗口，无 gap）
            w_start = prev_end - 0.5 if prev_end > -999 else vs - 0.4
            w_end = ve + 0.6
            if i + 1 < len(segs):
                w_end = min(w_end, segs[i + 1][0] + 0.1)
            windows.append({'start': round(w_start, 2), 'end': round(w_end, 2),
                            'dur': round(w_end - w_start, 2), 'voice': [vs, ve], 'text': txt})
            prev_end = w_end
        windows[-1]['end'] = round(segs[-1][1] + 1.0, 2)
        windows[-1]['dur'] = round(windows[-1]['end'] - windows[-1]['start'], 2)
        # +offset 偏移（scene-1 从 offset 起，vo=offset+0.4）
        for w in windows:
            w['start'] = round(w['start'] + offset, 2)
            w['end'] = round(w['end'] + offset, 2)
            w['dur'] = round(w['end'] - w['start'], 2)
        json.dump(windows, open(os.path.join(tmp, '%s_windows.json' % sid), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        # design：构成族/机位按窗口轮换（相邻不同）
        design = {}
        for i, w in enumerate(windows, 1):
            design[str(i)] = {
                'label': 'SHOT %d' % i,
                'camera': CAMS[(i - 1 + idx * 2) % len(CAMS)],
                'motion': 'halftone dots shimmer, paper scraps drift, label strip slides in',
                'family': FAMS[(i - 1 + idx) % len(FAMS)],
            }
        json.dump(design, open(os.path.join(tmp, '%s_design.json' % sid), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('%s: %d segs -> %d windows (%.2f-%.2f)' % (sid, len(segs), len(windows), windows[0]['start'], windows[-1]['end']))

    print('DONE - windows in %s' % tmp)

if __name__ == '__main__':
    main()
