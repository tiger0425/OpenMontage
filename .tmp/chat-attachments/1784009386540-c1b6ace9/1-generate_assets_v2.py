import json
import os
import shutil
import time
import uuid
import requests


COMFYUI_URL = "http://127.0.0.1:8188"
COMFYUI_INPUT_DIR = "E:/ComfyUI_ROB2700/ComfyUI/input"
COMFYUI_OUTPUT_DIR = "E:/ComfyUI_ROB2700/ComfyUI/output"
PROJECT_DIR = "videos/fabric-promo"
ASSETS_DIR = f"{PROJECT_DIR}/assets"

# Valid LTX frame counts: (n-1) % 8 == 0
LTX_FRAMES = 97  # ~4 seconds at 24fps


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
    client_id = str(uuid.uuid4())
    payload = {
        "prompt": workflow,
        "client_id": client_id
    }
    resp = requests.post(f"{COMFYUI_URL}/prompt", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_history(prompt_id, max_wait=1200):
    start = time.time()
    while time.time() - start < max_wait:
        try:
            resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            data = resp.json()
            if prompt_id in data and data[prompt_id].get("status", {}).get("status_str") == "success":
                return data[prompt_id]
            elif prompt_id in data and data[prompt_id].get("status", {}).get("status_str") == "error":
                raise RuntimeError(f"Generation failed: {data[prompt_id]}")
        except Exception as e:
            print(f"  poll error: {e}")
        time.sleep(5)
    raise TimeoutError(f"Generation did not complete within {max_wait}s")


def find_output_files(history, output_type):
    outputs = history.get("outputs", {})
    files = []
    for node_id, node_outputs in outputs.items():
        if output_type in node_outputs:
            files.extend(node_outputs[output_type])
        if output_type == "gifs":
            for alt in ["video", "mp4", "images"]:
                if alt in node_outputs:
                    files.extend(node_outputs[alt])
    return files


def copy_output_to_assets(filename, dest_name):
    src = os.path.join(COMFYUI_OUTPUT_DIR, filename)
    if not os.path.exists(src):
        for root, dirs, files in os.walk(COMFYUI_OUTPUT_DIR):
            if filename in files:
                src = os.path.join(root, filename)
                break
    if not os.path.exists(src):
        raise FileNotFoundError(f"Output file not found: {filename}")
    dest = os.path.join(ASSETS_DIR, dest_name)
    shutil.copy2(src, dest)
    print(f"  copied {src} -> {dest}")
    return dest


def copy_to_input(filename, dest_name=None):
    src = os.path.join(ASSETS_DIR, filename)
    name = dest_name or filename
    dest = os.path.join(COMFYUI_INPUT_DIR, name)
    shutil.copy2(src, dest)
    print(f"  copied to input: {dest}")
    return name


def run_job(name, workflow, output_type, dest_name, modifications, copy_input_as=None):
    print(f"\n=== Running: {name} ===")
    wf = json.loads(json.dumps(workflow))  # deep copy
    for mod in modifications:
        mod(wf)
    
    debug_path = os.path.join(ASSETS_DIR, f"workflow_{name}.json")
    with open(debug_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    
    result = submit_workflow(wf)
    prompt_id = result["prompt_id"]
    print(f"  submitted prompt_id: {prompt_id}")
    
    history = get_history(prompt_id, max_wait=1200)
    files = find_output_files(history, output_type)
    if not files:
        print(json.dumps(history, indent=2, ensure_ascii=False))
        raise RuntimeError(f"No {output_type} output found in history")
    
    filename = files[0]["filename"] if isinstance(files[0], dict) else files[0]
    print(f"  output: {filename}")
    asset_path = copy_output_to_assets(filename, dest_name)
    
    if copy_input_as:
        copy_to_input(dest_name, copy_input_as)
    
    return asset_path


# Load base workflows
klein_wf = load_workflow(f"{ASSETS_DIR}/klein_workflow.json")
ltx23_wf = load_workflow(f"{ASSETS_DIR}/ltx23_workflow.json")

os.makedirs(ASSETS_DIR, exist_ok=True)

jobs = []

# Job 1: Klein fabric base (no hand) for fabric scene video
jobs.append((
    "klein_fabric_base",
    klein_wf,
    "images",
    "klein_fabric_base.jpg",
    [
        lambda wf: set_load_image(wf, "76", "fabric-original.jpg"),
        lambda wf: set_clip_text(wf, "114:113",
            "Art film still, cinematic top-down shot of vintage red plaid linen-cotton fabric "
            "draped on a weathered wooden table. Soft golden window light from the left, "
            "gentle shadows, muted film color palette. Visible linen slub texture, "
            "brick-red and dark brown woven plaid, matte finish. Quiet contemplative mood, "
            "minimal composition. No hand, no person. 35mm film grain, shallow depth of field."),
    ],
    "klein_fabric_base.jpg"
))

# Job 2: Klein hand on fabric (separate hand overlay, Plan B)
jobs.append((
    "klein_hand_fabric",
    klein_wf,
    "images",
    "klein_hand_fabric.jpg",
    [
        lambda wf: set_load_image(wf, "76", "fabric-original.jpg"),
        lambda wf: set_clip_text(wf, "114:113",
            "Intimate art film close-up, elegant young woman's hand with exactly five fingers "
            "gently resting on vintage red plaid linen-cotton fabric. Perfect hand anatomy, "
            "smooth skin, no wrinkles, no veins, no jewelry, no nail polish. "
            "Soft golden window light, warm muted tones, 35mm film grain. "
            "Weathered wooden table, poetic tactile moment, contemplative mood."),
    ],
    "klein_hand_fabric.jpg"
))

# Job 3: Klein model wearing shirt (fashion first frame)
jobs.append((
    "klein_model_shirt",
    klein_wf,
    "images",
    "klein_model_shirt.jpg",
    [
        lambda wf: set_load_image(wf, "76", "fabric-original.jpg"),
        lambda wf: set_clip_text(wf, "114:113",
            "Art house fashion film, full body vertical shot. Asian woman in bright minimalist room, "
            "wearing relaxed red plaid linen-cotton shirt and tailored beige trousers. "
            "Brick-red and dark brown plaid, natural weave texture. "
            "Side profile, no visible face, contemplative elegant pose. "
            "Soft golden window light, muted film tones, 35mm grain. "
            "Natural body proportions, quiet sophisticated mood. No text, no logo."),
    ],
    "klein_model_shirt.jpg"
))

# Job 4: LTX23 fabric motion (subtle, no jumping)
jobs.append((
    "ltx_fabric_motion",
    ltx23_wf,
    "gifs",
    "ltx_fabric_motion.mp4",
    [
        lambda wf: set_load_image(wf, "59", "klein_fabric_base.jpg"),
        lambda wf: set_clip_text(wf, "69:5",
            "Cinematic still life of vintage red plaid linen-cotton fabric on weathered wood. "
            "Golden window light from the left, muted film tones. "
            "Subtle surface movement, gentle light shift across the weave. "
            "No hand, no person. Static camera. Quiet ambient room tone."),
        lambda wf: set_clip_text(wf, "69:6",
            "text, subtitles, caption, watermark, logo, signage, letter, word, character, "
            "hand, person, jump, bounce, sudden movement, distorted, deformed"),
        lambda wf: set_primitive_int(wf, "69:10", LTX_FRAMES),
    ]
))

# Job 5: LTX23 model life (minimal movement, elegant)
jobs.append((
    "ltx_model_life",
    ltx23_wf,
    "gifs",
    "ltx_model_life.mp4",
    [
        lambda wf: set_load_image(wf, "59", "klein_model_shirt.jpg"),
        lambda wf: set_clip_text(wf, "69:5",
            "Art film full body portrait of Asian woman in red plaid linen shirt and beige trousers. "
            "Bright minimalist room, soft golden window light, muted film tones. "
            "She shifts weight slightly with calm stillness. "
            "Camera holds static at waist height. Quiet ambient room tone."),
        lambda wf: set_clip_text(wf, "69:6",
            "text, subtitles, caption, watermark, logo, signage, letter, word, character, "
            "jump, bounce, sudden movement, distorted face, deformed hands, unrealistic body, "
            "plastic, silk, satin"),
        lambda wf: set_primitive_int(wf, "69:10", LTX_FRAMES),
    ]
))


if __name__ == "__main__":
    print("Starting ComfyUI generation jobs (v2 with LTX prompting guide)...")
    
    results = []
    for job in jobs:
        try:
            result_path = run_job(*job)
            results.append((job[0], result_path))
            print(f"  SUCCESS: {result_path}")
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append((job[0], f"FAILED: {e}"))
    
    print("\n=== Generation Summary ===")
    for name, path in results:
        print(f"{name}: {path}")
