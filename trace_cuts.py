"""Trace exactly what _cut_to_html produces for each cut."""
import json, sys, os
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.video.hyperframes_compose import HyperFramesCompose

# Load data
with open('projects/ai-news-daily/edit_decisions.json', encoding='utf-8') as f:
    ed = json.load(f)
with open('projects/ai-news-daily/asset_manifest.json', encoding='utf-8') as f:
    am = json.load(f)

workspace = Path(os.path.abspath('projects/ai-news-daily/hyperframes'))

hfc = HyperFramesCompose.__new__(HyperFramesCompose)

# Simulate _scaffold's resolve step
resolved_cuts, _ = hfc._resolve_and_stage_assets(ed['cuts'], am['assets'], workspace)

# Check has_subcomp for text-card cuts
for i, cut in enumerate(resolved_cuts):
    if cut.get('type') == 'text_card':
        text = cut.get('text') or cut.get('title') or ''
        has_subcomp = cut.get('has_subcomp', False)
        source = cut.get('source', '')
        print(f"cut[{i}] id={cut.get('id')} has_subcomp={has_subcomp} source='{source}' text='{text[:40]}'")

# Now call _cut_to_html for each text-card cut and see what it produces
print("\n--- _cut_to_html output ---")
for i, cut in enumerate(resolved_cuts):
    if cut.get('type') == 'text_card':
        html, tween = hfc._cut_to_html(i, cut, 1920, 1080, resolved_cuts)
        has_data_comp = 'data-composition-src' in html
        is_empty = '></div>' in html and '<h1>' not in html
        print(f"cut[{i}] id={cut.get('id')} has_subcomp={cut.get('has_subcomp',False)} has_data_comp={has_data_comp} is_empty={is_empty}")
        if is_empty:
            print(f"  HTML: {html[:200]}")
