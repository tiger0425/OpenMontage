#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_sync.py — series-adapt 音画同步与完整性验证（合并前强制关卡）

检查每幕 workspace 的：
  1. K-01: scene-1.data-start + 0.4 ≈ vo.data-start（±0.2s）
  2. K-02: workspace 内 WAV 前导静音 ≤0.2s（必须用 clean）
  3. K-06: 每幕 vo_end <= scene_end - 0.5s（语音不被截断，留余量）
  4. K-05: scene 窗口连续无 gap（gap <= 0.2s）
任一 FAIL 则退出码 1 —— 合并前必须全 PASS。

用法:
  python tools/verify_sync.py <episode_dir> <sid...>   # 指定幕
  python tools/verify_sync.py <episode_dir>            # 全部幕
"""
import re, sys, io, os, subprocess

def check_scene(ep, sid):
    p = os.path.join(ep, 'hyperframes-%s' % sid, 'index.html')
    if not os.path.exists(p):
        return [(sid, 'MISSING index.html')]
    s = io.open(p, encoding='utf-8').read()
    errors = []
    m_vo = re.search(r'<audio id="vo"[^>]*data-start="([\d.]+)"', s)
    m_s1 = re.search(r'<section class="clip" id="scene-1" data-start="([\d.]+)"', s)
    scenes = re.findall(r'<section class="clip" id="scene-\d+" data-start="([\d.]+)" data-duration="([\d.]+)"', s)
    if not (m_vo and m_s1 and scenes):
        return [(sid, 'missing vo/scene structure')]
    vo = float(m_vo.group(1))
    s1 = float(m_s1.group(1))
    last_end = max(float(a) + float(b) for a, b in scenes)
    # 1. vo/scene 同步
    if abs(s1 + 0.4 - vo) > 0.2:
        errors.append('K-01: scene1=%s vo=%s 不同步（应差 0.4s）' % (s1, vo))
    # 2. WAV 前导静音
    awav = os.path.join(ep, 'assets', 'audio', '%s_clean.wav' % sid)
    if not os.path.exists(awav):
        awav = os.path.join(ep, 'assets', 'audio', '%s.wav' % sid)
    r = subprocess.run(['ffmpeg','-i',awav,'-af','silencedetect=noise=-50dB:d=0.15','-f','null','-'],
                       capture_output=True, text=True)
    m = re.search(r'silence_start: ([\d.]+)', r.stderr)
    lead = float(m.group(1)) if m else 0.0
    if lead > 0.2:
        errors.append('K-02: WAV 前导静音 %.2fs（未用 clean）' % lead)
    # 3. 语音不截断（vo_end <= last_end - 0.5）
    r2 = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',awav], capture_output=True, text=True)
    adur = float(r2.stdout.strip())
    vo_end = vo + adur
    if vo_end > last_end - 0.5:
        errors.append('K-06: 语音结束 %.2f > 场景结束 %.2f（截断）' % (vo_end, last_end))
    # 4. 窗口连续（L-009: 相邻窗口必须重叠，next_start <= prev_end + 0.1）
    scenes_sorted = sorted((float(a), float(b)) for a, b in scenes)
    for i in range(1, len(scenes_sorted)):
        prev_end = scenes_sorted[i-1][0] + scenes_sorted[i-1][1]
        next_start = scenes_sorted[i][0]
        if next_start > prev_end + 0.1:
            errors.append('K-05: 窗口 gap %.2fs at %.2f（应重叠，L-009）' % (next_start - prev_end, prev_end))
    return [(sid, e) for e in errors]

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ep = sys.argv[1]
    sids = sys.argv[2:] if len(sys.argv) > 2 else ['s%02d' % i for i in range(1, 11)]
    all_fail = []
    for sid in sids:
        errs = check_scene(ep, sid)
        if errs:
            for _, e in errs:
                print('FAIL %s: %s' % (sid, e))
                all_fail.append((sid, e))
        else:
            print('PASS %s' % sid)
    if all_fail:
        print('\n%d 项未通过 — 修复后再合并（见 known-issues.md K-01/K-02/K-05/K-06）' % len(all_fail))
        sys.exit(1)
    print('\nALL PASS — 音画同步与完整性 OK，可合并')

if __name__ == '__main__':
    main()
