"""IndexTTS 常驻服务进程 — 模型只加载一次，通过 stdin 接收 JSON 指令（唯一服务端）。

备注：双入口历史——本文件为唯一服务端实现，客户端规范入口为 apps/indextts-bridge/client.py:IndexTTSSession，
旧桥 D:/index-tts/indextts_server.py 已删除（见 CALLING.md 杂音陷阱），pipeline_automator 侧自持的
_get/_synthesize 仅为兼容封装，新代码勿再自建 Popen。

支持 IndexTTS-2.5 与 IndexTTS-2 双版本（--version 2.5|2）：
  - 2.5: indextts/infer_v2_5.py，use_bf16 默认，lang/duration_factor，use_qwen_emo
  - 2:   indextts/infer_v2.py，use_fp16，无 lang/duration_factor

用法：
  python indextts_server.py --version 2.5 [--checkpoints <dir>] [--use-qwen-emo]

协议（每行一个 JSON）：
  请求:  {"id": "seg_1", "text": "...", "output_path": "...",
          "voice_ref": "...", "lang": "ZH", "duration_factor": 1.0,
          "seed": 42, "emo_vector": [...], "use_emo_text": bool}
  响应:  {"id": "seg_1", "ok": true, "path": "..."}
         {"id": "seg_1", "ok": false, "error": "..."}
  退出:  关闭 stdin 或 {"cmd": "exit"}

零变速：不做 atempo，仅音量归一化。
"""
import json
import sys
import os
import argparse
import threading
from pathlib import Path

# 编码修复：父进程（OpenMontage 桥接）按 UTF-8 传输 JSON 协议。
# Windows 下 venv Python 默认 stdin/stdout 为 GBK，会导致中文乱码，
# 必须统一重配为 UTF-8（在任何读写之前执行）。
if hasattr(sys.stdin, "reconfigure"):
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 关键：把 stdout 替换为 stderr 代理，stdout 只用于协议。
# 这样模型内部的 print（"All auxiliary models ready" 等）全部落到 stderr，
# 不会污染 stdout 的 JSON 协议流。
_PROTOCOL_STDOUT = sys.stdout
if hasattr(_PROTOCOL_STDOUT, "reconfigure"):
    try:
        _PROTOCOL_STDOUT.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
sys.stdout = sys.stderr

# 音量归一化目标
TARGET_RMS = 3500

def normalize_volume(wav_path, target_rms=TARGET_RMS):
    import numpy as np
    import scipy.io.wavfile as wavfile
    try:
        sr, data = wavfile.read(str(wav_path))
    except Exception:
        return
    audio = data.astype(np.float32)
    if audio.max() > 0:
        audio = audio / 32768.0
    rms = float(np.sqrt(np.mean(audio**2)))
    if rms > 0:
        audio = audio * (target_rms / (rms * 32768.0))
    peak = float(np.abs(audio).max())
    if peak > 0.95:
        audio = audio * (0.95 / peak)
    out_i16 = (audio * 32767.0).astype(np.int16)
    wavfile.write(str(wav_path), sr, out_i16)


def build_model(version: str, checkpoints: Path, use_qwen_emo: bool):
    """按版本构造 IndexTTS 模型，返回 (model, infer_fn_uses_lang, use_bf16)。"""
    import torch

    if version == "2.5":
        from indextts.infer_v2_5 import IndexTTS2
        print(f">> loading IndexTTS-2.5 model (checkpoints={checkpoints})...", flush=True)
        model = IndexTTS2(
            cfg_path=str(checkpoints / "config.yaml"),
            model_dir=str(checkpoints),
            use_bf16=True,
            device="cuda",
            use_qwen_emo=use_qwen_emo,
        )
        return model, True
    else:  # "2"
        from indextts.infer_v2 import IndexTTS2
        print(f">> loading IndexTTS-2 model (checkpoints={checkpoints})...", flush=True)
        model = IndexTTS2(
            cfg_path=str(checkpoints / "config.yaml"),
            model_dir=str(checkpoints),
            use_fp16=True,
            device="cuda",
            use_qwen_emo=True,
        )
        return model, False


def main():
    parser = argparse.ArgumentParser(description="IndexTTS 常驻服务")
    parser.add_argument("--version", choices=["2.5", "2"], default="2.5",
                        help="IndexTTS 模型版本（2.5 默认）")
    parser.add_argument("--checkpoints", default=None,
                        help="checkpoints 目录（默认：脚本同级 checkpoints/ 或 checkpoints_2/）")
    parser.add_argument("--use-qwen-emo", action="store_true",
                        help="2.5 版本加载 QwenEmotion（use_emo_text 需要）")
    args = parser.parse_args()

    import torch

    repo = Path(__file__).resolve().parent
    if args.checkpoints:
        ckpt_dir = Path(args.checkpoints)
    elif args.version == "2":
        ckpt_dir = repo / "checkpoints_2"
    else:
        ckpt_dir = repo / "checkpoints"

    model, uses_lang = build_model(args.version, ckpt_dir, args.use_qwen_emo)
    print(">> model ready", flush=True)

    req_queue = []
    lock = threading.Lock()
    cond = threading.Condition(lock)
    results = {}

    def worker():
        while True:
            with cond:
                while not req_queue:
                    cond.wait()
                item = req_queue.pop(0)
            if item.get("cmd") == "exit":
                break
            rid = item["id"]
            try:
                text = item["text"]
                out_path = item["output_path"]
                voice_ref = item.get("voice_ref")
                seed = item.get("seed", 42)
                emo = item.get("emo_vector")  # None = 未指定
                explicit_use_emo_text = item.get("use_emo_text")
                emo_alpha = float(item.get("emo_alpha", 0.6))
                lang = item.get("lang") or "ZH"
                duration_factor = float(item.get("duration_factor", 1.0))
                # 去AI合成参数（可由客户端透传，无则用管线级去AI默认值）
                # 备注：temperature/top_p/top_k/repetition_penalty 为人耳听感“去AI”关键，
                # 默认走稳态（0.65/0.75/30/5.0）比官方 0.8/0.8/30/10 更少含糊与吃字。
                gen_temperature = float(item.get("temperature", 0.65))
                gen_top_p = float(item.get("top_p", 0.75))
                gen_top_k = int(item.get("top_k", 30))
                gen_repetition_penalty = float(item.get("repetition_penalty", 5.0))
                gen_max_mel_tokens = int(item.get("max_mel_tokens", 1000))

                # 三态情感语义：
                #   1) use_emo_text 显式 True  -> 自动判情感，覆盖 emo_vector
                #   2) use_emo_text 显式 False -> 固定情感：显式传了 emo_vector 才用
                #   3) 未指定 use_emo_text     -> 传了 emo_vector 则固定；否则纯净克隆（不注入情感）
                # 2.5 关键：固定 calm 不再注入 emo_vector（会触发情感-音色混合导致音色漂移），
                #          走官方纯净克隆路径（emo_vector=None, use_emo_text=False）保声纹。
                # 2 版本保持旧行为：未传 emo_vector 时默认 calm。
                calm_default = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
                if explicit_use_emo_text is True:
                    use_emo_text, emo_vector = True, None
                elif explicit_use_emo_text is False:
                    use_emo_text, emo_vector = False, emo
                else:
                    if emo is not None:
                        use_emo_text, emo_vector = False, emo
                    elif args.version == "2":
                        # 2 版本旧行为：未指定情感 → calm 固定向量
                        use_emo_text, emo_vector = False, calm_default
                    else:
                        # 2.5：未指定 → 纯净克隆（不注入情感，声纹保真）
                        use_emo_text, emo_vector = False, None

                torch.manual_seed(seed)
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(seed)

                os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
                infer_kwargs = {
                    "text": text,
                    "output_path": out_path,
                    "verbose": False,
                }
                if uses_lang:
                    # 2.5：lang 是必填位置参数
                    infer_kwargs["lang"] = lang
                    infer_kwargs["duration_factor"] = duration_factor
                if use_emo_text:
                    infer_kwargs["use_emo_text"] = True
                    infer_kwargs["emo_alpha"] = emo_alpha
                else:
                    infer_kwargs["emo_vector"] = emo_vector
                if voice_ref:
                    infer_kwargs["spk_audio_prompt"] = voice_ref
                # 去AI采样参数透传（温度/核采样/重复惩罚），无则用上文去AI默认值
                infer_kwargs["temperature"] = gen_temperature
                infer_kwargs["top_p"] = gen_top_p
                infer_kwargs["top_k"] = gen_top_k
                infer_kwargs["repetition_penalty"] = gen_repetition_penalty
                infer_kwargs["max_mel_tokens"] = gen_max_mel_tokens

                gen = model.infer(**infer_kwargs)
                for _ in gen:
                    pass

                normalize_volume(Path(out_path))
                results[rid] = {"id": rid, "ok": True, "path": out_path}
            except Exception as e:
                import traceback as _tb
                print(f">> ERROR {rid}: {e}", flush=True)
                _tb.print_exc()
                results[rid] = {"id": rid, "ok": False, "error": str(e)}
            with cond:
                cond.notify_all()

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    # 读取命令（stdin）→ 协议响应写到真实 stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            _PROTOCOL_STDOUT.write(json.dumps({"id": "?", "ok": False, "error": "bad json"}) + "\n")
            _PROTOCOL_STDOUT.flush()
            continue
        if req.get("cmd") == "exit":
            with cond:
                req_queue.append(req)
                cond.notify_all()
            break
        rid = req.get("id", "?")
        with cond:
            req_queue.append(req)
            cond.notify_all()
            while rid not in results:
                cond.wait()
            resp = results.pop(rid)
        _PROTOCOL_STDOUT.write(json.dumps(resp, ensure_ascii=False) + "\n")
        _PROTOCOL_STDOUT.flush()

    print(">> server exiting", flush=True)


if __name__ == "__main__":
    main()
