# -*- coding: utf-8 -*-
"""ref-remake 落地校验：manifest 加载 + director skill 齐全性 + playbook schema。"""
import os
import sys
import json

sys.path.insert(0, os.getcwd())  # allow running from apps/ref-remake/scripts/
import yaml
from jsonschema import Draft202012Validator

from lib.pipeline_loader import load_pipeline

errors = []

# 1) manifest loads (schema + loader)
try:
    m = load_pipeline("ref-remake")
    print("manifest loader OK")
except Exception as e:
    errors.append(f"manifest load failed: {e}")

# 2) director skills present
if not errors:
    for st in m["stages"]:
        p = "skills/" + st["skill"] + ".md"
        if not os.path.exists(p):
            errors.append(f"missing stage skill: {p}")
    print(f"stage skills checked: {len(m['stages'])}")

# 3) playbook validates against schema
try:
    schema = json.load(open("schemas/styles/playbook.schema.json", encoding="utf-8"))
    playbook = yaml.safe_load(open("styles/ref-remake.yaml", encoding="utf-8"))
    Draft202012Validator(schema).validate(playbook)
    print("playbook schema OK")
except Exception as e:
    errors.append(f"playbook validation failed: {e}")

# 4) artifact schemas valid + douyin branches present
for name in ("publish_copy", "cover_manifest", "note_manifest"):
    try:
        s = json.load(open(f"schemas/artifacts/{name}.schema.json", encoding="utf-8"))
        Draft202012Validator.check_schema(s)
        print(f"artifact schema {name} OK")
    except Exception as e:
        errors.append(f"artifact schema {name} failed: {e}")

# 5) template scripts exist
for script in ("gen_frames.py", "gen_tts.py", "build_timeline.py", "build_index.py", "redline_scan.py"):
    p = os.path.join("apps", "ref-remake", "scripts", script)
    if not os.path.exists(p):
        errors.append(f"missing template script: {p}")
print("template scripts checked: 5")

if errors:
    print("\nERRORS:")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("\nALL CHECKS PASSED")
