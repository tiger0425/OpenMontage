# OpenMontage

**MANDATORY: Read `AGENT_GUIDE.md` before responding to ANY user message.**

Do not act on the user's request until you have read AGENT_GUIDE.md.
It contains routing rules that determine your first action based on what the user asked.
Skipping it WILL cause you to take the wrong action.

There are no instructions in this file. All instructions are in AGENT_GUIDE.md.

## Provider Lockdown

**MANDATORY: Before any generation task, read `.agents/skills/provider-lockdown/SKILL.md`.**

# OpenMontage

**MANDATORY: Read `AGENT_GUIDE.md` before responding to ANY user message.**

Do not act on the user's request until you have read AGENT_GUIDE.md.
It contains routing rules that determine your first action based on what the user asked.
Skipping it WILL cause you to take the wrong action.

There are no instructions in this file. All instructions are in AGENT_GUIDE.md.

## Provider Lockdown

**MANDATORY: Before any generation task, read `.agents/skills/provider-lockdown/SKILL.md`.**

This skill locks which providers to use for image generation, TTS, music, video generation, and video composition. Providers listed there are the ONLY allowed ones — all others are prohibited regardless of availability. Violating the lockdown will produce output the user explicitly rejected.

## Universal Harness Enforcement (For ALL Agents)

**MANDATORY**: Any external intelligent agent (Cursor, Windsurf, OpenClaw, Codex, etc.) is strictly FORBIDDEN from attempting to execute the workflow manually or writing custom ad-hoc scripts to generate assets. 

To create or progress a video project, you MUST use the Universal Harness CLI (`bin/omo.py`). This CLI wraps the state machine and ensures you cannot bypass the pipeline.

**Usage:**
1. Check state: `python bin/omo.py status --project <name> --pipeline <type>`
2. Get strict stage prompt: `python bin/omo.py start-stage --project <name> --pipeline <type>`
3. Submit JSON artifact: `python bin/omo.py submit-artifact --project <name> --stage <stage> --file <path> --pipeline <type>`

You are a worker responding to the Harness. Do not guess the next steps. Do what `start-stage` tells you to do, submit it, and stop if the harness tells you to wait for human approval.

## Orchestration Red Lines (ABSOLUTE RULES)

To prevent agents from hallucinating code or skipping the pipeline, you MUST follow these constraints for every video request:
1. **NO AD-HOC SCRIPTS**: Do NOT write custom Python scripts (e.g. `generate_garment.py`, `test_imagen.py`) in the project directory to call tools. You must act as the pipeline orchestrator: read the YAML manifest, call tools interactively (e.g. via `python -c` or temporary scratch scripts), and write the canonical JSON artifacts.
2. **USE SELECTORS ONLY**: When generating media, you MUST route through `image_selector`, `video_selector`, or `tts_selector`. NEVER hardcode or directly import underlying providers (e.g. `GoogleImagen`, `ElevenLabsTTS`) in your tool calls.
3. **RESPECT CHECKPOINTS**: You MUST stop and wait for user approval at the stages defined by `human_approval_default: true` in the pipeline manifest (e.g. the `idea` stage). Do NOT generate final assets before the creative brief and render_runtime are explicitly approved.
4. **NO SINGLE-SHOT HTML GENERATION**: When building HyperFrames videos, you are strictly FORBIDDEN from writing `index.html` manually in one go. You MUST follow the 6-step pipeline: generate STORYBOARD.md -> await approval -> use `audio.mjs` for timestamps -> design `visual-design.md` -> use individual sub-agents per frame -> assemble via `assemble-index.mjs` and `transitions.mjs`. Bypassing this pipeline is a critical failure.
5. **PRE-FLIGHT CHECKLIST (MANDATORY)**: Before executing ANY stage from the harness, you MUST stop and complete these 4 steps in your mind:
   - **Step 1 (Read)**: Read the pipeline YAML definition and the schema of the artifact you are required to produce.
   - **Step 2 (Understand)**: Understand the holistic context. Do not just look at your current stage; understand what the previous stages produced and what the next stages need.
   - **Step 3 (Cross-Reference Assets)**: Explicitly list out all required asset types (Images, Video, Text Overlays, Audio). Cross-reference the input JSONs (e.g., `frame_blueprint`) against your target schema to ensure no field (like `overlay_notes`) is dropped.
   - **Step 4 (Execute)**: Only AFTER mapping the data completely may you begin writing code or calling tools to generate the JSON artifact.
