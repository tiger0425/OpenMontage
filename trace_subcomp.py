"""Debug: check overlay_text and is_pure_text_card for each text-card cut."""
import json, sys, os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools.video.hyperframes_compose import HyperFramesCompose

with open('projects/ai-news-daily/edit_decisions.json', encoding='utf-8') as f:
    ed = json.load(f)
with open('projects/ai-news-daily/asset_manifest.json', encoding='utf-8') as f:
    am = json.load(f)

workspace = Path(os.path.abspath('projects/ai-news-daily/hyperframes'))
hfc = HyperFramesCompose.__new__(HyperFramesCompose)
resolved_cuts, _ = hfc._resolve_and_stage_assets(ed['cuts'], am['assets'], workspace)

# Replicate the _scaffold loop logic
for i, cut in enumerate(resolved_cuts):
    cut_type = (cut.get('type') or '').lower()
    if cut_type != 'text_card':
        continue

    text_overlay = cut.get('text_overlay') or {}
    overlay_text = ''
    if isinstance(text_overlay, dict) and text_overlay:
        overlay_text = text_overlay.get('text') or text_overlay.get('title') or text_overlay.get('badge') or ''

    text = cut.get('text') or cut.get('title') or ''
    if not overlay_text and text:
        overlay_text = text

    source = cut.get('source') or ''
    src_path = Path(source) if source else None
    is_media = src_path and src_path.exists()
    is_pure_text_card = cut_type in {'text_card', 'hero_title', 'callout'} or (not source and text)

    should_set = overlay_text or (is_pure_text_card and not is_media)
    print(f"cut[{i}] id={cut.get('id')} text='{text[:30]}' overlay_text='{overlay_text[:30]}' is_media={is_media} is_pure={is_pure_text_card} should_set={should_set}")
