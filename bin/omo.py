#!/usr/bin/env python3
"""
OpenMontage Universal Harness CLI (omo)

This CLI is the strict orchestrator harness for OpenMontage.
External agents (Codex, OpenClaw, Cursor, etc.) MUST use this CLI to interact
with projects, preventing pipeline bypasses and ensuring correct state transitions.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib import checkpoint
from lib import pipeline_loader

PIPELINES_DIR = PROJECT_ROOT / "pipeline_defs"
PROJECTS_DIR = PROJECT_ROOT / "projects"

def cmd_status(args):
    """Check the status of a project."""
    project_id = args.project
    pipeline_type = args.pipeline

    print(f"Project: {project_id}")
    print(f"Pipeline: {pipeline_type or 'Not specified (auto-detect)'}")
    
    completed = checkpoint.get_completed_stages(PROJECTS_DIR, project_id, pipeline_type)
    print(f"Completed Stages: {', '.join(completed) if completed else 'None'}")
    
    next_stage = checkpoint.get_next_stage(PROJECTS_DIR, project_id, pipeline_type)
    if next_stage:
        print(f"\n[NEXT STAGE]: {next_stage}")
        print(f"To start this stage, run: python bin/omo.py start-stage --project {project_id} --pipeline <type>")
    else:
        print("\n[PIPELINE COMPLETE]")


def cmd_start_stage(args):
    """Print the strict prompt for the next stage."""
    project_id = args.project
    pipeline_type = args.pipeline
    
    next_stage = checkpoint.get_next_stage(PROJECTS_DIR, project_id, pipeline_type)
    if not next_stage:
        print("Pipeline is already complete.")
        return

    try:
        manifest = pipeline_loader.load_pipeline(pipeline_type)
    except FileNotFoundError:
        print(f"Error: Pipeline '{pipeline_type}' not found.")
        sys.exit(1)
    
    # Find stage configuration
    stage_config = None
    for s in manifest.get("stages", []):
        if s["name"] == next_stage:
            stage_config = s
            break
            
    if not stage_config:
        print(f"Error: Stage '{next_stage}' not found in pipeline manifest '{pipeline_type}'")
        sys.exit(1)
        
    skill_path = stage_config.get("skill")
    human_approval = stage_config.get("human_approval_default", False)
    
    canonical_artifact = checkpoint.CANONICAL_STAGE_ARTIFACTS.get(next_stage)
    
    print("="*60)
    print(f"HARNESS DISPATCH: Stage '{next_stage}'")
    print("="*60)
    print("AGENT INSTRUCTIONS:")
    print("1. You must ONLY complete the task for this specific stage.")
    print("2. You must NOT generate assets or write code for future stages.")
    if skill_path:
        print(f"3. Read the director skill at: {skill_path}")
    print(f"4. You must output a JSON artifact named '{canonical_artifact}'")
    print(f"5. Once generated, submit it using: python bin/omo.py submit-artifact --project {project_id} --stage {next_stage} --file <path_to_json> --pipeline {pipeline_type}")
    if human_approval:
        print("6. IMPORTANT: This stage requires human approval. The harness will block after submission.")
    print("="*60)


def cmd_submit_artifact(args):
    """Submit an artifact, validate it, and write the checkpoint."""
    project_id = args.project
    stage = args.stage
    file_path = Path(args.file)
    pipeline_type = args.pipeline
    
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
        
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            artifact_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: File is not valid JSON. {e}")
            sys.exit(1)
            
    canonical_artifact = checkpoint.CANONICAL_STAGE_ARTIFACTS.get(stage)
    if not canonical_artifact:
        print(f"Error: Unknown canonical artifact for stage '{stage}'")
        sys.exit(1)
        
    artifacts = {canonical_artifact: artifact_data}
    
    # Validation logic inside checkpoint.py will handle schema validation
    try:
        manifest = pipeline_loader.load_pipeline(pipeline_type)
        # Find if human approval is needed
        human_approval_required = False
        for s in manifest.get("stages", []):
            if s["name"] == stage:
                human_approval_required = s.get("human_approval_default", False)
                break
                
        status = "awaiting_human" if human_approval_required else "completed"
        
        path = checkpoint.write_checkpoint(
            pipeline_dir=PROJECTS_DIR,
            project_id=project_id,
            stage=stage,
            status=status,
            artifacts=artifacts,
            pipeline_type=pipeline_type,
            human_approval_required=human_approval_required,
            human_approved=False
        )
        print(f"SUCCESS: Checkpoint written to {path}")
        
        if human_approval_required:
            print(f"\n[HARNESS HALT]: Stage '{stage}' requires human approval.")
            print("Agent MUST STOP here and present the output to the user for approval.")
        else:
            print("\n[HARNESS OK]: Agent may proceed to the next stage using 'start-stage'.")
            
    except Exception as e:
        print(f"VALIDATION ERROR: Artifact rejected by Harness.")
        print(f"Reason: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="OpenMontage Universal Harness CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Status
    status_p = subparsers.add_parser("status", help="Check project status")
    status_p.add_argument("--project", required=True, help="Project ID/Name")
    status_p.add_argument("--pipeline", required=False, help="Pipeline Type (e.g. animated-explainer)")
    
    # Start Stage
    start_p = subparsers.add_parser("start-stage", help="Start the next stage and get strict instructions")
    start_p.add_argument("--project", required=True, help="Project ID/Name")
    start_p.add_argument("--pipeline", required=True, help="Pipeline Type")
    
    # Submit Artifact
    submit_p = subparsers.add_parser("submit-artifact", help="Submit artifact to complete a stage")
    submit_p.add_argument("--project", required=True, help="Project ID/Name")
    submit_p.add_argument("--stage", required=True, help="Stage name")
    submit_p.add_argument("--pipeline", required=True, help="Pipeline Type")
    submit_p.add_argument("--file", required=True, help="Path to JSON artifact file")
    
    args = parser.parse_args()
    
    if args.command == "status":
        cmd_status(args)
    elif args.command == "start-stage":
        cmd_start_stage(args)
    elif args.command == "submit-artifact":
        cmd_submit_artifact(args)

if __name__ == "__main__":
    main()
