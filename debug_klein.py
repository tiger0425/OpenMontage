"""Debug: submit Klein workflow with fabric upload override directly via client."""
import sys, json, time
sys.path.insert(0, r'E:\YifuAIForge\OpenMontage')
from pathlib import Path
from tools._comfyui.client import ComfyUIClient

PROJECT    = Path(r'E:\YifuAIForge\OpenMontage\projects\fabric-showcase-silk')
FABRIC_REF = Path(r'E:\YifuAIForge\OpenMontage\fabric.jpg')
KLEIN_WF   = r'E:\YifuAIForge\OpenMontage\tools\_comfyui\workflows\klein_fabric.json'
LOG        = PROJECT / 'gen_result.txt'
DEST       = PROJECT / 'assets' / 'images' / 'scene2_fabric_flat.png'

def log(msg):
    print(msg)
    with open(LOG, 'w', encoding='utf-8') as f:
        f.write(str(msg) + '\n')

client = ComfyUIClient()

# Upload fabric
log("Uploading fabric.jpg ...")
server_name = client.upload_image(FABRIC_REF, 'om_fabric_src.png')
log(f"Uploaded as: {server_name}")

# Load and patch Klein workflow
wf = json.loads(Path(KLEIN_WF).read_text(encoding='utf-8'))

# Override node 76's image with uploaded file
log(f"Patching node 76 image to: {server_name}")
wf['76']['inputs']['image'] = server_name

# Submit directly
log("Submitting workflow ...")
prompt_id = client.submit(wf)
log(f"prompt_id: {prompt_id}")

# Poll with longer timeout
log("Polling for completion (300s) ...")
try:
    entry = client.poll(prompt_id, timeout=300, interval=5)
    status = entry.get('status', {})
    log(f"Status: {status.get('status_str')} | completed={status.get('completed')}")

    outputs = entry.get('outputs', {})
    log(f"Output nodes: {list(outputs.keys())}")

    if not outputs:
        log("No outputs! Checking messages:")
        for msg in status.get('messages', []):
            log(f"  {msg}")

    # Try downloading from node 9
    node9 = outputs.get('9', {})
    log(f"Node 9 content: {str(node9)[:300]}")

    if node9 and 'images' in node9:
        items = node9['images']
        log(f"Found {len(items)} images on node 9!")
        for item in items:
            dest_path = Path(DEST)
            client.download(item['filename'], item.get('subfolder', ''), dest_path, item.get('type', 'output'))
            log(f"Downloaded: {dest_path}")
    else:
        log("Node 9 has no images — this is the bug!")

except Exception as e:
    log(f"Error: {e}")
