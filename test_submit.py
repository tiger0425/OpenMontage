"""Debug: submit Klein workflow directly and inspect prompt_id + history."""
import sys, json, time
sys.path.insert(0, r'E:\YifuAIForge\OpenMontage')
from pathlib import Path
from tools._comfyui.client import ComfyUIClient

PROJECT  = Path(r'E:\YifuAIForge\OpenMontage\projects\fabric-showcase-silk')
KLEIN_WF = r'E:\YifuAIForge\OpenMontage\tools\_comfyui\workflows\klein_fabric.json'
LOG      = PROJECT / 'gen_result.txt'

def log(msg):
    print(msg)
    with open(LOG, 'w', encoding='utf-8') as f:
        f.write(str(msg) + '\n')

client = ComfyUIClient()
wf = json.loads(Path(KLEIN_WF).read_text(encoding='utf-8'))

log("Submitting Klein workflow directly...")
prompt_id = client.submit(wf)
log(f"prompt_id: {prompt_id}")

log("Polling for completion (60s timeout)...")
try:
    entry = client.poll(prompt_id, timeout=120, interval=5)
    log(f"History entry keys: {list(entry.keys())}")
    status = entry.get('status', {})
    log(f"Status: {json.dumps(status)}")
    outputs = entry.get('outputs', {})
    log(f"Outputs nodes: {list(outputs.keys())}")
    for k, v in outputs.items():
        log(f"  Node {k}: {str(v)[:200]}")
except Exception as e:
    log(f"Error polling: {e}")
