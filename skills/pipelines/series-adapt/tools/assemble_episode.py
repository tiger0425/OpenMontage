import json, sys, io, os, shutil
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# assemble_episode.py — series-adapt workspace 组装器
# usage: python assemble_episode.py <sid> <total> <num_scenes> [--ep <ep_dir>] [--bgm <path>]
# 从 {sid}_parts.json 组装 HyperFrames workspace + index.html
# L-032: 无字幕层（干净渲染）
# ============================================================

sid = sys.argv[1]
total = float(sys.argv[2])
num_scenes = int(sys.argv[3])
TMP = r'C:\Users\tiger\AppData\Local\Temp\opencode'
parts = json.load(io.open(os.path.join(TMP, '%s_parts.json' % sid), encoding='utf-8'))

EP = r'E:\YifuAIForge\OpenMontage\projects\series-adapt-99\ep-02'
BGM = None
if '--ep' in sys.argv:
    EP = sys.argv[sys.argv.index('--ep') + 1]
if '--bgm' in sys.argv:
    BGM = sys.argv[sys.argv.index('--bgm') + 1]

ws = os.path.join(EP, 'hyperframes-%s' % sid)
os.makedirs(os.path.join(ws, 'assets', 'sfx'), exist_ok=True)
os.makedirs(os.path.join(ws, 'compositions'), exist_ok=True)

# copy images
src_img = os.path.join(EP, 'assets', 'images')
for i in range(1, num_scenes + 1):
    p = os.path.join(src_img, '%s_%d.png' % (sid, i))
    if os.path.exists(p):
        shutil.copy(p, os.path.join(ws, 'assets'))

# audio (scene narration)
shutil.copy(os.path.join(EP, 'assets', 'audio', '%s.wav' % sid), os.path.join(ws, 'assets', '%s.wav' % sid))
# bgm: from ep01 workspace if not specified
if BGM is None:
    cand = os.path.join(r'E:\YifuAIForge\OpenMontage\projects\series-adapt-99\ep-01\hyperframes-vox\assets\ep01_bgm.mp3')
    if os.path.exists(cand):
        shutil.copy(cand, os.path.join(ws, 'assets', 'bgm.mp3'))
        BGM = 'assets/bgm.mp3'
# sfx: copy from ep01 workspace
sfx_src = r'E:\YifuAIForge\OpenMontage\projects\series-adapt-99\ep-01\hyperframes-vox\assets\sfx'
if os.path.isdir(sfx_src):
    for f in os.listdir(sfx_src):
        if f.endswith('.wav'):
            shutil.copy(os.path.join(sfx_src, f), os.path.join(ws, 'assets', 'sfx'))

io.open(os.path.join(ws, 'hyperframes.json'), 'w', encoding='utf-8').write(
    '{\n  "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",\n'
    '  "registry": "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",\n'
    '  "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"}\n}\n')

css = '''    :root {
      --paper: #D9C9A3;
      --paper-light: #E8DCBE;
      --ink: #1C1917;
      --ink-soft: rgba(28,25,23,0.72);
      --red: #C0392B;
      --mustard: #C4A35A;
      --mono: 'Courier New', 'Courier', monospace;
      --headline: 'Arial Narrow', 'Franklin Gothic Medium', 'Impact', sans-serif;
    }
    @font-face { font-family: 'PingFang SC'; src: local('PingFang SC'); }
    @font-face { font-family: 'Microsoft YaHei'; src: local('Microsoft YaHei'); }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: var(--paper); }
    #root { position: relative; width: 1920px; height: 1080px; overflow: hidden; }
    .clip { position: absolute; inset: 0; }
    .ground { position: absolute; inset: 0; background: radial-gradient(ellipse at 30% 20%, var(--paper-light), transparent 55%), radial-gradient(ellipse at 75% 85%, rgba(120,100,60,0.16), transparent 50%), var(--paper); }
    .grain { position: absolute; inset: 0; pointer-events: none; z-index: 60; background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.09'/%3E%3C/svg%3E"); opacity: 0.55; }
    .board { position: absolute; inset: 0; opacity: 0; }
    .photo { position: absolute; overflow: hidden; box-shadow: 0 12px 30px rgba(60,45,20,0.38); will-change: transform; }
    .photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .tstrip { position: absolute; background: #F1E8D0; border: 1px solid rgba(28,25,23,0.25); box-shadow: 0 4px 12px rgba(60,45,20,0.28); font-family: var(--mono); font-size: 40px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink); padding: 16px 34px; white-space: nowrap; }
    .stamp { position: absolute; font-family: var(--headline); font-weight: 900; font-size: 60px; letter-spacing: 0.14em; color: var(--red); text-transform: uppercase; border: 6px double var(--red); padding: 12px 30px; opacity: 0.88; transform: rotate(-7deg); mix-blend-mode: multiply; z-index: 8; }
    .pin { position: absolute; width: 30px; height: 30px; border-radius: 50%; background: radial-gradient(circle at 35% 30%, #E8C56A, #A87B2F 70%); box-shadow: 0 3px 8px rgba(60,45,20,0.5), inset 0 -2px 4px rgba(0,0,0,0.3); z-index: 5; }
    .headline { position: absolute; font-family: var(--headline); font-weight: 900; color: var(--ink); line-height: 0.95; letter-spacing: -0.01em; text-transform: uppercase; z-index: 8; }
    .cap-sub { position: absolute; font-family: var(--mono); font-size: 28px; font-weight: 700; letter-spacing: 0.28em; text-transform: uppercase; color: var(--ink-soft); }
    .meta { position: absolute; top: 46px; left: 80px; right: 80px; z-index: 40; display: flex; justify-content: space-between; font-family: var(--mono); font-size: 22px; letter-spacing: 0.24em; color: rgba(28,25,23,0.55); text-transform: uppercase; }
    .cover { position: absolute; inset: 0; background: #17130C; opacity: 0; pointer-events: none; z-index: 96; }
    .fg-frame { position: absolute; inset: 0; pointer-events: none; z-index: 30; }
    .fg-frame::before, .fg-frame::after { content: ''; position: absolute; background: linear-gradient(135deg, transparent 45%, var(--paper) 50%, transparent 55%); }
    .fg-frame::before { top: 0; left: 0; width: 260px; height: 260px; border-top: 34px solid var(--paper); border-left: 34px solid var(--paper); }
    .fg-frame::after { bottom: 0; right: 0; width: 260px; height: 260px; border-bottom: 34px solid var(--paper); border-right: 34px solid var(--paper); }
    .fg-vig { position: absolute; inset: 0; pointer-events: none; z-index: 31; background: radial-gradient(ellipse at center, transparent 52%, rgba(23,19,12,0.55) 100%); }
    .fg-band { position: absolute; left: 0; right: 0; bottom: 0; height: 150px; z-index: 32; background: linear-gradient(to top, rgba(23,19,12,0.5), transparent); }
    .hl-bar { position: absolute; width: 340px; height: 22px; background: var(--red); z-index: 33; }
    .paper-cut { position: absolute; background: var(--paper-light); border: 1px solid rgba(28,25,23,0.2); box-shadow: 0 8px 20px rgba(60,45,20,0.3); }
    .paper-card { position: absolute; background: var(--paper-light); border: 1px solid rgba(28,25,23,0.22); box-shadow: 0 10px 24px rgba(60,45,20,0.32); }
    .headline-in { font-family: var(--headline); font-weight: 900; color: var(--ink); text-transform: uppercase; line-height: 1.05; }
    .cap-in { font-family: var(--mono); font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-soft); }
    .photo.small { box-shadow: 0 6px 16px rgba(60,45,20,0.3); }
    .string { position: absolute; pointer-events: none; z-index: 34; }
'''

html = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=1920, height=1080" />
  <title>Iron Dragon - %s (Vox Paper Collage)</title>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
''' % sid.upper() + css + '''  </style>
</head>
<body>
<div id="root" data-composition-id="main" data-width="1920" data-height="1080" data-duration="%.1f" data-start="0">

''' % total

if BGM:
    html += '''  <audio id="bgm" src="assets/bgm.mp3" data-start="0" data-volume="0.13">
    <track kind="captions" label="Music" />
  </audio>
'''
html += '''  <audio id="vo" src="assets/%s.wav" data-start="3">
    <track kind="captions" label="Narration" />
  </audio>

''' % sid

html += parts['sfx_html'] + '''

  <div class="ground"></div>
  <div class="grain"></div>
  <div class="meta"><span>99 MEMOIRS · EP.02</span><span>THE ONE-ARMED HERO</span></div>

''' + parts['scenes_html'] + '''

  <div class="cover" id="cover"></div>
</div>

<script>
window.__timelines = window.__timelines || {};
var tl = gsap.timeline({ paused: true });

''' + parts['js_body'] + '''

window.__timelines["main"] = tl;
</script>
</body>
</html>
'''

io.open(os.path.join(ws, 'index.html'), 'w', encoding='utf-8').write(html)
print('%s workspace ready: %s (%.1fs)' % (sid, ws, total))
