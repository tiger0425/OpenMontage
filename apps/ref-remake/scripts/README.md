# ref-remake 可复用脚本模板

配置驱动模板，源自 `projects/outsmart-cn/scripts/`（已验证 3 条成片的实际流程）泛化而来。
**所有脚本的 workdir 必须是 OpenMontage 根目录**（相对路径约定，嵌套运行会写错路径）。

## 脚本一览

| 脚本 | 阶段 | 作用 |
|---|---|---|
| `gen_frames.py` | assets | MiniMax image-01 生图：V2 风格块（styles/ref-remake.yaml verbatim）+ 参考图锚点（background_library/ref-remake/anchor/ahhuang_anchor.png），9:16，每帧固定 seed |
| `gen_tts.py` | assets | IndexTTS2 克隆音色分段配音（voice_ref_futian3.wav，seed 20260825），产出 seg_*.wav |
| `build_timeline.py` | compose 前 | 按 ffprobe 实测段长 + 字数比例分配画面时间轴 → timeline.json |
| `build_index.py` | compose | 从 timeline.json 生成 HyperFrames index.html（V2 点缀式，无字图 + HTML 叠字，push 转场，@font-face 中文声明） |
| `redline_scan.py` | script（闸门） | 改写稿 vs 原转录稿相似度扫描：单句 ≥0.75 红 / 整篇 ≥0.45 黄，产出 redline_scan.json 作闸门附件 |

## 用法

```bash
# workdir = OpenMontage 根目录
python apps/ref-remake/scripts/gen_frames.py    --config projects/<slug>/artifacts/frames_config.json
python apps/ref-remake/scripts/gen_tts.py       --config projects/<slug>/artifacts/tts_config.json
python apps/ref-remake/scripts/build_timeline.py --config projects/<slug>/artifacts/timeline_config.json
python apps/ref-remake/scripts/build_index.py   --config projects/<slug>/artifacts/index_config.json
python apps/ref-remake/scripts/redline_scan.py  --rewrite <script.md> --original <transcript.txt> --out <redline_scan.json>
```

每个脚本头部 docstring 附有 config JSON 的完整字段说明。

## 关键坑（交接文档固化）

1. **workdir 必须是根目录**——`build_index.py` 的 index.html 路径相对根目录；嵌套运行会渲染出 10 秒 init 模板。
2. `index.sample.html` 残留会触发 lint `multiple_root_compositions`，用后必删。
3. 生图必须是**无字底稿**——所有文字（标题/数字/字幕）由 HTML 层叠加。
4. MiniMax 422 sensitive 帧直接跳过，不阻塞整批。
5. 中文需要 `@font-face { src: local(...) }`（Noto Sans SC / PingFang SC / Microsoft YaHei）。
6. 转场：场景 div 加 `data-layout-allow-overflow`；pushWithRank 只用于带 rank 徽章场景，结尾用普通 push。
