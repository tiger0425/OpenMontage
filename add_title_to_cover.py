import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

src_image_path = r"C:\Users\tiger\.gemini\antigravity\brain\ea8e1e0b-6c72-4297-b967-ea94379d3357\bilibili_cover_harness_1785301636580.jpg"
out_image_path = r"C:\Users\tiger\.gemini\antigravity\brain\ea8e1e0b-6c72-4297-b967-ea94379d3357\bilibili_cover_with_text.jpg"

img = Image.open(src_image_path).convert("RGBA")
width, height = img.size

# Create transparent overlay for graphics and text
overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
draw = ImageDraw.Draw(overlay)

# Add top gradient to enhance text contrast
gradient = Image.new("RGBA", (width, int(height * 0.45)), (0, 0, 0, 0))
g_draw = ImageDraw.Draw(gradient)
for y in range(int(height * 0.45)):
    alpha = int(180 * (1.0 - y / (height * 0.45)))
    g_draw.line([(0, y), (width, y)], fill=(10, 15, 25, alpha))

overlay.paste(gradient, (0, 0), gradient)

# Fonts
font_path_bold = "C:/Windows/Fonts/msyhbd.ttc"
font_path_simhei = "C:/Windows/Fonts/simhei.ttf"

font_tag = ImageFont.truetype(font_path_bold, int(height * 0.045))
font_main = ImageFont.truetype(font_path_bold, int(height * 0.095))
font_sub = ImageFont.truetype(font_path_bold, int(height * 0.055))

# 1. Draw Tag Box (Top Left)
tag_text = "【硬核爆料】"
bbox_tag = draw.textbbox((0, 0), tag_text, font=font_tag)
tag_w = bbox_tag[2] - bbox_tag[1]
tag_h = bbox_tag[3] - bbox_tag[1]

tag_x = int(width * 0.06)
tag_y = int(height * 0.08)

# Tag background capsule
padding = 16
draw.rounded_rectangle(
    [tag_x, tag_y, tag_x + tag_w + padding * 2, tag_y + tag_h + padding],
    radius=12,
    fill=(225, 29, 72, 230), # Vibrant Red
    outline=(255, 255, 255, 250),
    width=3
)
draw.text((tag_x + padding, tag_y + padding // 2), tag_text, font=font_tag, fill=(255, 255, 255, 255))

# 2. Helper function to draw text with heavy outline/shadow
def draw_text_with_outline(draw_obj, x, y, text, font, text_color, outline_color, outline_width=5):
    # Shadow
    draw_obj.text((x + 4, y + 4), text, font=font, fill=(0, 0, 0, 220))
    # Outline
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx * dx + dy * dy <= outline_width * outline_width:
                draw_obj.text((x + dx, y + dy), text, font=font, fill=outline_color)
    # Main Text
    draw_obj.text((x, y), text, font=font, fill=text_color)

# 3. Main Title
main_title = "别再瞎学 PROMPT 了！"
main_x = int(width * 0.06)
main_y = int(height * 0.20)

draw_text_with_outline(
    draw, main_x, main_y,
    main_title, font_main,
    text_color=(255, 235, 59, 255), # Electric Yellow
    outline_color=(0, 0, 0, 255),
    outline_width=7
)

# 4. Sub Title (Banner Box)
sub_title = "大厂 AI Agent 核心架构 HARNESS 揭秘"
sub_x = int(width * 0.06)
sub_y = int(height * 0.35)

bbox_sub = draw.textbbox((0, 0), sub_title, font=font_sub)
sub_w = bbox_sub[2] - bbox_sub[0]
sub_h = bbox_sub[3] - bbox_sub[1]

# Dark banner box for sub title
draw.rounded_rectangle(
    [sub_x - 10, sub_y - 6, sub_x + sub_w + 24, sub_y + sub_h + 12],
    radius=8,
    fill=(15, 23, 42, 220), # Dark Slate
    outline=(56, 189, 248, 255), # Cyan border
    width=3
)

draw.text((sub_x, sub_y), sub_title, font=font_sub, fill=(255, 255, 255, 255))

# Composite overlay on base image
final_img = Image.alpha_composite(img, overlay).convert("RGB")
final_img.save(out_image_path, quality=95)

print(f"Cover with clickbait text generated successfully at: {out_image_path}")
