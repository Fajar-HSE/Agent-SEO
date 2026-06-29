"""SEO Agent Platform - main entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Any

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import yaml

# Setup paths
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from agents.planner.agent import PlannerAgent
from agents.research.agent import ResearchAgent
from agents.keyword.agent import KeywordAgent
from agents.seo.agent import SEOAgent
from agents.writer.agent import WriterAgent
from agents.reviewer.agent import ReviewerAgent
from agents.publisher.agent import PublisherAgent
from agents.monitor.agent import MonitorAgent
from gateway.router import Router
from memory.session import SessionMemory
from memory.project import ProjectMemory
from gateway.logger import setup_logging

logger = logging.getLogger("seo-agent")

# Agent registry
AGENTS = {
    "planner": PlannerAgent,
    "research": ResearchAgent,
    "keyword": KeywordAgent,
    "seo": SEOAgent,
    "writer": WriterAgent,
    "reviewer": ReviewerAgent,
    "publisher": PublisherAgent,
    "monitor": MonitorAgent,
}


def load_config(path: str) -> dict:
    """Load YAML config file."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_mapping(mapping: dict, session: SessionMemory, step_outputs: dict) -> dict:
    """Resolve ${steps.X} and ${input.X} template variables."""
    resolved = {}
    for key, val in mapping.items():
        if isinstance(val, str) and val.startswith("${"):
            # Parse reference: ${input.keyword} or ${steps.plan.outline}
            ref = val[2:-1]  # remove ${ and }
            parts = ref.split(".")
            if parts[0] == "input":
                resolved[key] = session.get(parts[1], "")
            elif parts[0] == "steps" and len(parts) >= 2:
                step_id = parts[1]
                field = parts[2] if len(parts) > 2 else None
                step_data = step_outputs.get(step_id, {})
                if field:
                    resolved[key] = step_data.get(field, "")
                else:
                    resolved[key] = step_data
            else:
                resolved[key] = val
        else:
            resolved[key] = val
    return resolved


async def run_workflow(
    workflow_path: str,
    input_data: dict[str, Any],
    dry_run: bool = False,
):
    """Execute a workflow from YAML definition."""
    # Load workflow config
    wf_config = load_config(workflow_path)
    wf_name = wf_config.get("name", "unknown")
    workflow_id = uuid.uuid4().hex[:12]

    logger.info(f"Starting workflow: {wf_name} (id={workflow_id})")

    # Init memory
    session = SessionMemory()
    session.set("workflow_id", workflow_id)
    for k, v in input_data.items():
        session.set(k, v)

    # Init router
    providers_config = load_config(os.path.join(ROOT, "config", "providers.yaml"))
    router = Router(providers_config)

    # LLM function for agents
    provider_name = wf_config.get("provider", "huggingface")
    model_name = wf_config.get("model", "")

    async def llm_func(messages, model="", temperature=0.7, max_tokens=4096):
        return await router.complete(
            messages=messages,
            model=model or model_name,
            provider=provider_name,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # Track step outputs for template resolution
    step_outputs: dict[str, Any] = {}
    steps_results: list[dict] = []

    steps = wf_config.get("steps", [])

    for i, step in enumerate(steps):
        step_id = step["id"]
        agent_name = step["agent"]
        description = step.get("description", "")

        logger.info(f"[Step {i+1}/{len(steps)}] {step_id} — {agent_name}: {description}")

        if dry_run:
            logger.info(f"  [DRY RUN] Skipping execution")
            steps_results.append({"step_id": step_id, "agent": agent_name, "status": "dry_run"})
            continue

        # Resolve input mapping
        input_mapping = step.get("input_mapping", {})
        resolved_input = resolve_mapping(input_mapping, session, step_outputs)

        # Instantiate agent
        if agent_name not in AGENTS:
            logger.error(f"  Unknown agent: {agent_name}")
            continue

        agent = AGENTS[agent_name]()

        # Execute agent
        start = time.time()
        try:
            result = await agent.execute(resolved_input, llm_func)
            elapsed = time.time() - start

            step_outputs[step_id] = result
            session.set(step_id, result)
            session.add_history({
                "step_id": step_id,
                "agent": agent_name,
                "status": "completed",
                "confidence": result.get("confidence", 0),
                "elapsed_s": round(elapsed, 2),
            })

            steps_results.append({
                "step_id": step_id,
                "agent": agent_name,
                "status": "completed",
                "confidence": result.get("confidence", 0),
                "elapsed_s": round(elapsed, 2),
                "output_keys": list(result.keys()),
            })

            logger.info(f"  ✓ Completed in {elapsed:.1f}s — confidence: {result.get('confidence', 0):.2f}")

        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"  ✗ Failed in {elapsed:.1f}s: {e}")
            steps_results.append({
                "step_id": step_id,
                "agent": agent_name,
                "status": "failed",
                "error": str(e),
                "elapsed_s": round(elapsed, 2),
            })
            session.add_history({
                "step_id": step_id,
                "agent": agent_name,
                "status": "failed",
                "error": str(e),
            })

    # Final summary
    completed = sum(1 for s in steps_results if s.get("status") == "completed")
    failed = sum(1 for s in steps_results if s.get("status") == "failed")

    summary = {
        "workflow_id": workflow_id,
        "workflow": wf_name,
        "status": "completed" if failed == 0 else "partial" if completed > 0 else "failed",
        "steps_total": len(steps),
        "steps_completed": completed,
        "steps_failed": failed,
        "steps": steps_results,
        "final_output": step_outputs,
    }

    logger.info(f"Workflow finished: {completed}/{len(steps)} completed, {failed} failed")
    return summary


def list_workflows():
    """List available workflows."""
    wf_dir = os.path.join(ROOT, "workflows")
    if not os.path.exists(wf_dir):
        print("No workflows found.")
        return

    for f in sorted(os.listdir(wf_dir)):
        if f.endswith(".yaml") or f.endswith(".yml"):
            path = os.path.join(wf_dir, f)
            config = load_config(path)
            name = config.get("name", f)
            desc = config.get("description", "")
            steps = config.get("steps", [])
            print(f"  {name}")
            print(f"    File: {f}")
            print(f"    Desc: {desc.encode('ascii', 'replace').decode()}")
            print(f"    Steps: {len(steps)}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description="SEO Agent Platform — AI-powered content generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py run seo_article --keyword="AI dalam bisnis"
  python main.py run simple_article --keyword="tips SEO 2024"
  python main.py list
  python main.py run seo_article --keyword="test" --dry-run
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # Run command
    run_parser = sub.add_parser("run", help="Run a workflow")
    run_parser.add_argument("workflow", help="Workflow name (e.g. seo_article)")
    run_parser.add_argument("--keyword", "-k", required=True, help="Target keyword")
    run_parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Debug logging")

    # List command
    sub.add_parser("list", help="List available workflows")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "list":
        print("\nAvailable workflows:\n")
        list_workflows()
        return

    if args.command == "run":
        setup_logging(log_dir=os.path.join(ROOT, "logs"), level="DEBUG" if args.verbose else "INFO")

        workflow_path = os.path.join(ROOT, "workflows", f"{args.workflow}.yaml")
        if not os.path.exists(workflow_path):
            print(f"Workflow not found: {workflow_path}")
            sys.exit(1)

        input_data = {"keyword": args.keyword}

        result = asyncio.run(run_workflow(workflow_path, input_data, dry_run=args.dry_run))

        # Print summary
        print("\n" + "=" * 60)
        print(f"WORKFLOW RESULT: {result['workflow']}")
        print(f"Status: {result['status']}")
        print(f"Steps: {result['steps_completed']}/{result['steps_total']} completed")
        print("=" * 60)

        # Print final output keys
        final = result.get("final_output", {})
        if final:
            print("\nFinal outputs:")
            for step_id, data in final.items():
                if isinstance(data, dict):
                    print(f"  [{step_id}]")
                    for k, v in data.items():
                        val_str = str(v)[:100]
                        print(f"    {k}: {val_str}")


if __name__ == "__main__":
    main()
