import json, sys, io, glob, re, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# build_episode_parts.py — series-adapt 参数化场景生成器 v3
# usage: python build_episode_parts.py <sid> <num_scenes> <total> [<fams...>] [--ep <ep_dir>]
# 规则编码: L-009 连续窗口 / L-010 连续微动效 / L-027 构成族
#          / L-028 12fps 签名 / L-029 whip 缓动 / L-030 故事转场
#          / L-031 切在运动峰值 / L-032 NO burned-in subtitles
#          / L-036 每分镜独立构成族（相邻不同）
# ============================================================

sid = sys.argv[1]
num = int(sys.argv[2])
total = float(sys.argv[3])
fams = sys.argv[4].split(',') if len(sys.argv) > 4 and not sys.argv[4].startswith('--') else []
if len(sys.argv) > 5 and sys.argv[5] == '--ep':
    EP = sys.argv[6]
else:
    EP = r'E:\YifuAIForge\OpenMontage\projects\series-adapt-99\ep-02'
TMP = r'C:\Users\tiger\AppData\Local\Temp\opencode'

windows = json.load(open(os.path.join(TMP, '%s_windows.json' % sid)))
W = {i+1: w for i, w in enumerate(windows)}

design = {}
dpath = os.path.join(TMP, '%s_design.json' % sid)
if os.path.exists(dpath):
    design = json.load(open(dpath, encoding='utf-8'))

def d(idx, key, default=''):
    s = str(idx)
    if s in design and key in design[s]:
        return design[s][key]
    return default

# 真结构差异的构成族池（L-036 v2: 无左图右文系列；quadrant-grid 因 4 图引用易重复已移除）
FAMILIES = ['full-bleed', 'letterbox', 'top-title-cascade', 'blueprint-draw', 'diagonal-split', 'diagonal-split-rev']

if not fams:
    design_fams = [d(i+1, 'family') for i in range(num)]
    if all(design_fams):
        fams = design_fams
    else:
        fams = [FAMILIES[(i) % len(FAMILIES)] for i in range(num)]
if len(fams) == 1:
    fams = [FAMILIES[(i) % len(FAMILIES)] for i in range(num)]
if len(fams) != num:
    print('ERROR (L-036): %d families for %d sub-shots — must be 1 family PER sub-shot, adjacent different.' % (len(fams), num))
    sys.exit(1)
for i in range(1, num):
    if fams[i] == fams[i-1]:
        print('ERROR (L-036): sub-shots %d and %d share composition family %s — adjacent sub-shots MUST differ.' % (i, i+1, fams[i]))
        sys.exit(1)

# ===== 构成族构建器 v3（结构真不同的 6 种）=====
def build_scene(idx, fam):
    w = W[idx]
    img = '%s_%d.png' % (sid, idx)
    label = d(idx, 'label', 'SCENE %d' % idx)
    cap = d(idx, 'cap', '')
    track = 1 + (idx % 2)
    els = []
    if fam == 'full-bleed':
        els.append('      <div class="photo" id="p%d" style="left:0;top:0;width:1920px;height:1080px;">\n        <img src="assets/%s" alt="scene %d" />\n      </div>' % (idx, img, idx))
        els.append('      <div class="fg-frame" id="fg%d"></div>' % idx)
        els.append('      <div class="fg-vig" id="vig%d"></div>' % idx)
        els.append('      <div class="fg-band" id="band%d"></div>' % idx)
        els.append('      <div class="headline" id="h%d" style="left:120px;bottom:130px;font-size:96px;max-width:1400px;">%s</div>' % (idx, label))
        els.append('      <div class="hl-bar" id="bar%d"></div>' % idx)
        if cap:
            els.append('      <div class="cap-sub" id="c%d" style="left:124px;bottom:64px;">%s</div>' % (idx, cap))
        els.append('      <div class="pin" id="n%d" style="left:1700px;top:160px;"></div>' % idx)
        els.append('      <div class="pin" id="n%d" style="left:300px;top:820px;"></div>' % (idx+50))
    elif fam == 'letterbox':
        els.append('      <div class="photo" id="p%d" style="left:0;top:290px;width:1920px;height:500px;">\n        <img src="assets/%s" alt="scene %d" />\n      </div>' % (idx, img, idx))
        els.append('      <div class="fg-strip" id="fg%d" style="left:0;top:0;width:1920px;height:220px;"></div>' % idx)
        els.append('      <div class="fg-strip" id="fg%d" style="left:0;bottom:0;width:1920px;height:120px;"></div>' % (idx+100))
        els.append('      <div class="headline" id="h%d" style="left:140px;top:60px;font-size:56px;">%s</div>' % (idx, label))
        if cap:
            els.append('      <div class="cap-sub" id="c%d" style="left:140px;top:150px;">%s</div>' % (idx, cap))
        els.append('      <div class="pin" id="n%d" style="left:1750px;top:320px;"></div>' % idx)
    elif fam == 'top-title-cascade':
        els.append('      <div class="photo" id="p%d" style="left:320px;top:200px;width:1280px;height:420px;">\n        <img src="assets/%s" alt="scene %d" />\n      </div>' % (idx, img, idx))
        els.append('      <div class="headline" id="h%d" style="left:320px;top:80px;font-size:56px;">%s</div>' % (idx, label))
        if cap:
            els.append('      <div class="cap-sub" id="c%d" style="left:320px;top:150px;">%s</div>' % (idx, cap))
        for s in range(3):
            els.append('      <div class="tstrip" id="st%d_%d" style="left:%dpx;top:%dpx;transform:rotate(%ddeg);">ITEM %d</div>' % (idx, s, 260 + s*420, 700 + s*40, -1 + s, s+1))
        els.append('      <div class="pin" id="n%d" style="left:1750px;top:140px;"></div>' % idx)
    elif fam == 'blueprint-draw':
        els.append('      <div class="photo" id="p%d" style="left:0;top:180px;width:1920px;height:760px;">\n        <img src="assets/%s" alt="scene %d" />\n      </div>' % (idx, img, idx))
        els.append('      <svg class="string" id="bl%d" style="left:0;top:0;width:1920px;height:1080px;" viewBox="0 0 1920 1080"><path id="bl%d-p" d="M 120 940 L 1800 940" fill="none" stroke="#C0392B" stroke-width="3" stroke-dasharray="1700" stroke-dashoffset="1700"/></svg>' % (idx, idx))
        els.append('      <div class="headline" id="h%d" style="left:120px;top:60px;font-size:56px;">%s</div>' % (idx, label))
        if cap:
            els.append('      <div class="cap-sub" id="c%d" style="left:120px;top:130px;">%s</div>' % (idx, cap))
        els.append('      <div class="pin" id="n%d" style="left:1750px;top:140px;"></div>' % idx)
    elif fam == 'diagonal-split':
        els.append('      <div class="photo" id="p%d" style="left:-120px;top:80px;width:1080px;height:880px;transform:rotate(-5deg);">\n        <img src="assets/%s" alt="scene %d" />\n      </div>' % (idx, img, idx))
        els.append('      <div class="paper-card" id="pc%d" style="left:1100px;top:200px;width:720px;height:640px;transform:rotate(2deg);">\n        <div class="headline-in" style="padding:60px 60px 10px;font-size:52px;">%s</div>\n        <div class="cap-in" style="padding:0 60px;font-size:28px;">%s</div>\n        <div class="tstrip" id="st%d" style="position:absolute;left:60px;top:430px;">REF</div>\n      </div>' % (idx, label, cap or '&nbsp;', idx))
        els.append('      <div class="pin" id="n%d" style="left:1070px;top:160px;"></div>' % idx)
    elif fam == 'diagonal-split-rev':
        els.append('      <div class="photo" id="p%d" style="left:960px;top:80px;width:1080px;height:880px;transform:rotate(5deg);">\n        <img src="assets/%s" alt="scene %d" />\n      </div>' % (idx, img, idx))
        els.append('      <div class="paper-card" id="pc%d" style="left:100px;top:200px;width:720px;height:640px;transform:rotate(-2deg);">\n        <div class="headline-in" style="padding:60px 60px 10px;font-size:52px;">%s</div>\n        <div class="cap-in" style="padding:0 60px;font-size:28px;">%s</div>\n        <div class="tstrip" id="st%d" style="position:absolute;left:60px;top:430px;">REF</div>\n      </div>' % (idx, label, cap or '&nbsp;', idx))
        els.append('      <div class="pin" id="n%d" style="left:850px;top:160px;"></div>' % idx)
    else:
        els.append('      <div class="photo" id="p%d" style="left:300px;top:150px;width:1320px;height:720px;">\n        <img src="assets/%s" alt="scene %d" />\n      </div>' % (idx, img, idx))
        els.append('      <div class="headline" id="h%d" style="left:300px;bottom:80px;font-size:56px;">%s</div>' % (idx, label))
    return ('  <section class="clip" id="scene-%d" data-start="%.2f" data-duration="%.2f" data-track-index="%d">\n'
            '    <div class="board" id="bd-%d">\n%s\n    </div>\n  </section>' % (idx, w['start'], round(w['end']-w['start'],2), track, idx, '\n'.join(els)))

scenes_html = '\n'.join(build_scene(i+1, fams[i]) for i in range(num))

# ===== JS（入场 + L-010 连续微动效）=====
js = []
def t(x): return round(x, 2)
for idx in range(1, num+1):
    w = W[idx]
    js.append('tl.fromTo("#bd-%d", {opacity:0}, {opacity:1, duration:0.5, ease:"power1.out"}, %.2f);' % (idx, t(w['start']+0.05)))
    is_hl = d(idx, 'highlight', False)
    fade_dur = 0.2 if is_hl else 0.45
    js.append('tl.to("#bd-%d", {opacity:0, duration:%.2f, ease:"power1.in"}, %.2f);' % (idx, fade_dur, t(w['end']-fade_dur-0.1)))

for idx in range(1, num+1):
    fam = fams[idx-1]
    w = W[idx]
    st = w['start']; dur = w['end'] - st
    if fam == 'full-bleed':
        js.append('tl.fromTo("#p%d", {scale:1.0, opacity:0}, {scale:1.0, opacity:1, duration:0.55, ease:"power3.out"}, %.2f);' % (idx, t(st+0.2)))
        js.append('tl.to("#p%d", {scale:1.06, duration:%.2f, ease:"power2.inOut"}, %.2f);' % (idx, t(dur-0.8), t(st+0.8)))
        js.append('tl.fromTo("#fg%d", {opacity:0}, {opacity:1, duration:0.8, ease:"power2.out"}, %.2f);' % (idx, t(st+1.0)))
        js.append('tl.fromTo("#vig%d", {opacity:0}, {opacity:1, duration:1.4, ease:"power2.out"}, %.2f);' % (idx, t(st+1.2)))
        js.append('tl.fromTo("#band%d", {y:80, opacity:0}, {y:0, opacity:1, duration:0.8, ease:"power3.out"}, %.2f);' % (idx, t(st+1.6)))
        js.append('tl.fromTo("#h%d", {scale:1.3, opacity:0, x:-40}, {scale:1, opacity:1, x:0, duration:0.45, ease:"power3.out"}, %.2f);' % (idx, t(st+2.0)))
        js.append('tl.fromTo("#bar%d", {scaleX:0, opacity:0}, {scaleX:1, opacity:1, duration:0.5, ease:"power2.inOut"}, %.2f);' % (idx, t(st+2.5)))
        js.append('tl.fromTo("#n%d", {scale:0, opacity:0}, {scale:1, opacity:1, duration:0.3, ease:"power2.out"}, %.2f);' % (idx, t(st+2.8)))
        js.append('tl.fromTo("#n%d", {scale:0, opacity:0}, {scale:1, opacity:1, duration:0.3, ease:"power2.out"}, %.2f);' % (idx+50, t(st+3.1)))
    elif fam == 'letterbox':
        js.append('tl.fromTo("#p%d", {y:200, opacity:0}, {y:0, opacity:1, duration:1.0, ease:"power3.out"}, %.2f);' % (idx, t(st+0.4)))
        js.append('tl.fromTo("#fg%d", {y:-90, opacity:0}, {y:0, opacity:1, duration:0.7, ease:"power3.out"}, %.2f);' % (idx, t(st+0.1)))
        js.append('tl.fromTo("#fg%d", {y:60, opacity:0}, {y:0, opacity:1, duration:0.7, ease:"power3.out"}, %.2f);' % (idx+100, t(st+0.1)))
        js.append('tl.fromTo("#h%d", {opacity:0}, {opacity:1, duration:0.55, ease:"power3.out"}, %.2f);' % (idx, t(st+1.6)))
        js.append('tl.fromTo("#n%d", {scale:0, opacity:0}, {scale:1, opacity:1, duration:0.3, ease:"power2.out"}, %.2f);' % (idx, t(st+2.4)))
    elif fam == 'top-title-cascade':
        js.append('tl.fromTo("#p%d", {opacity:0}, {opacity:1, duration:0.6, ease:"power1.out"}, %.2f);' % (idx, t(st+0.3)))
        js.append('tl.fromTo("#h%d", {x:-60, opacity:0}, {x:0, opacity:1, duration:0.55, ease:"power3.out"}, %.2f);' % (idx, t(st+0.8)))
        for s in range(3):
            js.append('tl.fromTo("#st%d_%d", {scale:1.4, opacity:0}, {scale:1, opacity:1, duration:0.4, ease:"power3.out"}, %.2f);' % (idx, s, t(st+1.6+s*0.5)))
        js.append('tl.fromTo("#n%d", {scale:0, opacity:0}, {scale:1, opacity:1, duration:0.3, ease:"power2.out"}, %.2f);' % (idx, t(st+3.6)))
    elif fam == 'blueprint-draw':
        js.append('tl.fromTo("#p%d", {scale:1.1, opacity:0}, {scale:1.1, opacity:1, duration:0.7, ease:"power2.out"}, %.2f);' % (idx, t(st+0.3)))
        js.append('tl.to("#p%d", {scale:1.0, duration:%.2f, ease:"power2.inOut"}, %.2f);' % (idx, t(dur-1.0), t(st+0.8)))
        js.append('tl.fromTo("#bl%d-p", {strokeDashoffset:1700}, {strokeDashoffset:0, duration:2.5, ease:"power2.inOut"}, %.2f);' % (idx, t(st+1.5)))
        js.append('tl.fromTo("#h%d", {x:-50, opacity:0}, {x:0, opacity:1, duration:0.55, ease:"power3.out"}, %.2f);' % (idx, t(st+2.2)))
        js.append('tl.fromTo("#n%d", {scale:0, opacity:0}, {scale:1, opacity:1, duration:0.3, ease:"power2.out"}, %.2f);' % (idx, t(st+3.2)))
    elif fam == 'diagonal-split':
        js.append('tl.fromTo("#p%d", {x:-120, opacity:0, rotation:-12}, {x:0, opacity:1, rotation:-6, duration:0.9, ease:"power2.inOut"}, %.2f);' % (idx, t(st+0.3)))
        js.append('tl.fromTo("#pc%d", {y:40, opacity:0, rotation:0}, {y:0, opacity:1, rotation:3, duration:0.7, ease:"power3.out"}, %.2f);' % (idx, t(st+1.0)))
        js.append('tl.fromTo("#n%d", {scale:0, opacity:0}, {scale:1, opacity:1, duration:0.3, ease:"power2.out"}, %.2f);' % (idx, t(st+2.2)))
    elif fam == 'diagonal-split-rev':
        js.append('tl.fromTo("#p%d", {x:120, opacity:0, rotation:12}, {x:0, opacity:1, rotation:6, duration:0.9, ease:"power2.inOut"}, %.2f);' % (idx, t(st+0.3)))
        js.append('tl.fromTo("#pc%d", {y:40, opacity:0, rotation:0}, {y:0, opacity:1, rotation:-3, duration:0.7, ease:"power3.out"}, %.2f);' % (idx, t(st+1.0)))
        js.append('tl.fromTo("#n%d", {scale:0, opacity:0}, {scale:1, opacity:1, duration:0.3, ease:"power2.out"}, %.2f);' % (idx, t(st+2.2)))
    else:
        js.append('tl.fromTo("#p%d", {opacity:0}, {opacity:1, duration:0.7, ease:"power2.out"}, %.2f);' % (idx, t(st+0.3)))
        js.append('tl.fromTo("#h%d", {x:50, opacity:0}, {x:0, opacity:1, duration:0.55, ease:"power3.out"}, %.2f);' % (idx, t(st+1.2)))

    # ===== L-010 连续微动效层（入场 settle 后循环到场景结束）=====
    loop_start = st + 3.4
    if dur > 5.5 and loop_start < w['end'] - 1.0:
        remaining = w['end'] - loop_start
        # 照片微动（sway）
        if fam in ('full-bleed', 'letterbox', 'blueprint-draw'):
            cycle = 3.8
            rep = max(0, int((remaining - cycle) // cycle) - 1)
            if rep > 0:
                js.append('tl.to("#p%d", {y:6, rotation:0.3, duration:%.2f, ease:"sine.inOut", yoyo:true, repeat:%d, overwrite:"auto"}, %.2f);' % (idx, cycle/2, rep, t(loop_start)))
        # 标题/标签微动（paper corner lift）
        if fam in ('full-bleed', 'letterbox', 'top-title-cascade', 'blueprint-draw'):
            cycle2 = 2.9
            rep2 = max(0, int((remaining - cycle2) // cycle2) - 1)
            if rep2 > 0:
                js.append('tl.to("#h%d", {rotation:0.7, y:3, duration:%.2f, ease:"sine.inOut", yoyo:true, repeat:%d}, %.2f);' % (idx, cycle2/2, rep2, t(loop_start + 0.3)))
        # 图钉 pulse（full-bleed/letterbox/top-title-cascade 有图钉元素）
        if fam in ('full-bleed', 'letterbox', 'top-title-cascade', 'blueprint-draw'):
            cycle3 = 1.8
            rep3 = max(0, int((remaining - cycle3) // cycle3) - 1)
            if rep3 > 0:
                js.append('tl.to("#n%d", {scale:1.12, duration:%.2f, ease:"sine.inOut", yoyo:true, repeat:%d}, %.2f);' % (idx, cycle3/2, rep3, t(loop_start + 0.6)))

js_body = '\n'.join(js)

# SFX
sfx_events = []
for m in re.finditer(r'tl\.(?:fromTo|to)\("#([\w-]+)",\s*\{[^}]*\},\s*\{[^}]*\},\s*([\d.]+)\)', js_body):
    sel, at = m.group(1), float(m.group(2))
    if sel.startswith('bd-'): continue
    sfx_events.append((at, sel))
sfx_events.sort(key=lambda e: e[0])
def sfx_for(sel):
    if sel.startswith('p') or sel.startswith('g'): return 'paper_slide'
    if sel.startswith('h') or sel.startswith('c'): return 'tape_press'
    if sel.startswith('n'): return 'pin_click'
    if 'line' in sel or sel.startswith('ln') or sel.startswith('bl') or sel.startswith('gr'): return 'string_zip'
    if sel.startswith('st'): return 'tape_press'
    if sel.startswith('fg') or sel.startswith('pc'): return 'paper_tap'
    return 'paper_tap'
sfx_tags = []
seen = set()
for at, sel in sfx_events:
    if sel in seen: continue
    seen.add(sel)
    sfx_tags.append('  <audio id="sfx%d" src="assets/sfx/%s.wav" data-start="%.2f" data-volume="0.28">\n    <track kind="captions" label="SFX" />\n  </audio>' % (len(sfx_tags)+1, sfx_for(sel), at))
sfx_html = '\n'.join(sfx_tags)

# L-032: NO burned-in subtitles
io.open(os.path.join(TMP, '%s_parts.json' % sid), 'w', encoding='utf-8').write(json.dumps({
    'scenes_html': scenes_html, 'js_body': js_body, 'sfx_html': sfx_html,
    'subs_html': '', 'sub_js': '',
    'total': total, 'fams': fams,
}))
print('%s parts: %d scenes, fams=%s, %d js, %d sfx, total %.1f' % (sid, num, ','.join(fams), len(js_body.split(chr(10))), len(sfx_tags), total))
