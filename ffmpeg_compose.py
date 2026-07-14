"""
FFmpeg 拼接：按 5 幕顺序组装视频
Scene1 (0-5s):   scene2_fabric_flat.png + 品牌文字
Scene2 (5-9s):   scene2_video.mp4
Scene3 (9-13s):   scene3_video.mp4
Scene4 (13-17s):  scene4_video.mp4
Scene5 (17-20s):  scene5_cta.jpg + 品牌文字
"""
import subprocess, os
from pathlib import Path

BASE = Path(r'E:\YifuAIForge\OpenMontage\fabric-showcase-silk\assets')
OUT  = Path(r'E:\YifuAIForge\OpenMontage\fabric-showcase-silk\renders\final.mp4')
TMP  = Path(r'E:\YifuAIForge\OpenMontage\fabric-showcase-silk\renders\tmp_frames')
TMP.mkdir(exist_ok=True)

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode != 0:
        print("ERR:", r.stderr[-300:])
    return r

# 从混音音频中提取时长
r = run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format',
         str(BASE / 'audio' / 'mixed.wav')])
import json
try:
    audio_dur = float(json.loads(r.stdout)['format']['duration'])
except:
    audio_dur = 17.44
print(f"Audio duration: {audio_dur}s")

# 构建文件列表: 每段 [input_path, start_time, duration]
# s1: scene2_fabric_flat.png 静止 5s
# s2: scene2_video.mp4 4s
# s3: scene3_video.mp4 4s
# s4: scene4_video.mp4 4s
# s5: scene5_cta.jpg 静止 3s

# 用 drawtext 添加文字 (ffmpeg drawtext 在 Windows 对中文支持差，改用图片覆盖)

# 方案：先生成带文字的图片，再拼接
TMP_IMG = TMP / 'with_text'
TMP_IMG.mkdir(exist_ok=True)

# Scene1: fabric图片 + 品牌文字用图片合成
# 先用 PIL 生成带文字的 Scene1 和 Scene5 图片
from PIL import Image, ImageDraw, ImageFont
import math

def make_text_image(bg_path, text1, text2, out_path):
    img = Image.open(bg_path).convert('RGBA')
    w, h = img.size
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # 尝试系统字体
    try:
        font1 = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 60)
        font2 = ImageFont.truetype("C:/Windows/Fonts/simhei.ttf", 36)
    except:
        font1 = ImageFont.load_default()
        font2 = font1
    # 文字居中底部
    bbox = draw.textbbox((0, 0), text1, font=font1)
    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    draw.text(((w - bw) // 2, h - 160), text1, fill=(255, 255, 255, 255), font=font1)
    bbox2 = draw.textbbox((0, 0), text2, font=font2)
    bw2 = bbox2[2] - bbox2[0]
    bh2 = bbox2[3] - bbox2[1]
    draw.text(((w - bw2) // 2, h - 90), text2, fill=(220, 220, 220, 200), font=font2)
    img = Image.alpha_composite(img, overlay).convert('RGB')
    img.save(out_path)
    print(f"  Made: {out_path}")

print("Making text images...")
# Scene1: 面料图片 + 晟鑫纺织
make_text_image(BASE / 'images' / 'scene2_fabric_flat.png',
               '晟鑫纺织', '', TMP / 'scene1_text.jpg')
# Scene5: CTA图片 + 文字
make_text_image(BASE / 'images' / 'scene5_cta.jpg',
               '晟鑫纺织', '平价真丝质感，性价比天花板', TMP / 'scene5_text.jpg')

# 生成每段视频片段
def img_to_video(img_path, duration, out_mp4):
    run(['ffmpeg', '-y', '-loop', '1', '-i', str(img_path),
         '-t', str(duration), '-vf', 'fps=30,scale=1080:1920',
         '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
         '-pix_fmt', 'yuv420p', '-an', str(out_mp4)])
    print(f"  {out_mp4.name}: {out_mp4.stat().st_size//1024}KB")

def trim_video(in_mp4, duration, out_mp4):
    run(['ffmpeg', '-y', '-i', str(in_mp4), '-t', str(duration),
         '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
         '-vf', 'scale=1080:1920', '-pix_fmt', 'yuv420p', '-an', str(out_mp4)])
    print(f"  {out_mp4.name}: {out_mp4.stat().st_size//1024}KB")

print("Making clips...")
img_to_video(TMP / 'scene1_text.jpg', 5.0, TMP / 'clip1.mp4')
trim_video(BASE / 'video' / 'scene2_video.mp4', 4.0, TMP / 'clip2.mp4')
trim_video(BASE / 'video' / 'scene3_video.mp4', 4.0, TMP / 'clip3.mp4')
trim_video(BASE / 'video' / 'scene4_video.mp4', 4.0, TMP / 'clip4.mp4')
img_to_video(TMP / 'scene5_text.jpg', 3.0, TMP / 'clip5.mp4')

# 拼接所有片段
clips = list(TMP / f'clip{i}.mp4' for i in range(1, 6))
concat_list = TMP / 'concat.txt'
with open(concat_list, 'w') as f:
    for c in clips:
        f.write(f"file '{c}'\n")

print("Concatenating...")
run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0',
     '-i', str(concat_list),
     '-c', 'copy', TMP / 'video_no_audio.mp4'])

# 混音
print("Adding audio...")
run(['ffmpeg', '-y',
     '-i', str(TMP / 'video_no_audio.mp4'),
     '-i', str(BASE / 'audio' / 'mixed.wav'),
     '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
     '-c:a', 'aac', '-b:a', '128k',
     '-shortest',
     '-pix_fmt', 'yuv420p',
     str(OUT)])
print(f"Done: {OUT} ({OUT.stat().st_size//1024//1024}MB)")
