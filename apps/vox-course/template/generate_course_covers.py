#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VOX 科技课程全套连贯性封面生成器 (apps/vox-course/template/generate_course_covers.py)

功能：
  根据课程元数据与核心论点，自动化生成具备明确【课程品牌】、【体系连贯性】与【集数指引】的
  全平台 5 大标准比例封面矩阵：
  - 16:9 (1920x1080) B 站 Web/App 横屏主封面
  - 4:3  (1440x1080) B 站动态与推荐流卡片
  - 1:1  (1080x1080) B 站合集大图 / 微信方形分享图
  - 3:4  (1080x1440) 移动端竖版卡片推荐流
  - 9:16 (1080x1920) 手机全屏动态 / 竖屏短视频
"""

import json
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_MAIN = "C:/Windows/Fonts/msyhbd.ttc"
FONT_BOLD = "C:/Windows/Fonts/simhei.ttf"

def get_font(size):
    return ImageFont.truetype(FONT_MAIN, size)

def get_font_bold(size):
    return ImageFont.truetype(FONT_BOLD, size)

# VOX 工业科技色系
C_BG = (18, 19, 22)           # 深色宇宙底板 #121316
C_CARD = (24, 27, 34)         # 深灰纸板卡片 #181B22
C_BORDER = (55, 62, 75)       # 边框微色
C_GOLD = (255, 204, 0)        # 醒目亮黄 #FFCC00
C_ORANGE = (255, 95, 31)      # 工业警示橙 #FF5F1F
C_GREEN = (0, 255, 65)        # 终端荧光绿 #00FF41
C_RED = (198, 40, 40)         # 连载朱红 #C62828
C_WHITE = (255, 255, 255)
C_SUB = (175, 185, 200)       # 次级灰白


def draw_badge(draw, x, y, text, font, fill_color, text_color, px=18, py=8, radius=6):
    """根据文本实际渲染边界动态绘制自适应药丸徽章，绝不溢出文字"""
    bb = draw.textbbox((x, y), text, font=font)
    rect = [(bb[0] - px, bb[1] - py), (bb[2] + px, bb[3] + py)]
    draw.rounded_rectangle(rect, radius=radius, fill=fill_color)
    draw.text((x, y), text, font=font, fill=text_color)
    return rect[1][0]  # 返回右边界 x2，便于后续元素流式排布


def generate_covers(course_title: str, ep_index: int, ep_topic: str,
                    headline_top: str, headline_main: str, headline_sub: str,
                    out_dir: Path, bg_image_path: Path = None):
    out_dir.mkdir(parents=True, exist_ok=True)
    
    ep_str = f"第 {ep_index:02d} 讲 · {ep_topic}"
    next_ep_num = ep_index + 1

    points = [
        "① 【MIT 重磅报告】砸了 300 亿美金，为什么连第 3 轮上下文都撑不过？",
        "② 【死循环根因】传统助手把上下文当水桶，死命压缩必然引发脑死亡！",
        "③ 【工程化破局】常驻 IPython 运行时与前缀缓存，瞬间跳过 18,400+ Token！",
        "④ 【算力经济学】避免花大几万买回一台开机飞快吐纸奇慢的“高级复印机”！"
    ]

    # =========================================================================
    # 1. 16:9 画布 (1920x1080) B 站主封面
    # =========================================================================
    W16, H16 = 1920, 1080
    im16 = Image.new("RGB", (W16, H16), C_BG)
    draw16 = ImageDraw.Draw(im16)

    # 细微扫描线
    for y in range(0, H16, 12):
        draw16.line([(0, y), (W16, y)], fill=(14, 15, 18), width=1)

    # 背景混合
    if bg_image_path and bg_image_path.exists():
        with Image.open(bg_image_path) as bg_im:
            bg_im = bg_im.resize((W16, H16), Image.Resampling.LANCZOS)
            bg_im = bg_im.filter(ImageFilter.GaussianBlur(8))
            # 极低透明度，确保不干扰前景大字
            im16 = Image.blend(im16, bg_im.convert("RGB"), 0.22)
            draw16 = ImageDraw.Draw(im16)

    # 顶部课程品牌主通栏
    draw16.rectangle([(60, 40), (1860, 115)], fill=(12, 14, 18), outline=(42, 46, 56), width=2)
    draw16.rectangle([(60, 40), (75, 115)], fill=C_ORANGE)
    draw16.text((100, 56), f"【硬核实战系统课】《{course_title}》", font=get_font(34), fill=C_WHITE)
    
    # 连载徽章
    draw16.rounded_rectangle([(1530, 52), (1840, 102)], radius=8, fill=(0, 42, 14), outline=C_GREEN, width=2)
    draw16.text((1550, 63), "● 全网首发 · 体系连载", font=get_font(23), fill=C_GREEN)

    # 集数标签（动态计算边界，杜绝重叠）
    right_x = draw_badge(draw16, 85, 165, ep_str, get_font_bold(32), C_RED, C_WHITE, px=22, py=10)
    
    # EPISODE 标签排在后面
    ep_badge_text = f"EPISODE {ep_index:02d}"
    bb_ep = draw16.textbbox((right_x + 20, 168), ep_badge_text, font=get_font(26))
    draw16.rounded_rectangle([(right_x + 15, bb_ep[1] - 8), (bb_ep[2] + 16, bb_ep[3] + 8)], radius=6, fill=(32, 36, 46), outline=C_ORANGE, width=2)
    draw16.text((right_x + 20, 168), ep_badge_text, font=get_font(26), fill=C_ORANGE)

    # 本讲核心大标题
    draw16.text((70, 255), headline_top, font=get_font_bold(72), fill=C_WHITE)
    draw16.text((70, 355), headline_main, font=get_font_bold(88), fill=C_GOLD)
    draw16.text((70, 485), f"撕开参数迷信：{headline_sub}", font=get_font(40), fill=C_ORANGE)

    # 实战清单卡片
    draw16.rounded_rectangle([(70, 565), (1280, 930)], radius=8, fill=(16, 18, 24), outline=C_BORDER, width=2)
    for idx, p in enumerate(points):
        draw16.text((105, 595 + idx * 78), p, font=get_font(27), fill=(235, 240, 250))

    # 右侧：核心结论与下集预告
    draw16.rounded_rectangle([(1310, 565), (1850, 930)], radius=8, fill=(22, 25, 34), outline=C_BORDER, width=2)
    draw16.text((1345, 600), "// 本集核心结论 //", font=get_font(22), fill=C_ORANGE)
    draw16.text((1345, 642), "HARNESS > MODEL", font=get_font_bold(42), fill=C_GREEN)
    draw16.text((1345, 705), "底盘决定上限，工程主宰未来", font=get_font(25), fill=C_WHITE)
    
    draw16.line([(1345, 755), (1815, 755)], fill=(50, 56, 70), width=2)
    draw16.text((1345, 780), f"▼ 下讲连贯预告 (EP.{next_ep_num:02d}) ▼", font=get_font(22), fill=C_GOLD)
    draw16.text((1345, 820), "直接撕开沙箱，从零手搓底盘！", font=get_font(25), fill=(220, 225, 235))

    # 底部全景导览
    draw16.rectangle([(0, 990), (W16, H16)], fill=(10, 11, 14))
    draw16.text((70, 1018), "【体系化课程导览】01 认知破局 → 02 沙箱手搓 → 03 内存状态外挂 → 04 前缀缓存 → 05 压测基准 → 06 芯片经济学", font=get_font(24), fill=C_SUB)

    path_16x9 = out_dir / "series_cover_16x9.png"
    im16.save(path_16x9)

    # =========================================================================
    # 2. 4:3 画布 (1440x1080) B 站动态/卡片独立排版（非粗暴裁切）
    # =========================================================================
    W43, H43 = 1440, 1080
    im43 = Image.new("RGB", (W43, H43), C_BG)
    draw43 = ImageDraw.Draw(im43)

    # 顶部课程标
    draw43.rectangle([(50, 40), (1390, 115)], fill=(12, 14, 18), outline=(42, 46, 56), width=2)
    draw43.rectangle([(50, 40), (65, 115)], fill=C_ORANGE)
    draw43.text((85, 56), f"【硬核系统课】《{course_title}》", font=get_font(32), fill=C_WHITE)
    draw43.text((1150, 62), "● 体系连载中", font=get_font(24), fill=C_GREEN)

    # 集数标
    rx43 = draw_badge(draw43, 65, 160, ep_str, get_font_bold(30), C_RED, C_WHITE, px=20, py=9)
    draw_badge(draw43, rx43 + 20, 163, f"EP.{ep_index:02d}", get_font(26), (32, 36, 46), C_ORANGE, px=16, py=7)

    # 核心大标题
    draw43.text((50, 245), headline_top, font=get_font_bold(62), fill=C_WHITE)
    draw43.text((50, 335), headline_main, font=get_font_bold(76), fill=C_GOLD)
    draw43.text((50, 445), f"大模型只是引擎 · Harness 才是真底盘！", font=get_font(34), fill=C_ORANGE)

    # 中部实战清单
    draw43.rounded_rectangle([(50, 520), (1390, 890)], radius=8, fill=(16, 18, 24), outline=C_BORDER, width=2)
    for idx, p in enumerate(points):
        draw43.text((80, 555 + idx * 80), p, font=get_font(26), fill=(235, 240, 250))

    # 底部下期预告
    draw43.rectangle([(0, 960), (W43, H43)], fill=(10, 11, 14))
    draw43.text((50, 1000), f"▼ 连载中 · 下讲 (EP.{next_ep_num:02d})：直接撕开沙箱，从零手搓底盘！", font=get_font(28), fill=C_GOLD)

    path_43 = out_dir / "series_cover_4x3.png"
    im43.save(path_43)

    # =========================================================================
    # 3. 1:1 画布 (1080x1080) B 站合集/正方卡片
    # =========================================================================
    im11 = Image.new("RGB", (1080, 1080), C_BG)
    draw11 = ImageDraw.Draw(im11)

    draw11.rectangle([(40, 40), (1040, 105)], fill=(12, 14, 18), outline=C_BORDER, width=2)
    draw11.rectangle([(40, 40), (55, 105)], fill=C_ORANGE)
    draw11.text((70, 54), f"《{course_title}》", font=get_font(28), fill=C_WHITE)
    draw11.text((800, 58), "● 连载中", font=get_font(22), fill=C_GREEN)

    # 集数标签（自适应宽度）
    draw_badge(draw11, 60, 145, ep_str, get_font_bold(28), C_RED, C_WHITE, px=20, py=8)

    # 核心大字
    draw11.text((40, 225), "为什么 95% 的大模型落地", font=get_font_bold(52), fill=C_WHITE)
    draw11.text((40, 300), "回报率干脆是 0 ？", font=get_font_bold(68), fill=C_GOLD)
    draw11.text((40, 400), "大模型只是引擎 · Harness 才是底盘！", font=get_font(32), fill=C_ORANGE)

    # 实战清单卡片
    draw11.rounded_rectangle([(40, 480), (1040, 890)], radius=8, fill=(16, 18, 24), outline=C_BORDER, width=2)
    p_11 = [
        "① 【MIT报告】300亿美金雪崩，连第3轮都撑不过",
        "② 【上下文腐烂】传统死命压缩必然引发脑死亡",
        "③ 【状态外挂】IPython 终端与前缀缓存跳过1.8万Token",
        "④ 【算力陷阱】别花大几万买回高级复印机烧电费"
    ]
    for idx, p in enumerate(p_11):
        draw11.text((70, 515 + idx * 80), p, font=get_font(26), fill=(230, 235, 245))

    # 底部预告
    draw11.rectangle([(0, 960), (1080, 1080)], fill=(10, 11, 14))
    draw11.text((40, 1000), f"▼ 连载中 · 下讲 (EP.{next_ep_num:02d})：从零手搓生产级执行沙箱", font=get_font(26), fill=C_GOLD)

    path_11 = out_dir / "series_cover_1x1.png"
    im11.save(path_11)

    # =========================================================================
    # 4. 3:4 画布 (1080x1440) 移动端竖版卡片
    # =========================================================================
    im34 = Image.new("RGB", (1080, 1440), C_BG)
    draw34 = ImageDraw.Draw(im34)

    draw34.rectangle([(40, 50), (1040, 130)], fill=(12, 14, 18), outline=C_BORDER, width=2)
    draw34.rectangle([(40, 50), (55, 130)], fill=C_ORANGE)
    draw34.text((75, 70), f"【体系实战课】《{course_title}》", font=get_font(30), fill=C_WHITE)

    draw_badge(draw34, 65, 185, ep_str, get_font_bold(32), C_RED, C_WHITE, px=22, py=10)

    draw34.text((40, 290), "为什么 95% 的大模型落地", font=get_font_bold(54), fill=C_WHITE)
    draw34.text((40, 375), "回报率是 0 ？", font=get_font_bold(80), fill=C_GOLD)
    draw34.text((40, 495), "大模型是引擎 · Harness 才是真底盘！", font=get_font(34), fill=C_ORANGE)

    draw34.rounded_rectangle([(40, 580), (1040, 1100)], radius=8, fill=(16, 18, 24), outline=C_BORDER, width=2)
    for idx, p in enumerate(points):
        draw34.text((70, 620 + idx * 115), p, font=get_font(26), fill=(230, 235, 245))

    draw34.rounded_rectangle([(40, 1140), (1040, 1330)], radius=8, fill=(22, 25, 34), outline=C_BORDER, width=2)
    draw34.text((75, 1170), f"▼ 体系连载 · 下集预告 (EP.{next_ep_num:02d}) ▼", font=get_font(24), fill=C_GOLD)
    draw34.text((75, 1220), "直接撕开沙箱，从零手搓生产级执行底盘！", font=get_font_bold(30), fill=C_WHITE)

    path_34 = out_dir / "series_cover_3x4.png"
    im34.save(path_34)

    # =========================================================================
    # 5. 9:16 画布 (1080x1920) 手机竖屏小视频
    # =========================================================================
    im916 = Image.new("RGB", (1080, 1920), C_BG)
    draw916 = ImageDraw.Draw(im916)

    draw916.rectangle([(40, 90), (1040, 180)], fill=(12, 14, 18), outline=C_BORDER, width=2)
    draw916.rectangle([(40, 90), (55, 180)], fill=C_ORANGE)
    draw916.text((80, 115), f"【硬核实战课】《{course_title}》", font=get_font(32), fill=C_WHITE)

    draw_badge(draw916, 70, 255, ep_str, get_font_bold(36), C_RED, C_WHITE, px=26, py=12)

    draw916.text((40, 380), "为什么 95% 大模型项目", font=get_font_bold(58), fill=C_WHITE)
    draw916.text((40, 470), "回报率干脆是 0 ？", font=get_font_bold(84), fill=C_GOLD)
    draw916.text((40, 600), "大模型是引擎 · Harness 才是底盘！", font=get_font(36), fill=C_ORANGE)

    draw916.rounded_rectangle([(40, 710), (1040, 1370)], radius=12, fill=(16, 18, 24), outline=C_BORDER, width=2)
    for idx, p in enumerate(points):
        draw916.text((70, 760 + idx * 145), p, font=get_font(28), fill=(235, 240, 250))

    draw916.rounded_rectangle([(40, 1420), (1040, 1680)], radius=10, fill=(22, 25, 34), outline=C_BORDER, width=2)
    draw916.text((80, 1460), "HARNESS > MODEL", font=get_font_bold(52), fill=C_GREEN)
    draw916.text((80, 1540), "底盘决定上限，工程主宰未来", font=get_font(32), fill=C_WHITE)

    draw916.rectangle([(0, 1780), (1080, 1920)], fill=(10, 11, 14))
    draw916.text((40, 1820), f"▼ 连载中 · 下讲 (EP.{next_ep_num:02d})：手搓生产级执行底盘", font=get_font(30), fill=C_GOLD)

    path_916 = out_dir / "series_cover_9x16.png"
    im916.save(path_916)

    print(f">> [generate_course_covers] 成功生成 5 大标准比例课程连贯封面矩阵至: {out_dir}")
    return {
        "16:9": str(path_16x9),
        "4:3": str(path_43),
        "1:1": str(path_11),
        "3:4": str(path_34),
        "9:16": str(path_916)
    }


if __name__ == "__main__":
    out = Path(r"projects/agent-harness-ep01/package/covers")
    bg = Path(r"projects/agent-harness-ep01/renders/clean_sc1_30b.png")
    generate_covers(
        course_title="生产级 AI Agent 架构与底盘工程",
        ep_index=1,
        ep_topic="破局与认知重构篇",
        headline_top="为什么 95% 的大模型应用落地",
        headline_main="回报率干脆是 0 ？",
        headline_sub="模型只是概率引擎，Harness 才是真底盘！",
        out_dir=out,
        bg_image_path=bg
    )
