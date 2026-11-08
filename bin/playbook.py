#!/usr/bin/env python3
"""Style playbook CLI.

Inspect and validate the visual identity presets under styles/*.yaml.

Examples:
    python bin/playbook.py list
    python bin/playbook.py show vox-paper
    python bin/playbook.py validate vox-paper
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from styles.playbook_loader import (
    list_playbooks,
    load_playbook,
    validate_playbook,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect OpenMontage style playbooks.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List playbooks and their two fonts.")

    show = sub.add_parser("show", help="Print a playbook as YAML.")
    show.add_argument("name")

    validate = sub.add_parser("validate", help="Validate a playbook against the schema.")
    validate.add_argument("name")

    args = parser.parse_args()

    if args.command == "list":
        names = list_playbooks()
        if not names:
            print("No playbooks found under styles/.")
            return
        for name in names:
            try:
                pb = load_playbook(name)
                typo = pb.get("typography", {})
                heading = (typo.get("headings") or {}).get("font", "?")
                body = (typo.get("body") or {}).get("font", "?")
                print(f"{name:20s} {heading} / {body}")
            except Exception as exc:  # noqa: BLE001 - show the broken playbook
                print(f"{name:20s} INVALID: {exc}")
        return

    if args.command == "show":
        print(yaml.dump(load_playbook(args.name), allow_unicode=True, sort_keys=False))
        return

    if args.command == "validate":
        pb = load_playbook(args.name)
        validate_playbook(pb)
        print(f"{args.name}: OK")
        print(json.dumps({"name": pb["identity"]["name"], "fonts": {
            "headings": (pb["typography"].get("headings") or {}).get("font"),
            "body": (pb["typography"].get("body") or {}).get("font"),
        }}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
