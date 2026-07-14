"""Test: run a simple Flux2 txt2img to verify basic image output works."""
import sys, json, time
sys.path.insert(0, r'E:\YifuAIForge\OpenMontage')
from pathlib import Path
from tools._comfyui.client import ComfyUIClient
from tools.graphics.comfyui_image import ComfyUIImage

PROJECT     = Path(r'E:\YifuAIForge\OpenMontage\projects\fabric-showcase-silk')
LOG         = PROJECT / 'gen_result.txt'
FLUX2_WF    = r'E:\YifuAIForge\OpenMontage\tools\_comfyui\workflows\flux2-txt2img.json'

def log(msg):
    print(msg)
    with open(LOG, 'w', encoding='utf-8') as f:
        f.write(str(msg) + '\n')

# First, list node IDs in the bundled Flux2 workflow
wf = json.loads(Path(FLUX2_WF).read_text(encoding='utf-8'))
log("Flux2-txt2img node IDs:")
for node_id in sorted(wf.keys()):
    ct = wf[node_id]['class_type']
    inputs_keys = list(wf[node_id].get('inputs', {}).keys())[:4]
    log(f"  {node_id!r:8s} [{ct}] inputs: {inputs_keys}")

log("\nRunning Flux2-txt2img workflow...")
img_tool = ComfyUIImage()
res = img_tool.execute({
    "prompt": "A beautiful silk fabric texture, macro photography",
    "workflow_path": FLUX2_WF,
    "output_node": "13",
    "output_path": str(PROJECT / 'assets' / 'images' / 'test_flux.png'),
    "workflow_name": "flux2-txt2img",
    "workflow_model": "flux2-dev-nvfp4"
})
log(f"success={res.success}")
if res.success:
    log(f"  output: {res.data.get('output')}")
else:
    log(f"  ERROR: {res.error}")
