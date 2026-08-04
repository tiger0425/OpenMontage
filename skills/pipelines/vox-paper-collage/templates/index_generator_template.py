"""Generate HyperFrames index.html for jiaozi-paper-money-1024 — alibaba-qwen38 pattern.

Structure per scene:
  <section class="clip" data-start data-duration data-track-index={alternating}>
    <div class="board" id="bd-sN">   (CSS opacity:0)
      bgimg / cutout hero / cutout l3 / headline / stamp / tstrip / tape / pin / string
    </div>
  </section>

Timing rules (alibaba pattern):
  - board cross-dissolve: prev fades out end-0.45s, next fades in start-0.4s (0.5s overlap, alternating tracks)
  - bg: scene_start + 0.1
  - HERO: scene_start + 0.3 (ALWAYS immediate, never voice-bound) + slow breathe to scale 1.05
  - l3: scene_start + 1.2 (fixed, no voice wait)
  - decor: staggered scene_start + 2.0..4.5
  - KEY voice elements (headline/stamp carrying the sentence's number): at sentence time + 0.2 (voice-driven)
  - SHORT scenes (<=6.5s): everything fast (hero 0.3, l3 0.8, decor 1.3-2.5) so nothing vanishes
  - All entrance anims: fromTo, duration 0.6-1.2, power2/3.out; tape/pin scale 0->1 0.3s
"""
import json

ROOT = r"E:\YifuAIForge\OpenMontage\projects\jiaozi-paper-money-1024"

sp = json.load(open(f"{ROOT}\\artifacts\\scene_plan.json", encoding="utf-8"))
ts = json.load(open(f"{ROOT}\\assets\\audio\\timestamps.json", encoding="utf-8"))
scenes = sp["scenes"]

W, H = 1920, 1080

# hero image aspect ratios (w/h) — used by LAYOUT R2 (height >= 55% canvas)
_hero_ratios = {
    "sc1_hero_basket.png": 1.24, "sc2_hero_merchant.png": 0.72, "sc3_hero_contract.png": 1.46,
    "sc4_hero_zhangyong.png": 0.96, "sc5_hero_jiaozi_stack.png": 1.34, "sc6_hero_encyclopedia.png": 1.09,
    "sc7_hero_imperial_seal.png": 1.02, "sc8_hero_europe_map.png": 1.18, "sc9_hero_swedish_coin.png": 1.04,
    "sc10_hero_signature.png": 1.59, "sc11_hero_phone_qr.png": 0.54, "sc12_hero_burnt.png": 1.21,
}

# scene content specs: bg, hero{src,w,x,y}, l3{src,w,x,y}, voice{selector,text,kind,pos,font}, decor[]
scene_specs = {
    "sc1": dict(
        bg="bg_news.png",
        hero=dict(src="sc1_hero_basket.png", w=818, x=960, y=190),
        l3=dict(src="sc1_l3_scale_weight.png", w=300, x=1459, y=600),
        voice=dict(text="3.5KG", kind="stamp", x=240, y=150, size=72),
        decor=[
            dict(kind="tstrip", text="益州 · 1024年", x=120, y=900, size=44),
            dict(kind="tape", x=300, y=390),
            dict(kind="tape", x=1240, y=720),
        ],
    ),
    "sc2": dict(
        bg="bg_graph.png",
        hero=dict(src="sc2_hero_merchant.png", w=475, x=960, y=190),
        l3=dict(src="sc2_l3_rice.png", w=300, x=1287, y=600),
        voice=dict(text="一贯 = 770文 ≈ 3.5公斤", kind="headline", x=120, y=140, size=86),
        decor=[
            dict(kind="tstrip", text="月收入约 30 斤", x=120, y=880, size=44),
            dict(kind="pin", x=1580, y=180),
            dict(kind="tape", x=1200, y=200),
        ],
    ),
    "sc3": dict(
        bg="bg_ledger.png",
        hero=dict(src="sc3_hero_contract.png", w=900, x=960, y=190),
        l3=dict(src="sc3_l3_red_seal.png", w=280, x=1490, y=600),
        voice=dict(text="16 户联保", kind="headline", x=140, y=150, size=110),
        decor=[
            dict(kind="tstrip", text="最早的众筹保险", x=140, y=900, size=48),
            dict(kind="string", x1=320, y1=760, x2=1520, y2=760),
            dict(kind="tape", x=1180, y=200),
        ],
    ),
    "sc4": dict(
        bg="bg_news.png",
        hero=dict(src="sc4_hero_zhangyong.png", w=634, x=960, y=190),
        l3=dict(src="sc4_l3_scroll.png", w=360, x=1397, y=600),
        voice=dict(text="世界第一个官方纸币机构", kind="headline", x=140, y=140, size=84),
        decor=[
            dict(kind="stamp", text="天圣二年", x=240, y=250, size=64),
            dict(kind="tstrip", text="益州知府 · 张咏", x=140, y=880, size=44),
            dict(kind="tape", x=1240, y=250),
        ],
    ),
    "sc5": dict(
        bg="bg_ledger.png",
        hero=dict(src="sc5_hero_jiaozi_stack.png", w=884, x=960, y=190),
        l3=dict(src="sc5_l3_numeral.png", w=340, x=1512, y=600),
        voice=None,
        decor=[
            dict(kind="tstrip", text="每界发行量 · 三年一换", x=140, y=150, size=44),
            dict(kind="tape", x=300, y=720),
        ],
    ),
    "sc6": dict(
        bg="bg_ancient.png",
        hero=dict(src="sc6_hero_encyclopedia.png", w=719, x=960, y=190),
        l3=dict(src="sc6_l3_range.png", w=320, x=1419, y=600),
        voice=dict(text="《文献通考》记载", kind="tstrip", x=140, y=150, size=44),
        decor=[
            dict(kind="tstrip", text="100-150万贯之间", x=140, y=900, size=44),
            dict(kind="tape", x=1200, y=220),
        ],
    ),
    "sc7": dict(
        bg="bg_news.png",
        hero=dict(src="sc7_hero_imperial_seal.png", w=673, x=960, y=190),
        l3=dict(src="sc7_l3_merchant_seal.png", w=260, x=1366, y=600),
        voice=dict(text="朝廷", kind="stamp", x=260, y=150, size=80),
        decor=[
            dict(kind="stamp", text="私商", x=1410, y=140, size=60),
            dict(kind="string", x1=620, y1=520, x2=1360, y2=600),
        ],
    ),
    "sc8": dict(
        bg="bg_nautical.png",
        hero=dict(src="sc8_hero_europe_map.png", w=779, x=960, y=190),
        l3=dict(src="sc8_l3_scale_coins.png", w=320, x=1449, y=600),
        voice=dict(text="与此同时，欧洲在…", kind="headline", x=140, y=150, size=80),
        decor=[
            dict(kind="tape", x=220, y=760),
        ],
    ),
    "sc9": dict(
        bg="bg_nautical.png",
        hero=dict(src="sc9_hero_swedish_coin.png", w=686, x=960, y=190),
        l3=dict(src="sc9_l3_timeline.png", w=420, x=1453, y=600),
        voice=dict(text="637年", kind="stamp", x=140, y=420, size=80),
        decor=[
            dict(kind="headline", text="1661 · 瑞典", x=140, y=150, size=96),
            dict(kind="tape", x=280, y=760),
        ],
    ),
    "sc10": dict(
        bg="bg_news.png",
        hero=dict(src="sc10_hero_signature.png", w=950, x=960, y=190),
        l3=dict(src="sc10_l3_seals.png", w=280, x=1490, y=600),
        voice=dict(text="最早的防伪密码", kind="tstrip", x=140, y=150, size=44),
        decor=[
            dict(kind="tape", x=1380, y=220),
            dict(kind="pin", x=300, y=700),
        ],
    ),
    "sc11": dict(
        bg="bg_news.png",
        hero=dict(src="sc11_hero_phone_qr.png", w=356, x=960, y=190),
        l3=dict(src="sc11_l3_then_now.png", w=320, x=1238, y=600),
        voice=dict(text="一千年后", kind="headline", x=140, y=150, size=100),
        decor=[
            dict(kind="tstrip", text="成都街头 · 扫码支付", x=140, y=880, size=44),
            dict(kind="string", x1=760, y1=680, x2=1340, y2=640),
        ],
    ),
    "sc12": dict(
        bg="bg_news.png",
        hero=dict(src="sc12_hero_burnt.png", w=799, x=960, y=190),
        l3=dict(src="sc12_l3_questions.png", w=280, x=1439, y=600),
        voice=dict(text="至今没有定论", kind="stamp", x=140, y=880, size=72),
        decor=[
            dict(kind="headline", text="通货膨胀？伪造？战争？", x=140, y=150, size=84),
            dict(kind="tape", x=300, y=720),
        ],
    ),
}

def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

tl = []
sections = []
boards = []
tracks = []

for idx, sc in enumerate(scenes):
    sid = sc["id"]
    spec = scene_specs[sid]
    start = sc["start_seconds"]
    dur = sc["end_seconds"] - sc["start_seconds"]
    end = sc["end_seconds"]
    short = dur <= 7.0

    # ============================================================
    # LAYOUT HARD RULES (engine requirements, enforced by assert —
    #   violation ABORTS generation. Do NOT relax these.)
    #   source: scene-plan-director.md — hero 60% visual weight,
    #   centered & dominant; elements MUST overlap (叠压) not tile.
    # ============================================================
    h = spec["hero"]
    assert abs(h["x"] - W // 2) <= 20, (
        f"[LAYOUT-FAIL] {sid}: hero x={h['x']} not centered (canvas center={W//2}). "
        "Engine rule: hero is the dominant focal element, must be centered."
    )
    hero_h = h["w"] / _hero_ratios.get(h["src"], 1.0)
    assert hero_h >= 0.55 * H, (
        f"[LAYOUT-FAIL] {sid}: hero height {hero_h:.0f}px < 55% of canvas ({0.55*H:.0f}px). "
        "Engine rule: hero must dominate the frame (~60% visual weight)."
    )
    l3 = spec["l3"]
    hero_left, hero_right = h["x"] - h["w"] // 2, h["x"] + h["w"] // 2
    l3_left, l3_right = l3["x"] - l3["w"] // 2, l3["x"] + l3["w"] // 2
    overlap_x = min(hero_right, l3_right) - max(hero_left, l3_left)
    assert overlap_x > 0, (
        f"[LAYOUT-FAIL] {sid}: l3 ({l3['x']}) does not overlap hero ({h['x']}). "
        "Engine rule: elements must overlap (叠压, tape/stamp crossing), not tile flat."
    )
    assert hero_left >= 0 and hero_right <= W, (
        f"[LAYOUT-FAIL] {sid}: hero [{hero_left},{hero_right}] out of canvas (0..{W})."
    )

    # alternating tracks: 0,1,0,1...
    track = idx % 2

    # ----- element timing -----
    # HERO always immediate: start + 0.3 (short scene: +0.2)
    hero_t = start + (0.2 if short else 0.3)
    # L3: short -> +0.8, normal -> +1.2
    l3_t = start + (0.8 if short else 1.2)
    # voice element: normal scenes land with a sentence (voice-driven) but must stay
    # visible >= 2.5s (never at scene tail). SHORT scenes land early always.
    segs = [s for s in ts["segments"] if start - 0.1 <= s["start"] < end + 0.1]
    if spec.get("voice"):
        if short:
            v_t = start + 1.2
        elif segs:
            # prefer a mid/late sentence but cap at end - 2.5 so it stays visible
            cand = min(segs[-1]["start"] + 0.2, end - 2.5)
            # never earlier than l3 (visual layering), never before start + 1.5
            v_t = max(cand, start + 1.5)
        else:
            v_t = start + 2.5
    else:
        v_t = start + (1.5 if short else 2.5)
    # decor: staggered from start + 2.0 (short: +1.3)
    d_base = start + (1.3 if short else 2.0)

    # ----- DOM -----
    els = []
    els.append(f'<div class="bgimg" id="{sid}-bg"><img src="assets/{spec["bg"]}" alt="" /></div>')

    h = spec["hero"]
    els.append(f'<div class="cutout" id="{sid}-hero" style="left:{h["x"] - h["w"]//2}px;top:{h["y"]}px;width:{h["w"]}px;transform:rotate(-2deg);"><img src="assets/{h["src"]}" alt="" /></div>')

    l3 = spec["l3"]
    els.append(f'<div class="cutout" id="{sid}-l3" style="left:{l3["x"] - l3["w"]//2}px;top:{l3["y"]}px;width:{l3["w"]}px;transform:rotate(2deg);"><img src="assets/{l3["src"]}" alt="" /></div>')

    if spec.get("voice"):
        v = spec["voice"]
        kind = v["kind"]
        style = f'left:{v["x"]}px;top:{v["y"]}px;font-size:{v.get("size", 64)}px;'
        if kind == "stamp":
            style += "transform:rotate(-7deg);"
        els.append(f'<div class="{kind}" id="{sid}-voice" style="{style}">{esc(v["text"])}</div>')

    for i, d in enumerate(spec["decor"]):
        cid = f"{sid}-dec{i}"
        kind = d["kind"]
        style = f'left:{d.get("x", 0)}px;top:{d.get("y", 0)}px;'
        if kind == "string":
            x1, y1 = d.get("x1", 0), d.get("y1", 0)
            x2, y2 = d.get("x2", 0), d.get("y2", 0)
            style = f'left:{x1}px;top:{y1}px;width:{max(10, x2 - x1)}px;height:3px;transform-origin:left center;'
        elif kind in ("tape", "pin"):
            style += f'transform:rotate({-8 + i * 4}deg);'
        text = esc(d.get("text", "")) if d.get("text") else ""
        els.append(f'<div class="{kind}" id="{cid}" style="{style}">{text}</div>')

    sections.append(
        f'<section class="clip" id="scene-{sid}" data-start="{start:.2f}" data-duration="{dur:.2f}" data-track-index="{track}">\n'
        f'  <div class="board" id="bd-{sid}">\n' + "\n".join("    " + e for e in els) + "\n  </div>\n</section>"
    )

    # ----- GSAP -----
    # board dissolve: fade in at start-0.4 (overlap prev), fade out end-0.45
    fade_in_at = max(0.0, start - 0.4)
    tl.append(f'tl.fromTo("#bd-{sid}", {{opacity:0}}, {{opacity:1, duration:0.5, ease:"power1.out"}}, {fade_in_at:.2f});')
    tl.append(f'tl.to("#bd-{sid}", {{opacity:0, duration:0.45, ease:"power1.in"}}, {end - 0.45:.2f});')
    tl.append(f'tl.set("#bd-{sid}", {{opacity:0}}, {end:.2f});')

    # bg
    tl.append(f'tl.fromTo("#{sid}-bg", {{opacity:0}}, {{opacity:1, duration:0.6, ease:"power1.out"}}, {start + 0.1:.2f});')

    # HERO (immediate, drop-in)
    tl.append(f'tl.fromTo("#{sid}-hero", {{y:-90, opacity:0}}, {{y:0, opacity:1, duration:{1.0 if short else 1.2}, ease:"power2.out"}}, {hero_t:.2f});')
    # hero slow breathe to end (living poster)
    breathe_dur = max(0.5, end - 0.3 - (hero_t + 1.2))
    tl.append(f'tl.to("#{sid}-hero", {{scale:1.05, duration:{breathe_dur:.2f}, ease:"power1.inOut"}}, {hero_t + 1.2:.2f});')

    # L3
    tl.append(f'tl.fromTo("#{sid}-l3", {{y:60, opacity:0}}, {{y:0, opacity:1, duration:{0.8 if short else 1.0}, ease:"power2.out"}}, {l3_t:.2f});')

    # voice element
    if spec.get("voice"):
        v = spec["voice"]
        if v["kind"] == "stamp":
            tl.append(f'tl.fromTo("#{sid}-voice", {{scale:2.2, opacity:0, rotate:-14}}, {{scale:1, opacity:1, rotate:-7, duration:0.7, ease:"power3.out"}}, {v_t:.2f});')
        elif v["kind"] == "headline":
            tl.append(f'tl.fromTo("#{sid}-voice", {{x:-70, opacity:0}}, {{x:0, opacity:1, duration:0.7, ease:"power3.out"}}, {v_t:.2f});')
        else:  # tstrip
            tl.append(f'tl.fromTo("#{sid}-voice", {{x:70, opacity:0}}, {{x:0, opacity:1, duration:0.7, ease:"power2.out"}}, {v_t:.2f});')

    # decor
    for i, d in enumerate(spec["decor"]):
        cid = f"{sid}-dec{i}"
        t = min(d_base + i * 0.5, end - 0.6)
        kind = d["kind"]
        if kind == "string":
            tl.append(f'tl.fromTo("#{cid}", {{scaleX:0, opacity:0}}, {{scaleX:1, opacity:1, duration:0.8, ease:"power2.out"}}, {t:.2f});')
        elif kind == "stamp":
            tl.append(f'tl.fromTo("#{cid}", {{scale:2.0, opacity:0, rotate:-14}}, {{scale:1, opacity:1, rotate:-7, duration:0.6, ease:"power3.out"}}, {t:.2f});')
        else:  # tape / pin / tstrip / headline
            tl.append(f'tl.fromTo("#{cid}", {{scale:0, opacity:0}}, {{scale:1, opacity:1, duration:0.35, ease:"power2.out"}}, {t:.2f});')

# ----- audio (narration) -----
sec_dur = {
    "s1": 10.774, "s2": 11.738, "s3": 16.048, "s4": 2.531,
    "s5": 13.819, "s6": 16.825, "s7": 7.187, "s8": 12.460,
    "s9": 6.339, "s10": 8.777, "s11": 8.557,
}
script = json.load(open(f"{ROOT}\\artifacts\\script.json", encoding="utf-8"))
sec_start = {}
cursor = 0.0
for s in script["sections"]:
    sec_start[s["id"]] = cursor
    cursor += sec_dur[s["id"]]

audio_blocks = []
for i, s in enumerate(script["sections"], 1):
    audio_blocks.append(
        f'<audio id="nar-{i:02d}" src="assets/seg_{i:02d}.wav" data-start="{sec_start[s["id"]]:.2f}"></audio>'
    )

# ----- sfx (paper ASMR at key entrances) -----
sfx_plan = [
    (0.40, "paper_slide"), (1.20, "paper_tap"), (3.20, "stamp_thud"),
    (11.30, "paper_slide"), (12.40, "paper_tap"), (13.60, "stamp_thud"),
    (23.30, "paper_slide"), (24.40, "tape_press"), (25.60, "stamp_thud"),
    (42.00, "paper_slide"), (43.20, "paper_tap"), (45.00, "stamp_thud"),
    (56.00, "paper_slide"), (57.20, "paper_tap"),
    (61.50, "paper_slide"), (62.70, "paper_tap"), (64.00, "stamp_thud"),
    (72.50, "stamp_thud"), (74.00, "pin_click"),
    (79.80, "paper_slide"), (81.00, "paper_tap"),
    (84.00, "paper_slide"), (85.50, "paper_tap"), (87.50, "stamp_thud"),
    (92.30, "paper_slide"), (93.60, "paper_tap"),
    (98.50, "paper_slide"), (100.00, "string_zip"),
    (107.30, "paper_slide"), (108.60, "paper_tap"), (110.50, "stamp_thud"),
]
sfx_blocks = []
for t, name in sfx_plan:
    sfx_blocks.append(f'<audio id="sfx-{t:.1f}" src="assets/sfx/{name}.mp3" data-start="{t:.2f}" data-volume="0.28"></audio>')

# ----- assemble -----
html = f"""<!doctype html>
<html lang="zh">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width={W}, height={H}" />
  <title>北宋交子起源全记录 · 中文历史纪录片</title>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <style>
    :root {{
      --paper: #D8C7A3;
      --paper-light: #E8DCBE;
      --ink: #1A1A1A;
      --ink-soft: rgba(26,25,23,0.72);
      --red: #C33B2E;
      --mustard: #D4A83D;
      --mono: 'Courier New', 'Courier', monospace;
      --headline: 'Arial Narrow', 'Franklin Gothic Medium', 'Impact', sans-serif;
    }}
    @font-face {{ font-family: 'PingFang SC'; src: local('PingFang SC'); }}
    @font-face {{ font-family: 'Microsoft YaHei'; src: local('Microsoft YaHei'); }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: var(--paper); }}
    #root {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; }}
    .clip {{ position: absolute; inset: 0; }}

    .grain {{
      position: absolute; inset: 0; pointer-events: none; z-index: 60;
      background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.09'/%3E%3C/svg%3E");
      opacity: 0.5;
    }}

    .board {{ position: absolute; inset: 0; opacity: 0; }}
    .bgimg {{ position: absolute; inset: 0; }}
    .bgimg img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    .cutout {{
      position: absolute;
      will-change: transform;
      filter: drop-shadow(0 14px 24px rgba(60,45,20,0.35));
    }}
    .cutout img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}

    .tape {{
      position: absolute; width: 150px; height: 40px;
      background: rgba(212,168,61,0.40);
      box-shadow: 0 2px 6px rgba(60,45,20,0.25);
      opacity: 0.9;
    }}
    .tstrip {{
      position: absolute;
      background: #F1E8D0;
      border: 2px solid rgba(26,25,23,0.35);
      box-shadow: 0 6px 16px rgba(60,45,20,0.30);
      font-family: var(--mono);
      font-size: 44px; font-weight: 700;
      letter-spacing: 0.06em;
      color: var(--ink);
      padding: 16px 30px;
      white-space: nowrap;
    }}
    .stamp {{
      position: absolute;
      font-family: 'PingFang SC', 'Microsoft YaHei', var(--headline);
      font-weight: 900; font-size: 68px; letter-spacing: 0.12em;
      color: var(--red);
      border: 7px double var(--red);
      padding: 14px 32px;
      opacity: 0.88;
      transform: rotate(-7deg);
      mix-blend-mode: multiply;
      white-space: nowrap;
    }}
    .pin {{
      position: absolute; width: 30px; height: 30px;
      border-radius: 50%;
      background: radial-gradient(circle at 35% 30%, #E8C56A, #A87B2F 70%);
      box-shadow: 0 3px 8px rgba(60,45,20,0.5), inset 0 -2px 4px rgba(0,0,0,0.3);
      z-index: 5;
    }}
    .headline {{
      position: absolute;
      font-family: 'PingFang SC', 'Microsoft YaHei', var(--headline);
      font-weight: 900;
      color: var(--ink);
      line-height: 1.05;
      letter-spacing: 0.02em;
      text-shadow: 0 3px 0 rgba(255,255,255,0.5), 0 6px 18px rgba(60,45,20,0.25);
      white-space: nowrap;
    }}
    .string {{
      position: absolute; height: 3px;
      background: var(--red);
      border-radius: 2px;
    }}
  </style>
</head>
<body>
<div id="root" data-composition-id="main" data-width="{W}" data-height="{H}" data-duration="115.05" data-start="0">

  <!-- NARRATION -->
{chr(10).join("  " + a for a in audio_blocks)}

  <!-- SFX -->
{chr(10).join("  " + a for a in sfx_blocks)}

  <div class="grain"></div>

{chr(10).join(sections)}

</div>

<script>
window.__timelines = window.__timelines || {{}};
var tl = gsap.timeline({{ paused: true }});

{chr(10).join(tl)}

window.__timelines["main"] = tl;
</script>
</body>
</html>
"""

out = f"{ROOT}\\hyperframes\\index.html"
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"index.html written: {len(html)} chars, {len(sections)} scenes, {len(tl)} tweens")
