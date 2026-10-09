#!/usr/bin/env python3
"""WRC 竖屏合成生成器（prototype v1，用于 wayfinder #65 验收）

输入: 集脚本 JSON（wrc_episode.schema.json 契约 + 每幕 display 块 + visuals[].asset_path + audio_s）
输出: hyperframes@0.7.109 兼容的 index.html（1080x1920 竖屏）

用法:
    python generate_composition.py <episode.json> <assets_dir> <out_index.html>
"""
import json, sys, os

# ---------------------------------------------------------------- helpers
def hf_id(prefix):
    hf_id.n += 1
    return f"hf-{prefix}-{hf_id.n}"
hf_id.n = 0

def esc(s):
    s = str(s)
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def el(tag, attrs, style=None, inner="", cls=None, hid=None):
    a = [f'{k}="{v}"' for k, v in attrs.items()]
    if style:
        a.append(f'style="{style}"')
    if cls:
        a.append(f'class="{cls}"')
    if hid:
        a.append(f'data-hf-id="{hid}"')
    return f"<{tag} {' '.join(a)}>{inner}</{tag}>"

# ---------------------------------------------------------------- CSS
CSS = """
@font-face { font-family: "PingFang SC"; src: local("PingFang SC"); }
@font-face { font-family: "Microsoft YaHei"; src: local("Microsoft YaHei"); }
*{margin:0;padding:0;box-sizing:border-box}
html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#0a0e1a}
body{font-family:"PingFang SC","Microsoft YaHei",sans-serif}
.clip{position:absolute}
.scene-bg{width:1080px;height:1920px;background:transparent}
.glass-bar{width:1080px;background:rgba(10,14,26,0.65);backdrop-filter:blur(12px);border-top:3px solid #ff3b30}
.tag{display:inline-block;background:#ff3b30;color:#fff;font-size:26px;font-weight:800;padding:8px 20px;border-radius:8px;letter-spacing:2px}
.tag-ghost{display:inline-block;background:#fff;color:#0a0e1a;font-size:26px;font-weight:800;padding:8px 20px;border-radius:8px;letter-spacing:2px}
.title{color:#fff;font-weight:900;line-height:1.2}
.sub{color:#a8b2c7;line-height:1.5}
.hook-big{position:relative;z-index:6;color:#ff3b30;font-weight:900;text-align:center}
.hook-sub{color:#fff;font-size:30px;font-weight:800}
.img-card{position:absolute;left:50%;top:52%;transform:translate(-50%,-50%);width:82%;height:auto;max-height:500px;object-fit:contain;background:rgba(0,0,0,0.2);border:2px solid rgba(255,255,255,0.9);border-radius:14px;box-shadow:0 12px 30px rgba(0,0,0,0.5);z-index:4}
.box-img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#0a0e1a}
.list-item{display:flex;align-items:center;gap:14px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);border-radius:14px;padding:14px 20px}
.list-item-hot{display:flex;align-items:center;gap:14px;background:rgba(255,59,48,0.14);border:1px solid rgba(255,59,48,0.35);border-radius:14px;padding:14px 20px}
.list-badge{color:#ff3b30;font-size:24px;font-weight:800;margin-left:auto}
.list-badge-dim{color:#a8b2c7;font-size:24px;margin-left:auto}
.punch{position:relative;color:#5a6580;font-size:26px;font-weight:800}
.badge-pill{position:relative;z-index:5;background:#ff3b30;color:#fff;font-size:26px;font-weight:900;padding:10px 22px;border-radius:100px;letter-spacing:2px}
.grad-v{position:absolute;inset:0;background:linear-gradient(180deg,rgba(10,14,26,0.15) 0%,rgba(10,14,26,0.35) 40%,rgba(10,14,26,0.85) 100%)}
.grad-r{position:absolute;inset:0;background:linear-gradient(180deg,rgba(13,17,23,0.4) 0%,rgba(42,14,14,0.85) 100%)}
.grad-zone{position:absolute;inset:0;background:linear-gradient(180deg,transparent 30%,rgba(10,14,26,0.25) 65%,rgba(10,14,26,0.95) 100%)}
.vs-card{flex:1;background:rgba(0,0,0,0.55);border:1px solid rgba(255,255,255,0.18);border-radius:14px;padding:14px;text-align:center;backdrop-filter:blur(6px)}
.vs-card-hot{flex:1;background:#ff3b30;border-radius:14px;padding:14px;text-align:center}
.cmp-card{flex:1;background:rgba(255,59,48,0.18);border:1px solid rgba(255,59,48,0.4);border-radius:14px;padding:14px;text-align:center}
.cmp-card-hot{flex:1;background:#ff3b30;border-radius:14px;padding:14px;text-align:center}
.cta-pill{position:relative;z-index:5;background:#ff3b30;color:#fff;font-size:28px;font-weight:900;padding:14px 28px;border-radius:100px}
"""

# ---------------------------------------------------------------- media
def media_el(vis, asset_dir, hid, mid=None, opacity0=False, vstart=0.0, vdur=8.0):
    """visual -> 铺满媒体盒的 img/video（center/ending 布局用）；非首张 opacity:0 以便交叉淡化"""
    src = f"assets/{vis.get('asset_path','')}"
    attrs = {"src": src, "data-hf-id": hid}
    if mid:
        attrs["id"] = mid
    style = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#0a0e1a;'
    if opacity0:
        style += 'opacity:0;'
    if vis.get("type") == "clip":
        # 场景内媒体片段：不加 loop（README 坑 #6——循环会压到下一幕）；data-duration 保证时间窗结束自动切换
        attrs.update({"muted": "", "playsinline": "",
                      "data-start": str(round(vstart, 2)),
                      "data-duration": str(round(vdur, 2))})
        return el("video", attrs, style)
    return el("img", attrs, style)

def split_media(vis, asset_dir, mid, opacity0=False, vstart=0.0, vdur=8.0):
    """split 布局用：居中卡片式媒体（透明底，露出背景飞驰）。

    用 div 包裹 img/video（不能把 width/height:auto/max-height/object-fit 直接放
    img 上——实测该组合在本渲染环境下会把卡片异常放大到 ~790px 高，遮住玻璃卡）。
    id 挂在包裹层上供 GSAP 交叉淡化定位；opacity:0 初始态也放在包裹层。
    """
    src = f"assets/{vis.get('asset_path','')}"
    card_style = ("position:absolute;left:50%;top:64%;transform:translate(-50%,-50%);"
                  "width:100%;height:auto;max-height:700px;overflow:hidden;"
                  "background:rgba(0,0,0,0.35);border:2px solid rgba(255,255,255,0.9);"
                  "border-radius:16px;box-shadow:0 16px 40px rgba(0,0,0,0.6);z-index:4;")
    if opacity0:
        card_style += "opacity:0;"
    inner_style = "width:100%;height:auto;display:block;object-fit:contain;"
    attrs = {"src": src}
    if vis.get("type") == "clip":
        # 场景内媒体片段：播完即停（不带 loop，避免循环压到下一幕）；背景循环视频的 loop 在 bgv 处单独处理
        # 必须给 video 自己的 data-start/data-duration 时间窗——否则 hyperframes 不拥有播放权，
        # 片段播完后的帧会脱离场景容器持续显示
        attrs.update({"muted": "", "playsinline": "",
                      "data-start": str(round(vstart, 2)),
                      "data-duration": str(round(vdur, 2))})
        inner = el("video", attrs, inner_style)
    else:
        inner = el("img", attrs, inner_style)
    return el("div", {"id": mid, "class": "split-card", "data-hf-id": f"hf-{mid}"},
              card_style, inner)

def crossfade_times(scene, dur):
    """visual 切换时间（绝对秒，场景内）：offset_hint 优先，否则等分"""
    vs = scene.get("visuals", [])
    n = len(vs)
    if n <= 1:
        return []
    out = []
    for i in range(1, n):
        oh = vs[i].get("offset_hint")
        if oh is not None:
            t = dur * oh / 100.0
        else:
            t = dur * i / n
        out.append(t)
    return out

# ---------------------------------------------------------------- layouts
def render_split(scene, si, sstart, sdur, asset_dir, ctx):
    """上图区 + 底部玻璃卡"""
    d = scene.get("display", {})
    html = []
    hh = d.get("hook")
    if hh:
        html.append(el("div", {"id": f"{ctx['sid']}-hook", "class": "hook-big"},
                       'position:absolute;top:166px;left:0;right:0;font-size:64px;z-index:6',
                       f"{esc(hh['main'])}<br>{el('span', {'class':'hook-sub'}, '', esc(hh['sub']))}",
                       hid=f"hf-{ctx['sid']}-hook"))
    # 媒体区
    vs = scene.get("visuals", [])
    n = len(vs)
    cf = crossfade_times(scene, ctx["sdur"])          # 交叉淡化时刻（场景内，i=1..n-1）
    bounds = [0.0] + list(cf) + [ctx["sdur"]]          # 每个 visual 的可见窗口边界
    html.append(el("div", {}, "width:1080px;height:1000px;position:relative;overflow:hidden;background:transparent;",
                   "".join(
                       split_media(v, asset_dir, f"{ctx['sid']}-v{i}", opacity0=(i > 0),
                                    vstart=ctx["sstart"] + bounds[i],
                                    vdur=max(1.0, bounds[i+1] - bounds[i]))
                       for i, v in enumerate(vs)
                   ) + el("div", {"class": "grad-zone"}, "", "", hid=f"hf-{ctx['sid']}-gz"),
                   hid=f"hf-{ctx['sid']}-zone"))
    # 底部玻璃卡（对比行/副文追加在最后一项内容之后）
    bar = []
    vsb = d.get("vs")
    lab = d.get("label")
    if d.get("tag"):
        bar.append(el("div", {"id": f"{ctx['sid']}-tag"}, "margin-bottom:14px",
                      f"<span class='tag'>{esc(d['tag'])}</span>", None,
                      hid=f"hf-{ctx['sid']}-tag"))
    if d.get("title"):
        t = d["title"]
        main = t.get("main", "")
        hl = t.get("highlight", "")
        bar.append(el("div", {"id": f"{ctx['sid']}-title", "class": "title"},
                       "font-size:52px;margin-top:14px",
                       f"{esc(main)}<br>{el('span', {'style':'color:#ff3b30'}, '', esc(hl))}",
                       hid=f"hf-{ctx['sid']}-title"))
    if d.get("sub"):
        bar.append(el("div", {"id": f"{ctx['sid']}-sub", "class": "sub"},
                      "font-size:29px;margin-top:10px", esc(d["sub"]), hid=f"hf-{ctx['sid']}-sub"))
    extra_src = d.get("extra_video") or d.get("extra_img")
    if extra_src:
        media_paths = {v.get("asset_path") for v in scene.get("visuals", [])}
        if extra_src in media_paths:
            print(f"ERROR: {ctx['sid']} extra_src={extra_src} 与媒体区图片重复，跳过（需独立抽帧）")
        else:
            if str(extra_src).endswith(".mp4"):
                attrs = {
                    "src": f"assets/{extra_src}",
                    "muted": "",
                    "playsinline": "",
                    "loop": "",
                    "data-start": str(round(ctx["sstart"], 2)),
                    "data-duration": str(round(ctx["sdur"], 2))
                }
                bar.append(el("video", attrs,
                              "width:100%;height:300px;object-fit:cover;background:#0a0e1a;border-radius:12px;margin-top:14px;border:2px solid rgba(255,59,48,0.6);box-shadow:0 8px 24px rgba(0,0,0,0.5);",
                              hid=f"hf-{ctx['sid']}-extra"))
            else:
                bar.append(el("img", {"src": f"assets/{extra_src}"},
                              "width:100%;height:250px;object-fit:contain;background:transparent;border-radius:12px;margin-top:14px;border:1px solid rgba(255,255,255,0.15);",
                              hid=f"hf-{ctx['sid']}-extra"))
    if vsb:
        bar.append(el("div", {"id": f"{ctx['sid']}-vs"},
                      "width:100%;display:flex;gap:12px;margin-top:16px;",
                      el("div", {"class": "vs-card"}, "",
                         f"<div style='color:#a8b2c7;font-size:20px'>{esc(vsb['before']['label'])}</div>"
                         f"<div style='color:#fff;font-size:30px;font-weight:900'>{esc(vsb['before']['value'])}</div>")
                      + "<div style='display:flex;align-items:center;color:#ff3b30;font-size:36px;font-weight:900'>→</div>"
                      + el("div", {"class": "vs-card-hot"}, "",
                           f"<div style='color:rgba(255,255,255,0.9);font-size:20px'>{esc(vsb['after']['label'])}</div>"
                           f"<div style='color:#fff;font-size:30px;font-weight:900'>{esc(vsb['after']['value'])}</div>"),
                      hid=f"hf-{ctx['sid']}-vs"))
    if lab:
        bar.append(el("div", {"id": f"{ctx['sid']}-label"},
                      "margin-top:14px;align-self:center;background:rgba(0,0,0,0.68);border:1px solid rgba(255,255,255,0.18);color:#fff;font-size:23px;font-weight:700;padding:10px 20px;border-radius:100px;backdrop-filter:blur(6px);",
                      esc(lab), hid=f"hf-{ctx['sid']}-label"))
    html.append(el("div", {"id": f"{ctx['sid']}-bar", "class": "glass-bar"},
                   "flex:1;padding:56px 48px 100px;display:flex;flex-direction:column;justify-content:flex-start;",
                   "".join(bar), hid=f"hf-{ctx['sid']}-bar"))
    return f'<div class="scene-bg" style="display:flex;flex-direction:column;position:relative">{"".join(html)}</div>'

def render_center(scene, si, sstart, sdur, asset_dir, ctx):
    """全屏居中列：badge/question/hook + 媒体盒 + list/punch"""
    d = scene.get("display", {})
    parts = []
    if d.get("badge"):
        parts.append(el("div", {"id": f"{ctx['sid']}-badge", "class": "badge-pill"}, "", esc(d["badge"]),
                        hid=f"hf-{ctx['sid']}-badge"))
    if d.get("question"):
        parts.append(el("div", {"id": f"{ctx['sid']}-question", "class": "title"},
                        "position:relative;z-index:5;font-size:62px;text-align:center;margin-top:18px;line-height:1.2",
                        esc(d["question"]), hid=f"hf-{ctx['sid']}-question"))
    hh = d.get("hook")
    if hh:
        parts.append(el("div", {"id": f"{ctx['sid']}-hook", "class": "hook-big"},
                        "font-size:64px;margin-top:26px",
                        f"{esc(hh['main'])}<br>{el('span', {'class':'hook-sub'}, '', esc(hh['sub']))}",
                        hid=f"hf-{ctx['sid']}-hook"))
    if scene.get("visuals"):
        vs_all = scene.get("visuals", [])
        n_all = len(vs_all)
        parts.append(el("div", {"id": f"{ctx['sid']}-media"},
                        "position:relative;z-index:5;width:100%;height:600px;margin-top:44px;border-radius:16px;overflow:hidden;border:2px solid rgba(255,255,255,0.85);box-shadow:0 14px 36px rgba(0,0,0,0.5);background:rgba(0,0,0,0.45);",
                        "".join(media_el(v, asset_dir, f"hf-{ctx['sid']}-v{i}", f"{ctx['sid']}-v{i}", opacity0=(i > 0),
                                     vstart=ctx["sstart"] + (ctx["sdur"] * i / n_all if i > 0 else 0.0),
                                     vdur=min(v.get("clip_duration_s") or 8,
                                              max(1.0, ctx["sdur"] - (ctx["sdur"] * i / n_all if i > 0 else 0.0))))
                                for i, v in enumerate(vs_all)),
                        hid=f"hf-{ctx['sid']}-media"))
    if d.get("list"):
        lis = []
        for i, it in enumerate(d["list"]):
            hot = it.get("hot")
            cls = "list-item-hot" if hot else "list-item"
            badge_cls = "list-badge" if hot else "list-badge-dim"
            lis.append(el("div", {"id": f"{ctx['sid']}-l{i}", "class": cls}, "",
                          f"<span style='font-size:32px'>{esc(it.get('emoji',''))}</span>"
                          f"<span style='color:#fff;font-size:28px;font-weight:700'>{esc(it['text'])}</span>"
                          f"<span class='{badge_cls}'>{esc(it.get('badge',''))}</span>",
                          hid=f"hf-{ctx['sid']}-l{i}"))
        parts.append(el("div", {"id": f"{ctx['sid']}-list"},
                        "position:relative;width:100%;margin-top:24px;display:flex;flex-direction:column;gap:12px;",
                        "".join(lis), hid=f"hf-{ctx['sid']}-list"))
    if d.get("numbers"):
        cards = []
        for i, n in enumerate(d["numbers"]):
            hot = n.get("highlight")
            cards.append(el("div", {"id": f"{ctx['sid']}-n{i}"},
                            f"flex:1;{'background:#ff3b30;' if hot else 'background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);'}border-radius:14px;padding:14px;text-align:center;",
                            f"<div style='color:{'rgba(255,255,255,0.9)' if hot else '#a8b2c7'};font-size:22px'>{esc(n['label'])}</div>"
                            f"<div class='num' style='color:#fff;font-size:40px;font-weight:900'>{esc(n['value'])}</div>",
                            hid=f"hf-{ctx['sid']}-n{i}"))
        parts.append(el("div", {"id": f"{ctx['sid']}-nums"},
                        "position:relative;width:100%;margin-top:24px;display:flex;gap:14px;",
                        "".join(cards), hid=f"hf-{ctx['sid']}-nums"))
    if d.get("punch"):
        parts.append(el("div", {"id": f"{ctx['sid']}-punch", "class": "punch"},
                        "margin-top:18px", esc(d["punch"]), hid=f"hf-{ctx['sid']}-punch"))
    return f'<div style="width:1080px;height:1920px;background:transparent;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:0 56px;position:relative;overflow:hidden;">' \
           f'{el("div", {"class":"grad-v"}, "", "", hid=f"hf-{ctx["sid"]}-g1")}' \
           f'{el("div", {"class":"grad-r"}, "", "", hid=f"hf-{ctx["sid"]}-g2")}' \
           f'{"".join(parts)}</div>'

def render_ending(scene, si, sstart, sdur, asset_dir, ctx):
    """结尾：媒体盒 + 标题 + 钩子 + CTA"""
    d = scene.get("display", {})
    parts = []
    if scene.get("visuals"):
        parts.append(el("div", {"id": f"{ctx['sid']}-media"},
                        "position:relative;z-index:5;width:100%;height:620px;border-radius:16px;overflow:hidden;border:2px solid rgba(255,255,255,0.9);box-shadow:0 16px 40px rgba(0,0,0,0.5);background:rgba(0,0,0,0.45);",
                        "".join(media_el(v, asset_dir, f"hf-{ctx['sid']}-v{i}", f"{ctx['sid']}-v{i}", opacity0=(i > 0),
                                     vstart=ctx["sstart"] + (ctx["sdur"] * i / max(1, len(scene.get("visuals", []))) if i > 0 else 0.0),
                                     vdur=min(v.get("clip_duration_s") or 8,
                                              max(1.0, ctx["sdur"] - (ctx["sdur"] * i / max(1, len(scene.get("visuals", []))) if i > 0 else 0.0))))
                                for i, v in enumerate(scene.get("visuals", []))),
                        hid=f"hf-{ctx['sid']}-media"))
    if d.get("title"):
        t = d["title"]
        parts.append(el("div", {"id": f"{ctx['sid']}-title", "class": "title"},
                        "position:relative;z-index:5;font-size:56px;text-align:center;margin-top:26px;line-height:1.2",
                        f"{esc(t['main'])}<br>{el('span', {'style':'color:#ff3b30'}, '', esc(t['highlight']))}",
                        hid=f"hf-{ctx['sid']}-title"))
    hh = d.get("hook")
    if hh:
        parts.append(el("div", {"id": f"{ctx['sid']}-hook", "class": "hook-big"},
                        "font-size:60px;margin-top:20px",
                        f"{esc(hh['main'])}<br>{el('span', {'class':'hook-sub'}, '', esc(hh['sub']))}",
                        hid=f"hf-{ctx['sid']}-hook"))
    if d.get("cta"):
        parts.append(el("div", {"id": f"{ctx['sid']}-cta", "class": "cta-pill"}, "margin-top:28px",
                        esc(d["cta"]), hid=f"hf-{ctx['sid']}-cta"))
    return f'<div style="width:1080px;height:1920px;background:transparent;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:0 56px;position:relative;overflow:hidden;">' \
           f'{el("div", {"class":"grad-v"}, "", "", hid=f"hf-{ctx["sid"]}-g1")}' \
           f'{el("div", {"class":"grad-r"}, "", "", hid=f"hf-{ctx["sid"]}-g2")}' \
           f'{"".join(parts)}</div>'

# ---------------------------------------------------------------- timeline
def tl_entries(scene, si, sstart, sdur, asset_dir):
    """返回 GSAP 时间轴条目（绝对时间）"""
    sid = f"s{si}"
    d = scene.get("display", {})
    e = []
    def add(line):
        e.append(line)
    if d.get("badge"):
        add(f'tl.from("#{sid}-badge",{{scale:0,opacity:0,duration:0.5,ease:"back.out(1.6)"}},{sstart+0.2});')
    if d.get("question"):
        add(f'tl.from("#{sid}-question",{{y:40,opacity:0,duration:0.6,ease:"power3.out"}},{sstart+0.4});')
    if d.get("hook"):
        add(f'tl.from("#{sid}-hook",{{scale:0.7,opacity:0,duration:0.5,ease:"back.out(1.7)"}},{sstart+0.5});')
    if scene.get("visuals"):
        add(f'tl.from("#{sid}-media",{{scale:0.8,opacity:0,duration:0.6,ease:"back.out(1.5)"}},{sstart+0.8});')
    # visual 交叉淡入淡出
    for i, t in enumerate(crossfade_times(scene, sdur), start=1):
        add(f'tl.to("#{sid}-v{i}",{{opacity:1,duration:0.6,ease:"power2.out"}},{round(sstart+t,2)});')
    if d.get("tag"):
        add(f'tl.from("#{sid}-tag",{{scale:0.8,opacity:0,duration:0.4,ease:"back.out(1.4)"}},{sstart+1.0});')
    if d.get("title"):
        add(f'tl.from("#{sid}-title",{{y:30,opacity:0,duration:0.5}},{sstart+1.2});')
    if d.get("sub"):
        add(f'tl.from("#{sid}-sub",{{y:20,opacity:0,duration:0.4}},{sstart+1.6});')
    if d.get("list"):
        add(f'tl.from("#{sid}-list",{{y:30,opacity:0,duration:0.5}},{sstart+1.2});')
    if d.get("numbers"):
        add(f'tl.from("#{sid}-nums",{{y:30,opacity:0,duration:0.5}},{sstart+1.2});')
        for i, n in enumerate(d["numbers"]):
            if n.get("countup"):
                key = n.get("key", f"n{i}")
                add(f'let o{key}={{v:0}};tl.to(o{key},{{v:{n["value"]},duration:1.2,ease:"power2.out",onUpdate:function(){{var e=document.getElementById("{sid}-n{i}");var s=e.querySelector(".num");s.textContent=Math.round(o{key}.v)}}}},{sstart+1.3});')
    if d.get("punch"):
        add(f'tl.from("#{sid}-punch",{{opacity:0,duration:0.4}},{sstart+2.2});')
    if d.get("vs"):
        add(f'tl.from("#{sid}-vs",{{y:-20,opacity:0,duration:0.5}},{sstart+0.5});')
    if d.get("label"):
        add(f'tl.from("#{sid}-label",{{y:20,opacity:0,duration:0.4}},{sstart+0.9});')
    if d.get("cta"):
        add(f'tl.from("#{sid}-cta",{{scale:0.9,opacity:0,duration:0.5,ease:"back.out(1.4)"}},{sstart+1.4});')
    return e

# ---------------------------------------------------------------- main
def main():
    ep_path, asset_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(ep_path, encoding="utf-8") as f:
        ep = json.load(f)["episode"]
    scenes = ep["scenes"]
    # 计算每幕绝对时间（audio_s 优先，否则 duration_estimate_s，否则默认 15）
    starts = []
    t = 0.0
    for sc in scenes:
        starts.append(t)
        t += sc.get("audio_s") or sc.get("duration_estimate_s") or 15.0
    total = round(t, 2)
    bg = ep.get("background", "youtube_rally_vertical.mp4")

    body = []
    # 音频
    for i, sc in enumerate(scenes):
        dur = round(sc.get("audio_s") or sc.get("duration_estimate_s") or 15.0, 2)
        body.append(el("audio", {"id": f"audio-s{i}", "class": "clip",
                                 "data-start": str(round(starts[i], 2)), "data-duration": str(dur),
                                 "data-track-index": "6", "src": f"assets/s{i}.wav"},
                       None, "", None, f"hf-{i}-audio"))
    # 每幕
    for i, sc in enumerate(scenes):
        sid = f"s{i}"
        sstart = round(starts[i], 2)
        sdur = round(sc.get("audio_s") or sc.get("duration_estimate_s") or 15.0, 2)
        ctx = {"sid": sid, "si": i, "sstart": sstart, "sdur": sdur}
        bgv = el("video", {"id": f"bg-{sid}", "class": "clip", "data-start": str(sstart), "data-duration": str(sdur),
                           "data-track-index": "0", "muted": "", "playsinline": "", "loop": "", "src": f"assets/{bg}"},
                 "width:1080px;height:1920px;object-fit:cover;filter:brightness(0.62) contrast(1.05);")
        layout = sc.get("display", {}).get("layout", "center")
        if layout == "split":
            scene_inner = render_split(sc, i, sstart, sdur, asset_dir, ctx)
        elif layout == "ending":
            scene_inner = render_ending(sc, i, sstart, sdur, asset_dir, ctx)
        else:
            scene_inner = render_center(sc, i, sstart, sdur, asset_dir, ctx)
        scene_div = el("div", {"id": sid, "class": "clip", "data-start": str(sstart),
                               "data-duration": str(sdur), "data-track-index": "1",
                               "data-hf-id": f"hf-{sid}-wrap"},
                       "width:1080px;height:1920px;", scene_inner)
        body.append(bgv)
        body.append(scene_div)

    # 水印
    body.append(el("div", {"id": "watermark", "class": "clip",
                           "data-start": "0", "data-duration": str(total), "data-track-index": "2"},
                   "right:32px;bottom:42px;background:rgba(0,0,0,0.55);border:1px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.9);font-size:24px;font-weight:700;padding:10px 18px;border-radius:100px;backdrop-filter:blur(6px);",
                   esc(ep.get("watermark", "拉力冷知识")), None, "hf-wm"))

    # GSAP timeline
    tls = []
    for i, sc in enumerate(scenes):
        sstart = round(starts[i], 2)
        sdur = round(sc.get("audio_s") or sc.get("duration_estimate_s") or 15.0, 2)
        tls.extend(tl_entries(sc, i, sstart, sdur, asset_dir))
    script_js = ("window.__timelines = window.__timelines || {};\n"
                 "const tl = gsap.timeline({paused:true});\n"
                 + "\n".join(tls) + "\n"
                 f'window.__timelines["main"]=tl;\n')

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1080, height=1920">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{CSS}</style>
</head>
<body>
<div data-hf-id="hf-root" id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="1080" data-height="1920">
{"\n".join(body)}
</div>
<script>
{script_js}</script>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK: {out_path} total={total}s scenes={len(scenes)}")

if __name__ == "__main__":
    main()
