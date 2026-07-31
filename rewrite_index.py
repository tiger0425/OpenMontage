"""Rewrite index.html: inline all text-card content, remove empty divs."""
import json
import re
from pathlib import Path

project = Path(__file__).parent
workspace = project / "projects" / "ai-news-daily" / "hyperframes"

def get_start(cuts, idx):
    return float(cuts[idx].get("in_seconds", 0) or 0)

def get_duration(cuts, idx):
    c = cuts[idx]
    return max(0.1, float(c.get("out_seconds", 0) or 0) - float(c.get("in_seconds", 0) or 0))

# Load edit_decisions
with open(project / "projects/ai-news-daily/edit_decisions.json", encoding="utf-8") as f:
    ed = json.load(f)
cuts = ed["cuts"]

# Read current index.html
html_path = workspace / "index.html"
html = html_path.read_text(encoding="utf-8")

# 1. Replace sub-comp divs for text-card scenes with inline text
for i, cut in enumerate(cuts):
    if cut.get("type") != "text_card":
        continue
    text = cut.get("text") or cut.get("title") or ""
    if not text:
        continue
    scene_id = cut.get("id", f"cut-{i}")
    start = get_start(cuts, i)
    duration = get_duration(cuts, i)

    # Find and replace the sub-comp div
    pattern = f'<div id="el-{scene_id}" class="clip center" data-composition-id="{scene_id}"[^>]*></div>'
    match = re.search(pattern, html)
    if match:
        replacement = (
            f'<div id="el-{scene_id}" class="clip text-card center" '
            f'data-start="{start}" data-duration="{duration}" data-track-index="1" '
            f'style="font-family: var(--font-heading); font-size: 48px; font-weight: 700; '
            f'color: var(--color-fg); display: flex; align-items: center; justify-content: center; '
            f'text-align: center; z-index: 10;">'
            f'<h1 style="background: rgba(250, 246, 246, 0.90); padding: 20px 40px; '
            f'border-radius: 20px; box-shadow: 0 10px 30px rgba(60, 50, 51, 0.1); '
            f'border: 1px solid rgba(236, 210, 211, 0.6); max-width: 85%; margin: 0; '
            f'font-size: 48px; line-height: 1.2; backdrop-filter: blur(12px);">'
            f'{text}</h1></div>'
        )
        html = html.replace(match.group(0), replacement)
        print(f"Inline text: {scene_id} -> '{text[:40]}'")

# 2. Remove ALL remaining empty text-card divs (cut-XX without content)
html = re.sub(r'<div id="cut-\d+" class="clip text-card"[^>]*></div>', '', html)
print("Removed empty text-card divs")

# 3. Rebuild the GSAP timeline script
timeline_lines = [
    'window.__timelines = window.__timelines || {};',
    'const tl = gsap.timeline({ paused: true });',
]
# Text card fade-in animations
for i, cut in enumerate(cuts):
    if cut.get("type") == "text_card" and (cut.get("text") or cut.get("title")):
        scene_id = cut.get("id", f"cut-{i}")
        start = get_start(cuts, i)
        timeline_lines.append(
            f'tl.from("#el-{scene_id} h1", {{ y: 30, opacity: 0, duration: 0.6, ease: "power3.out" }}, {start});'
        )
# Video clip fade-in animations
for i, cut in enumerate(cuts):
    if cut.get("type") == "video":
        start = get_start(cuts, i)
        timeline_lines.append(
            f'tl.from("#cut-{i}", {{ opacity: 0, duration: 0.6, ease: "power2.out" }}, {start});'
        )
timeline_lines.append('window.__timelines["root"] = tl;')

new_script = '<script>\n      ' + '\n      '.join(timeline_lines) + '\n    </script>'
html = re.sub(r'<script>\s*window\.__timelines.*?</script>', new_script, html, flags=re.DOTALL)

html_path.write_text(html, encoding="utf-8")
print(f"\nDone. index.html rewritten.")
