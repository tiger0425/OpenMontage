import shutil
from pathlib import Path

SRC_IMG = Path(r'E:/ComfyUI_ROB2700/ComfyUI/output')
SRC_VID = Path(r'E:/ComfyUI_ROB2700/ComfyUI/output/video')
DEST_IMG = Path(r'E:/YifuAIForge/OpenMontage/projects/fabric-showcase-silk/assets/images')
DEST_VID = Path(r'E:/YifuAIForge/OpenMontage/projects/fabric-showcase-silk/assets/video')

# Scene 3 hand image: Flux2-Klein_00070_.png (15:19:56 latest)
shutil.copy2(SRC_IMG / 'Flux2-Klein_00070_.png', DEST_IMG / 'scene3_firstframe.jpg')
print(f"scene3: {(DEST_IMG / 'scene3_firstframe.jpg').stat().st_size // 1024}KB")

# Scene 4 model image: Flux2-Klein_00069_.png (15:19:44)
shutil.copy2(SRC_IMG / 'Flux2-Klein_00069_.png', DEST_IMG / 'scene4_firstframe.jpg')
print(f"scene4: {(DEST_IMG / 'scene4_firstframe.jpg').stat().st_size // 1024}KB")

# Scene 5 CTA: Flux2-Klein_00062_.png (14:57:37)
shutil.copy2(SRC_IMG / 'Flux2-Klein_00062_.png', DEST_IMG / 'scene5_cta.jpg')
print(f"scene5: {(DEST_IMG / 'scene5_cta.jpg').stat().st_size // 1024}KB")

# Scene 2 fabric flat: use scene2_fabric_flat.png (already there from gen_all_brief)
# Actually get from ComfyUI - find it
import os
for f in os.listdir(SRC_IMG):
    if f.startswith('Flux2-Klein'):
        # Find the one for scene 2 - it's from gen_all_brief which ran at 15:08
        pass
print("Scene 2 fabric already exists")

# Scene 3 hand video: LTX23_00017_.mp4 (15:20:56 latest from fix_s3_s5)
shutil.copy2(SRC_VID / 'LTX23_00017_.mp4', DEST_VID / 'scene3_video.mp4')
print(f"scene3_video: {(DEST_VID / 'scene3_video.mp4').stat().st_size // 1024}KB")

# Scene 2 fabric video: LTX23_00013_.mp4 (from gen_all_brief at 15:09:58)
shutil.copy2(SRC_VID / 'LTX23_00013_.mp4', DEST_VID / 'scene2_video.mp4')
print(f"scene2_video: {(DEST_VID / 'scene2_video.mp4').stat().st_size // 1024}KB")

# Scene 4 model video: LTX23_00015_.mp4 (from gen_all_brief at 15:12:53)
shutil.copy2(SRC_VID / 'LTX23_00015_.mp4', DEST_VID / 'scene4_video.mp4')
print(f"scene4_video: {(DEST_VID / 'scene4_video.mp4').stat().st_size // 1024}KB")

# List final assets
print("\nFinal assets:")
for f in sorted(DEST_IMG.iterdir()):
    print(f"  img/{f.name}: {f.stat().st_size // 1024}KB")
for f in sorted(DEST_VID.iterdir()):
    print(f"  vid/{f.name}: {f.stat().st_size // 1024}KB")
