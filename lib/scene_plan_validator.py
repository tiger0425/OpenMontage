"""Scene-plan doctrine validator.

Enforces rules 2 and 3 from the motion doctrine at the point where a
scene plan enters the pipeline:

  Rule 2 — objects, not icons:
    * every beat must anchor its hero layer to a real object or photo
    * `real_data` / `real_content` elements must trace to a `data_source`
    * icon / flat-panel language is rejected

  Rule 3 — learn composition from pros:
    * three depth layers per beat
    * one light source per scene
    * one idea per frame (core_idea + visual_metaphor)
    * camera moves carry a `shot_intent`

The validator is additive: legacy scene plans without `beats` are not
blocked (they get warnings), so existing projects keep working while new
plans are held to the doctrine.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from lib.slideshow_risk import score_slideshow_risk
from lib.variation_checker import check_scene_variation

# Words that signal an icon / flat panel standing in for a real object.
_ICON_RE = re.compile(
    r"\b(flat|vector|generic|simple|minimal)\s+(icon|panel|badge|card)\b"
    r"|\bicon\b|\bbadge\b"
    r"|图标|扁平化图标|通用面板|数字面板|扁平插画",
    re.IGNORECASE,
)

_DEPTH_LAYERS = {"bg", "hero", "element", "decor"}


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _scene_id(scene: dict[str, Any], idx: int) -> str:
    return str(scene.get("id") or f"scene[{idx}]")


def _beat_id(beat: dict[str, Any], scene_id: str, idx: int) -> str:
    return str(beat.get("id") or f"{scene_id}.beat[{idx}]")


def _text_of(beat: dict[str, Any]) -> str:
    parts = [
        beat.get("visual_metaphor") or "",
        beat.get("visual_idea") or "",
        beat.get("core_idea") or "",
        beat.get("image_prompt") or "",
        beat.get("sync_sentence") or "",
    ]
    return " ".join(parts)


def _check_beat(
    beat: dict[str, Any],
    scene_id: str,
    idx: int,
    blockers: list[str],
    warnings: list[str],
    suggestions: list[str],
) -> None:
    bid = _beat_id(beat, scene_id, idx)
    elements = beat.get("elements") or []

    # --- Rule 2: hero must be a real object, not a creative-only icon ---
    hero = [e for e in elements if e.get("layer") == "hero"]
    if not hero:
        blockers.append(
            f"{bid}: no hero layer. Rule 2 requires the beat's main idea to sit "
            f"on a real object (paper card, ledger, photo on a desk)."
        )
        suggestions.append(
            f"{bid}: add an element with layer='hero' and data_class='real_data' "
            f"or 'real_content'."
        )
    elif all(
        (e.get("data_class") or "creative") in ("creative", "css")
        for e in hero
    ):
        blockers.append(
            f"{bid}: hero layer is creative-only. Rule 2 requires a real object "
            f"or a real photo, not a generated icon."
        )
        suggestions.append(
            f"{bid}: set the hero element's data_class to 'real_data' or "
            f"'real_content' and add a data_source."
        )

    # --- Rule 2: real_data / real_content must trace to a source ---
    for element in elements:
        data_class = element.get("data_class")
        if data_class in ("real_data", "real_content") and not element.get("data_source"):
            blockers.append(
                f"{bid}: element {element.get('description', '<unnamed>')!r} is "
                f"{data_class} but has no data_source. Rule 2 requires traceability."
            )

    # --- Rule 3: one idea per frame ---
    if not str(beat.get("core_idea") or "").strip():
        warnings.append(f"{bid}: missing core_idea (rule 3: one idea per frame).")
    if not str(beat.get("visual_metaphor") or "").strip():
        warnings.append(
            f"{bid}: missing visual_metaphor (rule 3: replace the literal subject "
            f"with a concrete visual)."
        )
    if not str(beat.get("image_prompt") or "").strip():
        warnings.append(f"{bid}: missing image_prompt; generation will be vague.")

    # --- Rule 3: three depth layers ---
    layers = {e.get("layer") for e in elements if e.get("layer") in _DEPTH_LAYERS}
    if len(layers) < 2:
        blockers.append(
            f"{bid}: {len(layers)} depth layer(s); rule 3 requires at least "
            f"background + hero (three is the target)."
        )
    elif len(layers) < 3:
        warnings.append(
            f"{bid}: {len(layers)} depth layers; rule 3 targets three "
            f"(background, hero, element/decor)."
        )

    # --- Rule 2: reject icon / flat-panel language ---
    text = _text_of(beat)
    match = _ICON_RE.search(text)
    if match:
        blockers.append(
            f"{bid}: icon/flat-panel language {match.group(0)!r}. Rule 2 says "
            f"objects, not icons."
        )
        suggestions.append(
            f"{bid}: replace the icon/panel with a real object (paper card, "
            f"ledger, compass, photo on a desk)."
        )


def _check_legacy_scene(
    scene: dict[str, Any],
    scene_id: str,
    warnings: list[str],
) -> None:
    text = " ".join(
        str(scene.get(key) or "")
        for key in ("description", "framing", "overlay_notes", "movement")
    )
    match = _ICON_RE.search(text)
    if match:
        # Legacy plans are warned, not blocked, to keep old projects moving.
        warnings.append(
            f"{scene_id}: icon/flat-panel language {match.group(0)!r} "
            f"(rule 2). Replace it with a real object."
        )


def _check_composition(
    scenes: list[dict[str, Any]],
    edit_decisions: Optional[dict[str, Any]],
    renderer_family: Optional[str],
    blockers: list[str],
    warnings: list[str],
    suggestions: list[str],
) -> dict[str, Any]:
    variation = check_scene_variation(scenes)
    slideshow = score_slideshow_risk(
        scenes,
        edit_decisions=edit_decisions,
        renderer_family=renderer_family,
    )

    if variation.get("verdict") == "fail":
        blockers.extend(f"variation: {v}" for v in variation.get("violations", []))
    elif variation.get("verdict") == "revise":
        warnings.extend(f"variation: {v}" for v in variation.get("violations", []))
    suggestions.extend(variation.get("suggestions", []))

    if slideshow.get("verdict") == "fail":
        blockers.append(
            f"slideshow risk: {slideshow.get('average')} "
            f"({slideshow.get('verdict')}) — the plan reads like animated slides."
        )
        for name, dim in (slideshow.get("dimensions") or {}).items():
            if dim.get("score", 0) >= 3.0:
                blockers.append(f"slideshow/{name}: {dim.get('reason')}")
    elif slideshow.get("verdict") == "revise":
        warnings.append(
            f"slideshow risk: {slideshow.get('average')} "
            f"({slideshow.get('verdict')}) — tighten repetition/motion."
        )

    # Rule 3: one light source per scene. Legacy plans often omit it; warn.
    if len(scenes) >= 4:
        lit = sum(
            1 for s in scenes if (s.get("shot_language") or {}).get("lighting_key")
        )
        if lit < len(scenes) * 0.3:
            warnings.append(
                f"only {lit}/{len(scenes)} scenes define lighting_key; rule 3 asks "
                f"for one motivated light source per scene."
            )

    # Rule 3: camera moves must carry intent (the slideshow scorer also
    # checks this, but keep the message explicit here).
    purposeless = [
        s.get("id") or f"scene[{i}]"
        for i, s in enumerate(scenes)
        if (s.get("shot_language") or {}).get("camera_movement") not in (None, "static")
        and not s.get("shot_intent")
    ]
    if purposeless:
        warnings.append(
            "camera movement without shot_intent in: " + ", ".join(map(str, purposeless))
        )

    return {"variation": variation, "slideshow_risk": slideshow}


def validate_scene_plan(
    plan: dict[str, Any],
    *,
    edit_decisions: Optional[dict[str, Any]] = None,
    renderer_family: Optional[str] = None,
    fail_on_warnings: bool = False,
) -> dict[str, Any]:
    """Validate a scene plan against rules 2 and 3.

    Returns ``{ok, blockers, warnings, suggestions, metrics}``. ``ok`` is
    False when there are blockers (or warnings and ``fail_on_warnings``).
    """
    blockers: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []

    scenes = plan.get("scenes") or []
    if not scenes:
        return {
            "ok": False,
            "blockers": ["scene_plan has no scenes"],
            "warnings": [],
            "suggestions": [],
            "metrics": {"scenes": 0, "beats": 0},
        }

    beat_count = 0
    beats_with_hero = 0
    real_elements = 0
    legacy_scenes = 0

    for s_idx, scene in enumerate(scenes):
        sid = _scene_id(scene, s_idx)
        beats = scene.get("beats") or []
        if not beats:
            legacy_scenes += 1
            _check_legacy_scene(scene, sid, warnings)
            continue

        for b_idx, beat in enumerate(beats):
            beat_count += 1
            elements = beat.get("elements") or []
            if any(e.get("layer") == "hero" for e in elements):
                beats_with_hero += 1
            real_elements += sum(
                1 for e in elements if e.get("data_class") in ("real_data", "real_content")
            )
            _check_beat(beat, sid, b_idx, blockers, warnings, suggestions)

    if legacy_scenes:
        warnings.insert(
            0,
            f"{legacy_scenes}/{len(scenes)} scenes have no beats; rule 2/3 "
            f"beat-level checks skipped (legacy format).",
        )

    metrics = _check_composition(
        scenes, edit_decisions, renderer_family, blockers, warnings, suggestions
    )
    metrics.update(
        {
            "scenes": len(scenes),
            "beats": beat_count,
            "beats_with_hero": beats_with_hero,
            "real_elements": real_elements,
        }
    )

    ok = not blockers and not (fail_on_warnings and warnings)
    return {
        "ok": ok,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "suggestions": _dedupe(suggestions),
        "metrics": metrics,
    }


def validate_asset_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Enforce rule 2 traceability on an asset manifest."""
    blockers: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []

    assets = manifest.get("assets") or []
    for idx, asset in enumerate(assets):
        aid = str(asset.get("id") or f"asset[{idx}]")
        data_class = asset.get("data_class")
        traceable = asset.get("data_source") or asset.get("library_ref")
        if data_class in ("real_data", "real_content") and not traceable:
            blockers.append(
                f"{aid}: data_class={data_class!r} but no data_source/library_ref. "
                f"Rule 2 requires a traceable source."
            )
            suggestions.append(
                f"{aid}: add data_source (URL, archive id, or local path) "
                f"or library_ref."
            )
        if data_class == "real_content" and not asset.get("library_ref") and traceable:
            warnings.append(
                f"{aid}: real_content has a data_source but is not archived in "
                f"the shared library — consider library_ref for reuse."
            )

    return {
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "suggestions": suggestions,
        "metrics": {"assets": len(assets)},
    }


def format_report(report: dict[str, Any], title: str = "scene_plan") -> str:
    """Render a validator report as plain text for the CLI."""
    lines = [
        f"[{title}] {'PASS' if report.get('ok') else 'BLOCKED'}",
    ]
    blockers = report.get("blockers") or []
    warnings = report.get("warnings") or []
    suggestions = report.get("suggestions") or []
    if blockers:
        lines.append(f"  Blockers ({len(blockers)}):")
        lines.extend(f"    - {b}" for b in blockers)
    if warnings:
        lines.append(f"  Warnings ({len(warnings)}):")
        lines.extend(f"    - {w}" for w in warnings[:12])
        if len(warnings) > 12:
            lines.append(f"    … {len(warnings) - 12} more")
    if suggestions:
        lines.append(f"  Suggestions ({len(suggestions)}):")
        lines.extend(f"    - {s}" for s in suggestions[:8])
    return "\n".join(lines)


__all__ = [
    "validate_scene_plan",
    "validate_asset_manifest",
    "format_report",
]
