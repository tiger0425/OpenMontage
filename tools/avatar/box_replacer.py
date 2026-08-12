"""头像框替换工具：把视频中固定位置的解说头像框替换为数字人形象。

策略：基于头像框位置区域（样片验证：左下角固定矩形），用 FFmpeg 在固定区域
覆盖数字人形象图。不依赖人脸检测模型，对低分辨率 Shorts 鲁棒。

二创模式（MarkHasara）下，头像框替换是画面处理核心步骤：
1. 位置来源：config `avatar.box_hint`（lower_left/lower_right/upper_left/upper_right）
   或显式 box_region [x, y, w, h]（像素，可先跑 detect 模式自动找一次）
2. 替换：把数字人形象图 scale 到区域大小，用 FFmpeg overlay 覆盖
3. 透明支持：形象图为 PNG 带 alpha 时直接叠；否则不透明覆盖
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from tools.base_tool import (
    BaseTool,
    ToolResult,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolRuntime,
)

# 常见头像框位置 hint → 区域比例 [x_ratio, y_ratio, w_ratio, h_ratio]（相对画面）
BOX_HINTS = {
    "lower_left": [0.0, 0.55, 0.35, 0.30],      # 缩小：真实头像框约 30%x25%
    "lower_left_small": [0.02, 0.58, 0.28, 0.24],
    "lower_right": [0.55, 0.55, 0.35, 0.30],
    "upper_left": [0.0, 0.05, 0.35, 0.30],
    "upper_right": [0.55, 0.05, 0.35, 0.30],
}

# yunet 人脸检测模型路径（用于检测画面是否真有头像框）
FACE_MODEL = r"E:/YifuAIForge/OpenMontage/models/face/face_detection_yunet.onnx"


class BoxReplacer(BaseTool):
    name = "box_replacer"
    capability = "avatar"
    provider = "ffmpeg"
    runtime: ToolRuntime = ToolRuntime.LOCAL

    input_schema = {
        "type": "object",
        "properties": {
            "input_path": {"type": "string", "description": "输入视频路径"},
            "image_path": {"type": "string", "description": "数字人形象图路径（PNG 带 alpha 最佳）"},
            "output_path": {"type": "string", "description": "输出视频路径"},
            "box_hint": {
                "type": "string",
                "enum": list(BOX_HINTS.keys()),
                "description": "头像框位置 hint（按样片验证，MarkHasara 默认 lower_left）",
            },
            "box_region": {
                "type": "array",
                "items": {"type": "number"},
                "description": "显式区域 [x, y, w, h]（像素）。优先于 box_hint",
            },
            "opacity": {"type": "number", "description": "不透明覆盖时的透明度 0-1（默认 1.0）"},
            "detect_first": {
                "type": "boolean",
                "description": "先用 yunet 人脸检测确认左下区域存在头像框，无则跳过替换（默认 true）",
            },
            "force": {
                "type": "boolean",
                "description": "跳过人脸检测强制替换（默认 false）",
            },
        },
        "required": ["input_path", "image_path", "output_path"],
    }

    def _detect_left_lower_face(self, input_path: Path, sample_frames: int = 6,
                                expand_w: float = 1.4, expand_h: float = 2.0) -> Optional[tuple[int, int, int, int]]:
        """用 yunet 检测画面左下区域的人脸（解说头像框）。

        返回竖长头像框区域 [x, y, w, h]（匹配头像框实际比例：帽子+人脸+上身，
        约 1:2.2 竖长，占画面左下约 1/4 区域）。无则返回 None。
        expand_w/expand_h: 人脸框横向/纵向扩展系数。
        上扩较多（覆盖帽子顶部 + 形象图发冠），下扩覆盖上身。
        """
        import cv2
        cap = cv2.VideoCapture(str(input_path))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            total = 100
        detector = cv2.FaceDetectorYN_create(FACE_MODEL, "", (w, h))
        best = None  # (area, region)
        for i in range(sample_frames):
            pos = int(total * i / sample_frames)
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if not ok:
                continue
            _, faces = detector.detect(frame)
            if faces is None:
                continue
            for f in faces:
                x, y, fw, fh = f[0], f[1], f[2], f[3]
                cx, cy = x + fw / 2, y + fh / 2
                if cx < w * 0.5 and cy > h * 0.5:
                    # 竖长区域：人脸框为准，横向扩 1.6x，纵向扩 3.0x
                    # 上扩 45%（覆盖帽子顶部 + 形象图发冠），下扩 55%（覆盖上身）
                    bw = int(fw * expand_w)
                    bh = int(fh * expand_h)
                    bx = int(x - (bw - fw) * 0.5)
                    by = int(y - (bh - fh) * 0.45)
                    bx = max(0, min(bx, w - bw))
                    by = max(0, min(by, h - bh))
                    if bw <= 0 or bh <= 0:
                        continue
                    area = bw * bh
                    if best is None or area > best[0]:
                        best = (area, (bx, by, bw, bh))
        cap.release()
        return best[1] if best else None

    def _image_size(self, image_path: Path) -> tuple[int, int]:
        """读取图片宽高 (w, h)。"""
        from PIL import Image
        try:
            with Image.open(image_path) as im:
                return im.size
        except Exception:
            return 0, 0

    def _probe_video(self, input_path: Path) -> tuple[int, int]:
        """用 ffprobe 读视频分辨率 (w, h)。"""
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0", str(input_path),
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
        w, h = out.split(",")[:2]
        return int(w), int(h)

    def _resolve_region(self, inputs: dict, w: int, h: int) -> tuple[int, int, int, int]:
        """解析头像框区域为像素 [x, y, w, h]。"""
        if inputs.get("box_region"):
            x, y, bw, bh = [int(v) for v in inputs["box_region"]]
            return x, y, bw, bh
        hint = inputs.get("box_hint", "lower_left")
        rx, ry, rw, rh = BOX_HINTS[hint]
        return int(w * rx), int(h * ry), int(w * rw), int(h * rh)

    def _has_alpha(self, image_path: Path) -> bool:
        """判断形象图是否有透明通道（PNG）。"""
        suffix = image_path.suffix.lower()
        return suffix in (".png", ".webp")

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        image_path = Path(inputs["image_path"])
        output_path = Path(inputs["output_path"])

        if not input_path.exists():
            return ToolResult(success=False, error=f"输入视频不存在: {input_path}")
        if not image_path.exists():
            return ToolResult(success=False, error=f"形象图不存在: {image_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        w, h = self._probe_video(input_path)
        # 优先用检测到的人脸框区域（放大覆盖头像框），无检测时回退 hint
        detected = None
        if not inputs.get("force", False):
            try:
                detected = self._detect_left_lower_face(input_path)
            except Exception:
                detected = None

        skip_if_no_face = inputs.get("skip_if_no_face", True)
        if detected is None and skip_if_no_face and not inputs.get("force", False):
            # 无头像框：跳过替换，输出原视频副本，标记 replaced=false
            shutil.copy2(input_path, output_path)
            return ToolResult(
                success=True,
                data={
                    "output_path": str(output_path),
                    "region": None,
                    "resolution": f"{w}x{h}",
                    "replaced": False,
                    "note": "未检测到左下头像框，跳过替换",
                },
            )

        if detected is not None:
            x, y, bw, bh = detected
        else:
            x, y, bw, bh = self._resolve_region(inputs, w, h)
        opacity = float(inputs.get("opacity", 1.0))

        # 形象图适配竖长头像框：先按区域宽高比裁剪（保留人脸居中），再等比缩放铺满
        img_w, img_h = self._image_size(image_path)
        if img_w <= 0 or img_h <= 0:
            return ToolResult(success=False, error=f"无法读取形象图尺寸: {image_path}")

        # 裁剪比例 = 区域宽高比
        target_ratio = bh / bw if bw > 0 else 1.0  # 区域 高/宽
        img_ratio = img_h / img_w                  # 形象图 高/宽
        crop_cmd_extra = ""
        if img_ratio > target_ratio:
            # 形象图更瘦高：裁掉上下（保留中央），按宽度匹配
            crop_h = int(img_w * target_ratio)
            crop_y = int((img_h - crop_h) / 2)
            crop_cmd_extra = f"crop={img_w}:{crop_h}:0:{crop_y},"
        elif img_ratio < target_ratio:
            # 形象图更矮胖：裁掉左右（保留中央），按高度匹配
            crop_w = int(img_h / target_ratio)
            crop_x = int((img_w - crop_w) / 2)
            crop_cmd_extra = f"crop={crop_w}:{img_h}:{crop_x}:0,"

        # 等比缩放铺满区域（裁剪后比例与区域一致，无拉伸）
        tmp = Path(tempfile.mkdtemp()) / "avatar_scaled.png"
        scale_cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(image_path),
            "-vf", f"{crop_cmd_extra}scale={bw}:{bh}",
            str(tmp),
        ]
        subprocess.run(scale_cmd, timeout=120)

        ox, oy = x, y

        # 覆盖（透明形象图叠到检测区域）
        overlay_vf = f"[1:v]format=rgba[img];[0:v][img]overlay={ox}:{oy}[vout]"
        if not self._has_alpha(image_path) and opacity < 1.0:
            overlay_vf = (
                f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[img];"
                f"[0:v][img]overlay={ox}:{oy}[vout]"
            )
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(input_path),
            "-i", str(tmp),
            "-filter_complex", overlay_vf,
            "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "copy",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return ToolResult(success=False, error=f"FFmpeg overlay 失败: {result.stderr[-500:]}")

        return ToolResult(
            success=True,
            data={
                "output_path": str(output_path),
                "region": [x, y, bw, bh],
                "resolution": f"{w}x{h}",
                "replaced": True,
                "detected": detected is not None,
            },
        )
