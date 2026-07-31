import os
from PIL import Image, ImageDraw, ImageFont

src_image_path = r"C:\Users\tiger\.gemini\antigravity\brain\ea8e1e0b-6c72-4297-b967-ea94379d3357\bilibili_clean_background_1785302394737.jpg"
out_image_path = r"C:\Users\tiger\.gemini\antigravity\brain\ea8e1e0b-6c72-4297-b967-ea94379d3357\bilibili_handwritten_clean_cover.jpg"

img = Image.open(src_image_path).convert("RGBA")
width, height = img.size

# Separate text layer for clean text overlay
text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
t_draw = ImageDraw.Draw(text_layer)

# Add dark gradient overlay at top left to make text pop
gradient = Image.new("RGBA", (width, int(height * 0.55)), (0, 0, 0, 0))
g_draw = ImageDraw.Draw(gradient)
for y in range(int(height * 0.55)):
    alpha = int(190 * (1.0 - y / (height * 0.55)))
    g_draw.line([(0, y), (width, y)], fill=(8, 12, 22, alpha))

img.paste(gradient, (0, 0), gradient)

font_path_kai = "C:/Windows/Fonts/simkai.ttf"

font_tag = ImageFont.truetype(font_path_kai, int(height * 0.048))
font_main = ImageFont.truetype(font_path_kai, int(height * 0.11))
font_sub = ImageFont.truetype(font_path_kai, int(height * 0.062))

# 1. Top Left Tag: 【硬核爆料】
tag_x, tag_y = int(width * 0.05), int(height * 0.07)
t_draw.rounded_rectangle(
    [tag_x, tag_y, tag_x + int(width * 0.28), tag_y + int(height * 0.07)],
    radius=14,
    fill=(225, 29, 72, 235),
    outline=(255, 255, 255, 255),
    width=3
)
t_draw.text((tag_x + 15, tag_y + 6), "💥 硬核爆料", font=font_tag, fill=(255, 255, 255, 255))

# 2. Main Title: "别再瞎学 PROMPT 了！"
main_text = "别再瞎学 PROMPT 了！"
main_x = int(width * 0.05)
main_y = int(height * 0.18)

# Red brush background splash
t_draw.polygon([
    (main_x - 15, main_y + 8),
    (main_x + int(width * 0.88), main_y - 8),
    (main_x + int(width * 0.86), main_y + int(height * 0.13)),
    (main_x - 22, main_y + int(height * 0.14))
], fill=(220, 20, 60, 220))

def draw_brush_text(draw_obj, x, y, text, font, fill_color, stroke_color, stroke_w=6):
    # Shadow layer
    for dx in range(-stroke_w-3, stroke_w+4, 2):
        for dy in range(-stroke_w-3, stroke_w+4, 2):
            draw_obj.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 200))
    # Outer stroke
    for dx in range(-stroke_w, stroke_w+1):
        for dy in range(-stroke_w, stroke_w+1):
            if dx*dx + dy*dy <= stroke_w*stroke_w:
                draw_obj.text((x + dx, y + dy), text, font=font, fill=stroke_color)
    # Inner handwritten text
    draw_obj.text((x, y), text, font=font, fill=fill_color)

draw_brush_text(t_draw, main_x, main_y, main_text, font_main, fill_color=(255, 235, 59, 255), stroke_color=(0, 0, 0, 255), stroke_w=7)

# 3. Sub Title: "大厂 AI Agent 核心架构 HARNESS 揭秘"
sub_text = "大厂 AI Agent 核心架构 HARNESS 揭秘"
sub_x = int(width * 0.05)
sub_y = int(height * 0.35)

# Dark slate banner box behind sub title
t_draw.polygon([
    (sub_x - 10, sub_y - 6),
    (sub_x + int(width * 0.90), sub_y - 10),
    (sub_x + int(width * 0.88), sub_y + int(height * 0.095)),
    (sub_x - 15, sub_y + int(height * 0.09))
], fill=(15, 23, 42, 235))

draw_brush_text(t_draw, sub_x + 10, sub_y + 4, sub_text, font_sub, fill_color=(56, 189, 248, 255), stroke_color=(0, 0, 0, 255), stroke_w=5)

# Apply dynamic angle (-2.5 deg)
rotated_layer = text_layer.rotate(-2.5, resample=Image.BICUBIC, center=(width//2, height//2))

# Composite onto base image
final_img = Image.alpha_composite(img, rotated_layer).convert("RGB")
final_img.save(out_image_path, quality=95)

print(f"Clean handwritten cover generated successfully at: {out_image_path}")
