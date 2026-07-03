# Provenance — HyperFrames Layer 3 Skills

These skills are **vendored** from the upstream HyperFrames monorepo. Do not
edit them expecting the changes to survive a re-sync — changes need to go
upstream, or be recorded in the local-edit log below.

## Source

- Repo: https://github.com/heygen-com/hyperframes
- Vendored commit: `1bab79ef4c9d114af0d1a1ba3b3aff719236ee3d`
- Vendored date: `2026-06-18`

## Mirrored directories

| OpenMontage path                               | Upstream path                      |
| ---------------------------------------------- | ---------------------------------- |
| `.agents/skills/hyperframes/`                  | `skills/hyperframes/`              |
| `.agents/skills/hyperframes-cli/`              | `skills/hyperframes-cli/`          |
| `.agents/skills/hyperframes-registry/`         | `skills/hyperframes-registry/`     |
| `.agents/skills/website-to-hyperframes/`       | `skills/website-to-video/` (更名)  |
| `.agents/skills/hyperframes-core/`             | `skills/hyperframes-core/`         |
| `.agents/skills/hyperframes-animation/`        | `skills/hyperframes-animation/`    |
| `.agents/skills/hyperframes-creative/`         | `skills/hyperframes-creative/`     |
| `.agents/skills/hyperframes-media/`            | `skills/hyperframes-media/`        |

> `website-to-video` 在上游已被重命名，OpenMontage 保留旧目录名以保持引用兼容。
> `hyperframes-animation/assets/` 下的二进制文件（MP4 视频、图片素材）已排除，
> 仅保留文本知识文件。

## 未重新引入的技能

上游还有以下**工作流技能**未纳入（它们属于 HyperFrames 特定工作流，可能
与 OpenMontage 管道系统冲突）：

- `skills/embedded-captions/` — 现有视频字幕
- `skills/faceless-explainer/` — 无面讲解视频
- `skills/general-video/` — 通用视频创作
- `skills/graphic-overlays/` — 图形叠加
- `skills/motion-graphics/` — 动态图形
- `skills/pr-to-video/` — PR 转视频
- `skills/product-launch-video/` — 产品发布视频
- `skills/remotion-to-hyperframes/` — Remotion 迁移

若未来需要其中某个工作流技能，可按下方流程单独引入。

`gsap` 上游技能也未重新引入 — OpenMontage 已自带 GSAP 技能族
(`.agents/skills/gsap*/`)。

## Local edits

Any divergence from upstream is noted at the top of the edited file as an
HTML comment starting with `OpenMontage-local`. Current edits:

- *(无 — v0.6.112 版本已原生支持 `validate` 命令，先前本地添加的内容不再需要)*

## Re-sync procedure

```bash
# From the hyperframes clone
git clone --depth 1 https://github.com/heygen-com/hyperframes.git /tmp/hf-upstream

# From OpenMontage
cd /path/to/OpenMontage
rm -rf .agents/skills/hyperframes .agents/skills/hyperframes-cli \
       .agents/skills/hyperframes-registry .agents/skills/website-to-hyperframes \
       .agents/skills/hyperframes-core .agents/skills/hyperframes-animation \
       .agents/skills/hyperframes-creative .agents/skills/hyperframes-media
cp -r /tmp/hf-upstream/skills/hyperframes          .agents/skills/
cp -r /tmp/hf-upstream/skills/hyperframes-cli      .agents/skills/
cp -r /tmp/hf-upstream/skills/hyperframes-registry .agents/skills/
cp -r /tmp/hf-upstream/skills/website-to-video     .agents/skills/website-to-hyperframes/
cp -r /tmp/hf-upstream/skills/hyperframes-core     .agents/skills/
cp -r /tmp/hf-upstream/skills/hyperframes-animation .agents/skills/
cp -r /tmp/hf-upstream/skills/hyperframes-creative .agents/skills/
cp -r /tmp/hf-upstream/skills/hyperframes-media    .agents/skills/
# Remove binary assets from hyperframes-animation
find .agents/skills/hyperframes-animation -type f \( -name "*.mp4" -o -name "*.png" -o -name "*.jpg" -o -name "*.webp" -o -name "*.avif" \) -delete
# Then re-apply any local edits listed above and bump the vendored commit SHA.
```

## Why we vendor instead of referencing the upstream clone directly

1. OpenMontage contributors may not have the HyperFrames monorepo on disk.
2. Skills must be readable from the OpenMontage tree for agent discovery.
3. We want deterministic knowledge — upstream moves; we control when we pick
   up changes.
