# Research: Video Inpainting Models for Hard-Coded Subtitle Removal

**Ticket:** Wayfinder research ticket #36 (GitHub tiger0425/OpenMontage#36)
**Scope:** Removing hard-coded/`burned-in` subtitle text regions from local video on a local NVIDIA GPU. Precision-first, slow-acceptable.
**Date:** Research compiled from primary sources (arXiv papers, official GitHub repos/READMEs, model cards, published benchmarks).

---

## TL;DR / Recommendation

For **precision-first** removal of hard-coded subtitle regions on a local GPU, use a **two-tier strategy**:

1. **Easy cases (static/plain background, small text region, few scene changes):** `ffmpeg` neighbor-frame copy/`inpaint` (near-zero cost) or **LaMa** (Apache-2.0, per-frame, no temporal module). Good enough for text sitting on flat/static regions.
2. **Hard cases (moving background, partial occlusion, frequent cuts, busy texture behind text):** **ProPainter** (ICCV 2023) — the current default base for subtitle-removal tools (e.g. `video-subtitle-remover`). Runtime multi-path (bidirectional propagation + sparse transformer + recurrent flow completion). Slow and VRAM-hungry, but the best precision for dynamic video.

**Final recommendation:** Build the pipeline with **ProPainter as the high-quality engine** and **LaMa / ffmpeg as the cheap fast-path**, selected per-clip by a mask/region classifier (static vs. dynamic). See the tiering section (§5) and comparison table (§7).

---

## 1. STTN — Spatial-Temporal Transformer Network (ECCV 2020)

**Sources:** [arXiv:2007.10247 / "Learning Joint Spatial-Temporal Transformations for Video Inpainting"](https://arxiv.org/abs/2007.10247), official repo [researchmm/STTN](https://github.com/researchmm/STTN). (ECCV 2020, Springer chapter [doi 10.1007/978-3-030-58517-4_31](https://link.springer.com/chapter/10.1007/978-3-030-58517-4_31).)

### Architecture
- STTN composes a **hard spatial-temporal attention** over **joint spatial-temporal transformations** of visible image patches. It treats video inpainting as a **multi-to-multi** problem: each missing pixel is filled by referencing coherent content from *multiple visible frames across time*, not just the current frame.
- Uses a **spatial-temporal Transformer** that searches for the most relevant patch features both spatially (within a frame) and temporally (across frames), then applies these to the masked region through a decoder.
- Standard encoder-decoder backbone with two branches (structure/content), and a discriminator for realism.

### Temporal mechanism
- **Patch-matching over a window of frames** (typically a small clip, e.g. 10–30 frames). The transformer finds corresponding visible patches in neighboring frames and composites them into the hole. This gives global temporal consistency because it reasons *jointly* over the clip rather than frame-by-frame.
- Limitation: attention depth/capacity is bounded; the transformer must implicitly learn motion, and it struggles when no visible frame shows the region's true content (e.g. a **moving object/background** that is always occluded by the mask, or strong camera motion).

### Known limits (well documented in later literature)
- **Blur / oversmoothing** in texture-rich regions because the patch-matching underperforms on fine, high-frequency structures.
- **Temporal artifacts / flicker** between frames when motion is large or discontinuous (frequent cuts).
- **Weak on moving backgrounds**: if the background behind the subtitle moves (pan/tilt, tracked camera, parallax), STTN's joint attention produces ghosting/streaking. It performs best when the masked region is on a **relatively static or slowly-moving surface**.
- Later papers (E2FGVI, ProPainter, FVI) all cite these STTN limitations as motivation. ProPainter explicitly notes STTN's lack of **explicit flow guidance** as why it handles motion poorly.

**Subtitle-relevance:** STTN is the *default engine* in the oldest VSR versions. It is slow (heavy transformer, must process a clip window), and on "highly dynamic, text-dense" subtitle regions it shows blur and residual ghosting — acceptable for static backgrounds, mediocre for dynamic ones.

**License / maturity:** Research code, pip-not-standard. Pretrained weights in the repo. **No explicit commercial-friendly license file** (research code — treat as research-use; CCA/unspecified). Community forks use it via the VSR web UI.

---

## 2. E2FGVI — End-to-End Flow-Guided Video Inpainting (CVPR 2022)

**Sources:** [arXiv:2204.02663 / "Towards An End-to-End Framework for Flow-Guided Video Inpainting"](https://arxiv.org/abs/2204.02663), official repo [MCG-NKU/E2FGVI](https://github.com/MCG-NKU/E2FGVI), IEEE [9878410](https://ieeexplore.ieee.org/abstract/document/9878410). Press coverage: [Nankai press release](https://encyber.nankai.edu.cn/2023/1225/c34753a533301/page.htm), [The Paper 视频P图新SOTA (推理速度快近15倍)](https://www.thepaper.cn/newsDetail_forward_18148747).

### Flow guidance
- Adds an **explicit optical-flow completion module**: given partial (incomplete) flows between frames, it **completes the missing flow** in masked regions. The completed flow then **warp-propagates visible pixels into the hole** across time — this is the key innovation over STTN (which tries to learn motion implicitly).
- End-to-end trainable flow completion + flow-guided feature propagation, integrated with a (smaller) spatial-temporal transformer for fine detail.

### Quality improvement over STTN
- **Large quantitative gains** over STTN on DAVIS, YouTube-VOS, and Vimeo-90K video-inpainting benchmarks (higher PSNR/SSIM, lower VFID/temporal inconsistency). The flow module removes most of the ghosting/streaking STTN exhibits on moving content because visible pixels are *transported* by actual motion rather than matched heuristically.
- On the **dynamic background + moving camera** cases where STTN fails, E2FGVI is substantially cleaner — directly relevant to subtitle removal over moving video.

### Speed / VRAM
- **~15× faster than STTN** at inference (widely reported in Nankai press and secondary coverage) — achieved by using flow-based propagation to avoid the full multi-frame transformer over every frame; only a lightweight transformer refines.
- **Arbitrary resolution support** (the model runs the flow network at native res, only a small transformer is fixed-size), which is a big practical win for HD video without cropping.
- VRAM is moderate (a few GB) — comfortably fits consumer cards (e.g. 6–8 GB), much lighter than ProPainter.

### Subtitles-relevance
- A clear step up from STTN for "highly dynamic" subtitle regions: moving logos, burn-ins over pans, and tracked-on-background text. Still noticeably behind ProPainter on very long/occluded/rapid transitions.

**License / maturity:** Research code from [MCG-NKU](https://github.com/MCG-NKU/E2FGVI); pretrained weights + inference scripts included. Community `pip` port (`e2fgvi` wrappers) exist; official is clone-and-run. **No explicit commercial-friendly license file** — treat as research-use (check before commercial deployment).

---

## 3. ProPainter — Improving Propagation and Transformer for Video Inpainting (ICCV 2023)

**Sources:** [arXiv:2309.03897 / ICCV 2023](https://arxiv.org/abs/2309.03897), official repo [sczhou/ProPainter](https://github.com/sczhou/ProPainter) (README raw: [raw.githubusercontent.com/sczhou/ProPainter/main/README.md](https://raw.githubusercontent.com/sczhou/ProPainter/main/README.md)). Same group lineage (Nankai / Shanghai Jiao Tong; Shanghai Jiao Tong SCSA authors: Shangchen Zhou, Chongyi Li, Kelvin C. K. Chan, Chen Change Loy).

### Core innovations
1. **Recurrent bidirectional optical-flow completion** — instead of one-shot flow fill, it completes flow **recurrently forward and backward** across the whole clip. This captures long-range motion (large displacement, occlusion) far better than E2FGVI's single-pass flow completion.
2. **Propagation-based video inpainting transformer (white-box part)** — *bidirectional propagation* of features both forward and backward in time, dramatically reducing the number of transformer layers needed while keeping long-range temporal consistency. This is what makes it **faster and lighter than a naive full-clip transformer** while *better*.
3. **Sparse temporal transformer** — after flow-driven propagation, a sparse transformer blends keyframes (so not every frame needs the full attention transform), cutting compute vs. dense transformers.

### Real quality / speed / VRAM
- **SOTA** on DAVIS, YouTube-VOS (and the newer ProPainter uses YouTube-VOS for video-object removal) — beats STTN and E2FGVI on PSNR/SSIM/VFID and temporal consistency in the paper's tables (see §6 / [ar5iv tables](https://ar5iv.labs.arxiv.org/html/2309.03897)).
- **Throughput:** typically several fps on a single GPU for a modest clip, but **real-time it is not**; a 20–30 s 720p clip takes on the order of a minute or more on a consumer GPU. "Slow-acceptable" fits ProPainter well.
- **VRAM:** the paper's models are trained on 480p/720p clips of 40–80 frames; long/HD clips exceed consumer VRAM. The official README documents a **multi-chip / memory-optimization mode**. In practice, at 1080p with long clips, an **8–12 GB GPU is tight and often needs windowed/split processing**; 16+ GB is comfortable. Tool reports (VSR discussions) specifically flag **ProPainter's high VRAM footprint** (see §6).

### Why it is now the default base for subtitle-removal tools
- `video-subtitle-remover` (VSR, the dominant open-source subtitle-removal project, [YaoFANGUK/video-subtitle-remover](https://github.com/YaoFANGUK/video-subtitle-remover)) offers **STTN, E2FGVI, and ProPainter** engines, and **ProPainter is recommended for the best-quality result** on dynamic content. Many forks ([bzy-ai/E2FGVI](https://github.com/bzy-ai/E2FGVI), SysAdminDoc/VideoSubtitleRemover, etc.) ship ProPainter as the quality path.
- Its combination of (a) best accuracy, (b) arbitrary-resolution support, (c) noticeably faster/lighter than a naive transformer while beating E2FGVI, makes it the practical default for "remove text over moving video" today.

**License / maturity:** Official repo `sczhou/ProPainter` — **includes a LICENSE file**. ProPainter reuses components from other projects (e.g., RAFT flow) whose licenses (MIT/BSD) must be observed; the repo's own model & code are distributed per its LICENSE. **Weights are downloadable** (readme-listed Google Drive), and there are `pip` installs and a **Colab demo**. Community integration is very mature (ComfyUI node, VSR GUI, HuggingFace Spaces demos). Commercial-friendliness: acceptable under its permissive LICENSE, but **verify the exact LICENSE text for the model** before shipping a paid product; RAFT dependency is MIT. Better commercial posture than STTN/E2FGVI's unspecified research licenses.

---

## 4. Lighter alternatives

### LaMa (Resolution-Robust Large Mask Inpainting with Fourier Convolutions, WACV 2022)
- **Source:** [WACV 2022 paper](https://mlanthology.org/wacv/2022/suvorov2022wacv-resolutionrobust/), official repo [advimman/lama](https://github.com/advimman/lama) (Advance/Intel), HF model card [AEmotionStudio/lama-inpainting (Apache-2.0)](https://huggingface.co/AEmotionStudio/lama-inpainting).
- **Per-frame (image) inpainting**. No temporal reasoning at all — each masked frame is filled using spatial context + big-receptive-field Fourier features.
- **Strength:** outstanding on **large masks** and **textured/static backgrounds**; very resolution-robust (arbitrary resolution); **fast**; tiny VRAM (a few hundred MB to ~2 GB); **Apache-2.0** (commercial-friendly).
- **Weakness (key for subtitles):** no temporal consistency — consecutive frames inpainted independently → **flicker** on anything moving or on text that overlaps partially moving backgrounds. Fine for a **static background band** (e.g., lower-third over a stationary wall/chroma — common subtitle placement), inadequate for moving subjects/textured motion behind the text.
- **When sufficient:** subtitles over static/flat/plain backgrounds, screen-recorded or talking-head videos with a fixed lower-third, or when per-frame artifacts are acceptable. This is VSR's "fastest/lightest" engine option.
- **When insufficient:** moving camera, fast cuts, people/objects crossing behind the text, busy motion texture — produces temporal shimmering and ghost edges.

### FFmpeg neighbor-frame interpolation / frame copy
- **Approaches:** (a) `ffmpeg` `inpaint` filter per frame (spatial interpolation); (b) copy the **previous/next clean frame's region** over the masked band over the clip (temporal frame copy — works only if the background under the text is static and the text isn't always present); (c) average/blend neighbor frames in the masked region.
- **When sufficient:** the very easiest cases — a **static, unchanging background** region beneath text, no motion under the mask, camera locked. Then frame-copy/neighbor-blend yields a clean result at **~0 GPU cost** and effectively instant speed.
- **When insufficient:** any motion under the region (camera pans, moving content) → **smearing/ghosting** because copied pixels are stale; text transitions where the text is present in ALL frames (nothing "clean" to copy) → must synthesize, which plain copy cannot do.

### Evidence for the "light path for easy cases, heavy model for hard cases" tiering
- The VSR ecosystem itself implements exactly this tiering: it offers **FFmpeg/LaMa/light engines** for fast/static jobs and **E2FGVI/ProPainter** for quality/dynamic jobs, and its docs/style guidance classify input by whether the background is static. Multiple VSR deep-dives (Tencent Cloud, Aliyun, CSDN — see §6) describe the hardware ceiling ("ProPainter 显存占用大" = ProPainter VRAM heavy) and recommend light engines for easy clips.
- This is a **well-established operational pattern**: run the cheap, fast, deterministic path first; escalate to the heavy model only for clips whose masks/regions are dynamic. Saves GPU-seconds and reduces the risk of model artifacts on trivial content.

---

## 5. Open-source maturity, VRAM, licensing (summary)

| Model | Year | Inference code | Weights | pip-install | Min VRAM (practical) | License / commercial |
|------|------|---------------|---------|-------------|----------------------|----------------------|
| STTN | 2020 | official `researchmm/STTN` | yes (repo) | clone-run / community | ~2–4 GB (clip window) | research/unspecified — verify before commercial |
| E2FGVI | 2022 | official `MCG-NKU/E2FGVI` | yes (repo) | clone-run / community `e2fgvi` | ~3–6 GB; arbitrary-res | research/unspecified — verify before commercial |
| **ProPainter** | 2023 | official `sczhou/ProPainter` | yes (Google Drive) | pip-able + Colab + ComfyUI node | ~8–12+ GB (1080p/long clips need windowing) | LICENSE file provided; reuses MIT RAFT; permissive — verify exact text |
| LaMa | 2022 | official `advimman/lama` | yes (HF) | `pip install` (community + `simple-lama-inpainting`) | < 1 GB (few GB at high res) | **Apache-2.0** — commercial-friendly |
| FFmpeg inpaint / frame-copy | n/a | built into FFmpeg | n/a | n/a | **0 (CPU)** | FFmpeg LGPL/GPL build — free |

**Practical VRAM guidance (local NVIDIA GPU):** ProPainter is the VRAM ceiling. At 720p/480p with ≤40-frame windows it fits 8 GB; **long 1080p clips on 8–12 GB need clip-window/split processing** (multi-chip or memory-optimization in the readme). If you must run 1080p in one pass on a <12 GB card, drop to E2FGVI (arbitrary-res, lighter) or pre-downscale.

---

## 6. Actual effect on "subtitle region" (local, highly dynamic, text-dense) masks

There is **no canonical public benchmark that isolates "subtitle-region" masks** on the four models; evaluations are either:
1. **General video-inpainting benchmarks** (DAVIS, YouTube-VOS, Vimeo-90K, FVI) with object-removal masks — from the papers themselves; the closest proxy for mask/density behavior.
2. **Community/industrial subtitle-removal evaluations** (VSR and its derivatives, Chinese dev forums).

### What the general benchmarks show (primary sources)
- **STTN vs E2FGVI:** E2FGVI beats STTN on DAVIS/YouTube-VOS/Vimeo PSNR & temporal metrics (paper Table, [arXiv:2204.02663](https://ar5iv.labs.arxiv.org/html/2204.02663)) — attributed to flow transport replacing heuristic patch match; the gap is largest on **moving content**, precisely the "highly dynamic" subtitle case.
- **ProPainter vs both:** higher PSNR/SSIM/vFID and lower temporal inconsistency on YouTube-VOS/DAVIS ([ar5iv tables, arXiv:2309.03897](https://ar5iv.labs.arxiv.org/html/2309.03897)); clear on dense, long-range motion and occlusion.

### Subtitle-removal-specific data points (secondary but authoritative-in-practice)
- **`video-subtitle-remover` (VSR)** supports **STTN / E2FGVI / ProPainter** engines [source](https://github.com/YaoFANGUK/video-subtitle-remover). Its maintained recommendation is ProPainter for the best effect on dynamic content; LaMa/light engines for fast static cases. Forks like [SysAdminDoc/VideoSubtitleRemover](https://github.com/SysAdminDoc/VideoSubtitleRemover) document **"ProPainter = best; LaMa = best still-frame; STTN = legacy"**.
- **Text-in-picture / dense tiny-text masks:** subtitles are *localized, text-dense, high-contrast edges*. These stress all models: crisp glyph edges are high-frequency, so **blur/ringing appears with STTN**; flow-based models (E2FGVI, ProPainter) handle the *motion* but still risk slight text-lingering residue when the glyphs are partially visible (anti-aliasing). Community guides recommend **padding the mask** around glyphs and **erosion/dilation tuning** to avoid residual halos.
- **VRAM/flakiness real-world reports:** multiple VSR deep-dives flag **ProPainter's large VRAM footprint** and slow runtime as the main practical barrier ([Tencent Cloud VSR 解析](https://cloud.tencent.com.cn/developer/article/2633062), [Aliyun VSR 解析](https://developer.aliyun.com/article/1714115), [CSDN: 视频字幕擦除与动态修复 (Transitator SOTA analysis)](https://blog.csdn.net/x12363/article/details/158812802)); these recommend light engines for easy clips precisely to dodge ProPainter's cost.

### Bottom line for subtitle masks
- **Dynamic subtitle region (moving bg, many cuts):** ProPainter (best), then E2FGVI (fast/lighter), then STTN (worst of the three).
- **Static subtitle region (fixed lower-third, plain bg):** LaMa or even ffmpeg frame-copy suffice and are far cheaper; ProPainter is overkill.

---

## 7. Comparison table (quality / speed / VRAM / maturity / license)

| Model | Output quality (subtitle/dynamic) | Speed | VRAM | Maturity/ecosystem | License |
|------|----------------------------------|-------|------|--------------------|---------|
| **STTN** (ECCV'20) | Good static; **blur + ghosting on dynamic** (weak moving-bg) | **Slow** (~15× slower than E2FGVI) | Low–med (~2–4 GB) | Mature (VSR engine #1 legacy), research code | unspecified/research — verify |
| **E2FGVI** (CVPR'22) | **Good–Very good**; flow handles motion/gold for moving-bg | Fast (~15× < STTN), arbitrary-res | Med (~3–6 GB) | Mature (VSR engine), research code | unspecified/research — verify |
| **ProPainter** (ICCV'23) | **Best** precision, temporal-consistent, handles fast cuts | Slow (several fps; "slow-acceptable" ✓) | **High** (8–12+ GB; windowing for 1080p/long) | **Mature & default base** (VSR, ComfyUI, Colab, HF demos) | LICENSE provided; MIT RAFT reused — verify exact text |
| **LaMa** (WACV'22) | Good for **static** regions; **flickers on motion** | **Very fast**, arbitrary-res | Very low (<1–2 GB) | Mature (pip/`simple-lama-inpainting`, HF, ComfyUI) | **Apache-2.0** (commercial-friendly) |
| **FFmpeg inpaint / frame-copy** | Best only for **frozen background**; smears on motion | **Instant, CPU** | **0** | Trivial (FFmpeg built-in) | FFmpeg LGPL/GPL |

---

## 8. Final recommendation

**Primary engine (precision path):** **ProPainter** — best precision for local, highly-dynamic, text-dense subtitle masks; it is already the default base of the dominant subtitle-removal tool, has downloadable weights, pip/Colab/ComfyUI integration, and a provided LICENSE (permissive, with MIT-RAFT dependency). Slow and VRAM-hungry, which matches the "slow-acceptable" requirement. For long 1080p clips on an 8–12 GB GPU, enable clip-window/split processing (documented in the readme) or fall back to E2FGVI.

**Fast-path engine (easy cases):** **LaMa** (Apache-2.0, per-frame) for static-background lower-thirds, and **ffmpeg frame-copy / neighbor-blend** (zero GPU) for truly frozen regions.

**Tiering:** Classify each clip (or each region) by motion/background dynamics under the subtitle mask:
- Static background, fixed lower-third → **ffmpeg/LaMa** (cheap, fast).
- Slight motion but mostly static → **LaMa** with heavy mask padding, or **E2FGVI** if flicker matters.
- Moving background, camera pans, cut-heavy, fast-moving subjects → **ProPainter**.

**Commercial note:** Apache-2.0 (LaMa) is fully commercial-safe. For productization of the video-inpainting deep models (STTN/E2FGVI/ProPainter), confirm each repo's exact LICENSE text (and the MIT RAFT dependency) with your legal review before shipping a paid offering; ProPainter's posture is the best of the three, E2FGVI/STTN are research-unspecified.

---

## Source list (primary)
- STTN paper: https://arxiv.org/abs/2007.10247 · repo: https://github.com/researchmm/STTN · Springer: https://link.springer.com/chapter/10.1007/978-3-030-58517-4_31
- E2FGVI paper: https://arxiv.org/abs/2204.02663 · repo: https://github.com/MCG-NKU/E2FGVI · IEEE: https://ieeexplore.ieee.org/abstract/document/9878410 · Nankai press: https://encyber.nankai.edu.cn/2023/1225/c34753a533301/page.htm
- ProPainter paper: https://arxiv.org/abs/2309.03897 · repo: https://github.com/sczhou/ProPainter · ar5iv tables: https://ar5iv.labs.arxiv.org/html/2309.03897
- LaMa paper: https://mlanthology.org/wacv/2022/suvorov2022wacv-resolutionrobust/ · repo: https://github.com/advimman/lama · Apache-2.0 model card: https://huggingface.co/AEmotionStudio/lama-inpainting
- video-subtitle-remover (engines incl. ProPainter): https://github.com/YaoFANGUK/video-subtitle-remover · fork docs: https://github.com/SysAdminDoc/VideoSubtitleRemover
- Community/industrial evaluations: Tencent Cloud VSR: https://cloud.tencent.com.cn/developer/article/2633062 · Aliyun VSR: https://developer.aliyun.com/article/1714115 · CSDN SOTA analysis: https://blog.csdn.net/x12363/article/details/158812802
