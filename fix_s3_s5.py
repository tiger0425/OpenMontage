"""
Scene 3 手图 + Scene 3 视频 + Scene 5 CTA 重新生成
"""
import json, os, shutil, time, uuid, requests
from pathlib import Path

COMFYUI_URL        = "http://127.0.0.1:8188"
COMFYUI_INPUT_DIR  = Path("E:/ComfyUI_ROB2700/ComfyUI/input")
COMFYUI_OUTPUT_DIR = Path("E:/ComfyUI_ROB2700/ComfyUI/output")
ASSETS_DIR         = Path("E:/YifuAIForge/OpenMontage/projects/fabric-showcase-silk/assets")
WF_DIR             = Path("E:/YifuAIForge/OpenMontage/tools/_comfyui/workflows")
FABRIC_REF         = Path("E:/YifuAIForge/OpenMontage/fabric.jpg")
LOG_FILE           = ASSETS_DIR / "gen_log.txt"
LTX_FRAMES         = 97

def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")

def load_workflow(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def set_load_image(workflow, node_id, filename):
    workflow[node_id]["inputs"]["image"] = filename

def set_clip_text(workflow, node_id, text):
    workflow[node_id]["inputs"]["text"] = text

def set_primitive_int(workflow, node_id, value):
    workflow[node_id]["inputs"]["value"] = value

def submit_workflow(workflow):
    resp = requests.post(f"{COMFYUI_URL}/prompt",
        json={"prompt": workflow, "client_id": str(uuid.uuid4())}, timeout=30)
    resp.raise_for_status()
    return resp.json()["prompt_id"]

def get_history(prompt_id, max_wait=600):
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            data = resp.json()
            entry = data.get(prompt_id, {})
            s = entry.get("status", {}).get("status_str", "")
            if s == "success":
                return entry
            elif s == "error":
                raise RuntimeError(f"Failed: {entry}")
        except Exception as e:
            print(f"  poll: {e}")
        time.sleep(5)
    raise TimeoutError("Timeout")

def find_output(history):
    files = []
    for v in history.get("outputs", {}).values():
        for k in ["images", "gifs", "video", "mp4"]:
            if k in v:
                files.extend(v[k])
    return files

def copy_output(filename, dest):
    src = COMFYUI_OUTPUT_DIR / filename
    if not src.exists():
        for root, dirs, files in os.walk(COMFYUI_OUTPUT_DIR):
            for f in files:
                if f == filename or filename in f:
                    src = Path(root) / f
                    break
    shutil.copy2(src, dest)
    return dest

def copy_to_input(name):
    src = ASSETS_DIR / name
    if not src.exists():
        for root, dirs, files in os.walk(COMFYUI_OUTPUT_DIR):
            for f in files:
                if name.replace(".jpg","").replace(".png","") in f:
                    src = Path(root) / f
                    break
    if src.exists():
        shutil.copy2(src, COMFYUI_INPUT_DIR / name)

# ═══ Scene 5 CTA — 无文字 ════════════════════════════════════════════════════
log("[Scene5] CTA（禁文字）...")
klein_wf = load_workflow(WF_DIR / "klein_fabric.json")
wf5 = json.loads(json.dumps(klein_wf))
set_load_image(wf5, "76", "fabric-original.jpg")
set_clip_text(wf5, "114:113",
    "Dark matte background, elegant premium aesthetic. "
    "Fabric texture subtly visible as background accent. "
    "Minimal, refined, sophisticated composition. "
    "No text, no letters, no words, no symbols, no characters. "
    "No watermark. Vertical 9:16."
)
set_primitive_int(wf5, "114:112", 50020)
prompt_id = submit_workflow(wf5)
entry = get_history(prompt_id)
files = find_output(entry)
if files:
    filename = files[0]["filename"] if isinstance(files[0], dict) else files[0]
    copy_output(filename, ASSETS_DIR / "scene5_cta.jpg")
    log(f"  OK: scene5_cta.jpg")
else:
    log("  ERROR S5")

# ═══ Scene 3 手图 — 五指完整 ════════════════════════════════════════════════
log("[Scene3] 手图（五指完整）...")
wf3 = json.loads(json.dumps(klein_wf))
set_load_image(wf3, "76", "fabric-original.jpg")
set_clip_text(wf3, "114:113",
    "Elegant hand touching fabric surface, close-up. "
    "Hand has exactly five complete fingers, all visible and proportional. "
    "Fingers fully drawn, no missing fingers, no partial fingers. "
    "Natural relaxed hand posture, natural skin tone. "
    "Fabric fills most of the frame, hand is small portion. "
    "No jewelry, no nail polish, no rings, no watches. "
    "Soft diffused light, shallow depth of field. "
    "No text, no watermark. Vertical 9:16."
)
set_primitive_int(wf3, "114:112", 30020)
prompt_id = submit_workflow(wf3)
entry = get_history(prompt_id)
files = find_output(entry)
if files:
    filename = files[0]["filename"] if isinstance(files[0], dict) else files[0]
    copy_output(filename, ASSETS_DIR / "scene3_firstframe.jpg")
    copy_to_input("scene3_firstframe.jpg")
    log(f"  OK: scene3_firstframe.jpg")
else:
    log("  ERROR S3 img")

# ═══ Scene 3 视频 — 手慢慢抚摸，不抬手 ════════════════════════════════════════
log("[Scene3] 手触视频（慢慢抚摸，禁止抬手）...")
ltx_wf = load_workflow(WF_DIR / "ltx23_fabric.json")
wf_v3 = json.loads(json.dumps(ltx_wf))
set_load_image(wf_v3, "59", "scene3_firstframe.jpg")
set_clip_text(wf_v3, "69:5",
    "Fingers slowly and gently stroke the fabric surface, "
    "hand remains in contact with fabric at all times, "
    "no lifting, no lifting off, no raising, no detachment. "
    "Fingers move continuously and smoothly across the fabric texture. "
    "Hand stays low and close to fabric surface. "
    "Static camera. Quiet ambient room tone."
)
set_clip_text(wf_v3, "69:6",
    "text, subtitles, caption, watermark, logo, signage, letter, word, character, "
    "hand lifts off, hand raises, hand lifts, hand detaches from fabric, "
    "fingers separate, fingers spread apart, "
    "sudden movement, jump, bounce, distorted, deformed, "
    "satin sheen, silk shine, glossy"
)
set_primitive_int(wf_v3, "69:10", LTX_FRAMES)
set_primitive_int(wf_v3, "69:16", 30020)
prompt_id = submit_workflow(wf_v3)
log(f"  prompt_id: {prompt_id} (~3-5min)...")
entry = get_history(prompt_id, max_wait=600)
files = find_output(entry)
if files:
    filename = files[0]["filename"] if isinstance(files[0], dict) else files[0]
    copy_output(filename, ASSETS_DIR / "scene3_video.mp4")
    log(f"  OK: scene3_video.mp4")
else:
    log("  ERROR S3 vid")

log("Done")
