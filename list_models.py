"""List ALL available models in ComfyUI."""
import sys, json
sys.path.insert(0, r'E:\YifuAIForge\OpenMontage')
from tools._comfyui.client import ComfyUIClient

LOG = r'E:\YifuAIForge\OpenMontage\projects\fabric-showcase-silk\gen_result.txt'
def log(msg):
    print(msg)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(str(msg) + '\n')

client = ComfyUIClient()
models = client.list_models()

for category, items in models.items():
    log(f"\n{category}:")
    for item in sorted(items):
        log(f"  {item}")
