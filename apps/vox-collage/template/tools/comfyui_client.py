# -*- coding: utf-8 -*-
"""VOX Collage ComfyUI 客户端 (comfyui_client.py)

把 vox-collage 的两个重阶段真正接到本地 ComfyUI（此前 CLI 里是空壳）：
  - stills : Qwen-Image-Edit 2.1（wf_edit.json）风格化资料图
  - motion : MiniMax H3 Ref2Video（wf_vid.json）图层动效

纯 requests 调用：/upload/image -> /prompt -> /history -> /view，配合 /free 回收显存。
"""

import os
import time
from pathlib import Path

import requests

SERVER = os.environ.get("COMFYUI_SERVER_URL", "http://127.0.0.1:8188").rstrip("/")


class ComfyUIError(RuntimeError):
    pass


def is_up(timeout: float = 5.0) -> bool:
    try:
        requests.get(f"{SERVER}/system_stats", timeout=timeout)
        return True
    except Exception:
        return False


def free_memory() -> None:
    """释放 ComfyUI 常驻显存（进入下一个重阶段前调用，避免 24GB 被击穿）。"""
    try:
        requests.post(
            f"{SERVER}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=60,
        )
    except Exception:
        pass


def upload_image(local_path: Path, name: str) -> str:
    """上传本地图片到 ComfyUI input 目录，返回 LoadImage 可用的名称（含子目录）。"""
    local_path = Path(local_path)
    if not local_path.exists():
        raise ComfyUIError(f"upload source missing: {local_path}")
    with open(local_path, "rb") as f:
        files = {"image": (name, f, "image/png")}
        data = {"overwrite": "true", "type": "input"}
        r = requests.post(f"{SERVER}/upload/image", files=files, data=data, timeout=180)
    if r.status_code != 200:
        raise ComfyUIError(f"upload failed {r.status_code}: {r.text[:200]}")
    j = r.json()
    sub = j.get("subfolder") or ""
    return f"{sub}/{j['name']}" if sub else j["name"]


def queue_prompt(workflow: dict, client_id: str = "vox-collage") -> str:
    r = requests.post(
        f"{SERVER}/prompt",
        json={"prompt": workflow, "client_id": client_id},
        timeout=120,
    )
    if r.status_code != 200:
        raise ComfyUIError(f"queue failed {r.status_code}: {r.text[:500]}")
    return r.json()["prompt_id"]


def wait_prompt(prompt_id: str, timeout: float = 3600.0, poll: float = 2.0, on_tick=None) -> dict:
    start = time.time()
    while True:
        h = {}
        try:
            h = requests.get(f"{SERVER}/history/{prompt_id}", timeout=30).json()
        except Exception:
            h = {}
        if prompt_id in h:
            rec = h[prompt_id]
            st = rec.get("status") or {}
            if str(st.get("status_str", "")).lower() == "error":
                # 节点执行失败必须炸出来：此前直接 return，调用方只看到"无图像产物"而静默跳过
                detail = ""
                for m in (st.get("messages") or []):
                    if isinstance(m, (list, tuple)) and len(m) > 1 and isinstance(m[1], dict):
                        d = m[1]
                        if d.get("exception_message"):
                            detail = (f"{d.get('node_type')}@{d.get('node_id')}: "
                                      f"{d.get('exception_type')}: {d.get('exception_message')}")
                            break
                raise ComfyUIError(f"ComfyUI prompt {prompt_id} failed: {detail or st}")
            return rec
        if time.time() - start > timeout:
            raise ComfyUIError(f"timeout after {int(timeout)}s waiting prompt {prompt_id}")
        if on_tick:
            try:
                on_tick(time.time() - start)
            except Exception:
                pass
        time.sleep(poll)


def outputs_of(history: dict) -> list:
    """把 history.outputs 展平为 [{filename, subfolder, type, kind}]。"""
    out = []
    for _node_id, node_out in (history.get("outputs") or {}).items():
        for kind, items in (node_out or {}).items():
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and it.get("filename"):
                        out.append({**it, "kind": kind})
    return out


def download_output(item: dict, dest: Path) -> Path:
    params = {"filename": item["filename"], "type": item.get("type", "output")}
    if item.get("subfolder"):
        params["subfolder"] = item["subfolder"]
    r = requests.get(f"{SERVER}/view", params=params, timeout=600)
    if r.status_code != 200:
        raise ComfyUIError(f"download failed {r.status_code}: {item.get('filename')}")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest
