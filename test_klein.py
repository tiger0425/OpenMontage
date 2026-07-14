"""Minimal test: run Klein workflow as-is with no overrides to check it works."""
import sys, json
sys.path.insert(0, r'E:\YifuAIForge\OpenMontage')
from pathlib import Path
from tools._comfyui.client import ComfyUIClient
from tools.graphics.comfyui_image import ComfyUIImage

PROJECT  = Path(r'E:\YifuAIForge\OpenMontage\projects\fabric-showcase-silk')
KLEIN_WF = r'E:\YifuAIForge\OpenMontage\tools\_comfyui\workflows\klein_fabric.json'
LOG      = PROJECT / 'gen_result.txt'

def log(msg):
    print(msg)
    with open(LOG, 'w', encoding='utf-8') as f:
        f.write(str(msg) + '\n')

# Load and print all node IDs in Klein workflow
wf = json.loads(Path(KLEIN_WF).read_text(encoding='utf-8'))
log("Klein workflow node IDs:")
for node_id in sorted(wf.keys()):
    ct = wf[node_id]['class_type']
    inputs_keys = list(wf[node_id].get('inputs', {}).keys())[:5]
    log(f"  {node_id!r:20s} [{ct}] inputs: {inputs_keys}")

# Try submitting the workflow as-is (no overrides)
log("\nTesting Klein workflow without overrides...")
img_tool = ComfyUIImage()

try:
    res = img_tool.execute({
        "prompt": "test",
        "workflow_path": KLEIN_WF,
        "output_node": "9",
        "output_path": str(PROJECT / 'assets' / 'images' / 'test.png'),
        "workflow_name": "klein-fabric",
        "workflow_model": "flux-2-klein-9b"
    })
    log(f"Result: success={res.success}")
    if res.success:
        log(f"  output: {res.data.get('output')}")
    else:
        log(f"  ERROR: {res.error}")
except Exception as e:
    log(f"Exception: {e}")
