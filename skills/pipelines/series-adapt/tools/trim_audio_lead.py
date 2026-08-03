#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trim_audio_lead.py — series-adapt TTS 前导静音裁剪工具（L-050 / K-02）

IndexTTS2 合成的 WAV 自带 1.2-7.2s 前导静音（实测 s09 7.17s），
不裁会导致语音晚出 3-7s 且窗口错位。本工具：
  1. 检测每个 WAV 的前导静音（silencedetect -50dB）
  2. 裁掉 lead - 0.15s（保留缓冲），输出 {sid}_clean.wav
  3. 输出报告 audio_lead_report.json

用法:
  python tools/trim_audio_lead.py <episode_dir>
  例: python tools/trim_audio_lead.py projects/series-adapt-99/ep-02

规则:
  - 只处理 assets/audio/*.wav（非 _clean）
  - 幂等：已有 _clean 且前导 <=0.2s 则跳过
  - 必须在本工具之后再转写/建窗口（时间戳会偏移）
"""
import subprocess, sys, os, re, json

def detect_lead(wav):
    r = subprocess.run(['ffmpeg','-i',wav,'-af','silencedetect=noise=-50dB:d=0.15','-f','null','-'],
                       capture_output=True, text=True)
    m = re.search(r'silence_start: ([\d.]+)', r.stderr)
    return float(m.group(1)) if m else 0.0

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    ep = sys.argv[1]
    adir = os.path.join(ep, 'assets', 'audio')
    if not os.path.isdir(adir):
        print('ERROR: %s not found' % adir)
        sys.exit(1)

    results = {}
    for f in sorted(os.listdir(adir)):
        if not f.endswith('.wav') or '_clean' in f:
            continue
        src = os.path.join(adir, f)
        lead = detect_lead(src)
        clean = os.path.join(adir, f.replace('.wav', '_clean.wav'))
        if os.path.exists(clean):
            lead2 = detect_lead(clean)
            if lead2 <= 0.2:
                results[f] = {'lead': round(lead, 3), 'action': 'already-clean', 'new_lead': round(lead2, 3)}
                print('%s: 已有 clean (前导 %.2fs) 跳过' % (f, lead2))
                continue
        if lead <= 0.2:
            # 无前导静音，直接用原文件作为 clean
            subprocess.run(['ffmpeg','-y','-v','error','-i',src,'-c','copy',clean], capture_output=True, text=True)
            results[f] = {'lead': round(lead, 3), 'action': 'no-lead-copy'}
            print('%s: 无前导静音，复制为 clean' % f)
            continue
        cut = max(0.0, lead - 0.15)
        r = subprocess.run(['ffmpeg','-y','-v','error','-ss',str(cut),'-i',src,'-c','copy',clean], capture_output=True, text=True)
        lead2 = detect_lead(clean)
        r2 = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',clean], capture_output=True, text=True)
        dur = float(r2.stdout.strip())
        results[f] = {'lead': round(lead, 3), 'cut': round(cut, 3), 'new_dur': round(dur, 3), 'new_lead': round(lead2, 3)}
        status = 'OK' if lead2 <= 0.2 else 'STILL HAS LEAD!'
        print('%s: 前导 %.2fs -> 裁 %.2fs, 净 %.2fs, 新前导 %.2fs %s' % (f, lead, cut, dur, lead2, status))

    json.dump(results, open(os.path.join(adir, '..', 'audio_lead_report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('DONE - report: %s' % os.path.join(adir, '..', 'audio_lead_report.json'))

if __name__ == '__main__':
    main()
