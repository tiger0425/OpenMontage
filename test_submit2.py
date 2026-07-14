"""Debug: check what files were actually saved after Klein workflow run."""
import sys, json, time, requests
sys.path.insert(0, r'E:\YifuAIForge\OpenMontage')
from pathlib import Path

PROJECT  = Path(r'E:\YifuAIForge\OpenMontage\projects\fabric-showcase-silk')
LOG      = PROJECT / 'gen_result.txt'

def log(msg):
    print(msg)
    with open(LOG, 'w', encoding='utf-8') as f:
        f.write(str(msg) + '\n')

# Check what files exist in ComfyUI output directory
r = requests.get('http://127.0.0.1:8188/view?filename=&subfolder=Flux2-Klein', timeout=10)
log(f"Output dir status: {r.status_code}")
# Try listing files
r2 = requests.get('http://127.0.0.1:8188/files?subfolder=Flux2-Klein', timeout=10)
log(f"Files list: {r2.text[:500]}")

# Check recent prompt history
prompt_id = '77557e93-8187-4af6-a170-daf741e60d75'
r3 = requests.get(f'http://127.0.0.1:8188/history/{prompt_id}', timeout=10)
history = r3.json()
entry = history.get(prompt_id, {})
log(f"Full entry outputs: {json.dumps(entry.get('outputs', 'EMPTY'))}")

# Check if outputs are under a different key
log(f"All entry keys: {list(entry.keys())}")
