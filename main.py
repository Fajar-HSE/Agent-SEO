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

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, use system env vars

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
from agents.approval.agent import ApprovalAgent
from agents.rewriter.agent import RewriterAgent
from agents.fetcher.agent import FetcherAgent
from agents.trends.agent import TrendsAgent
from agents.topic_selector.agent import TopicSelectorAgent
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
    "approval": ApprovalAgent,
    "rewriter": RewriterAgent,
    "fetcher": FetcherAgent,
    "trends": TrendsAgent,
    "topic_selector": TopicSelectorAgent,
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
    step_callback=None,
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

    # Ensure language is always set to Indonesian by default
    if not session.get("language"):
        session.set("language", "id")

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
        
        if step_callback:
            try:
                await step_callback(step_id, agent_name, "running", i + 1, len(steps), description)
            except Exception as cb_err:
                logger.error(f"Callback error: {cb_err}")

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
            
            if step_callback:
                try:
                    await step_callback(step_id, agent_name, "completed", i + 1, len(steps), result)
                except Exception as cb_err:
                    logger.error(f"Callback error: {cb_err}")

            # If approval step rejected — stop the workflow
            if agent_name == "approval" and not result.get("approved", True):
                logger.warning(f"  ✗ Workflow stopped: approval rejected — {result.get('reason', '')}")
                break

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
            
            if step_callback:
                try:
                    await step_callback(step_id, agent_name, "failed", i + 1, len(steps), str(e))
                except Exception as cb_err:
                    logger.error(f"Callback error: {cb_err}")


    # Final summary
    completed = sum(1 for s in steps_results if s.get("status") == "completed")
    failed = sum(1 for s in steps_results if s.get("status") == "failed")

    # Get token/cost usage from router
    usage = router.get_usage_summary()

    summary = {
        "workflow_id": workflow_id,
        "workflow": wf_name,
        "status": "completed" if failed == 0 else "partial" if completed > 0 else "failed",
        "steps_total": len(steps),
        "steps_completed": completed,
        "steps_failed": failed,
        "total_tokens": usage["total_tokens"],
        "total_cost_usd": usage["total_cost_usd"],
        "steps": steps_results,
        "final_output": step_outputs,
    }

    logger.info(
        f"Workflow finished: {completed}/{len(steps)} completed, {failed} failed | "
        f"tokens={usage['total_tokens']}, cost=${usage['total_cost_usd']:.6f}"
    )
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
    run_parser.add_argument("workflow", help="Workflow name (e.g. seo_article, rewrite_article)")
    run_parser.add_argument("--keyword", "-k", required=True,
                            help="Target keyword OR source URL (for rewrite_article)")
    run_parser.add_argument("--target-keyword", default="",
                            help="[rewrite] Override detected keyword")
    run_parser.add_argument("--extra-context", default="",
                            help="[rewrite] Extra data: brand voice, real cases, insights")
    run_parser.add_argument("--language", default="id", choices=["id", "en"],
                            help="Output language: id=Indonesian (default), en=English")
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

        input_data = {
            "keyword": args.keyword,
            "target_keyword": getattr(args, "target_keyword", ""),
            "extra_context": getattr(args, "extra_context", ""),
            "language": getattr(args, "language", "id"),
        }

        result = asyncio.run(run_workflow(workflow_path, input_data, dry_run=args.dry_run))

        # ── Summary header ──────────────────────────────────────────
        print("\n" + "=" * 60)
        print(f"WORKFLOW RESULT : {result['workflow']}")
        print(f"Status          : {result['status'].upper()}")
        print(f"Steps           : {result['steps_completed']}/{result['steps_total']} completed")
        print(f"Tokens used     : {result.get('total_tokens', 0)}")
        print(f"Cost            : ${result.get('total_cost_usd', 0):.6f}")
        print("=" * 60)

        # ── Per-step confidence ──────────────────────────────────────
        print("\nStep results:")
        for step in result.get("steps", []):
            status_icon = "✓" if step.get("status") == "completed" else "✗"
            conf = step.get("confidence", 0)
            elapsed = step.get("elapsed_s", 0)
            print(f"  {status_icon} [{step['step_id']:12s}] {step['agent']:12s}  "
                  f"confidence={conf:.2f}  {elapsed:.1f}s")
            if step.get("error"):
                print(f"    ERROR: {step['error']}")

        # ── Extract article content ──────────────────────────────────
        final = result.get("final_output", {})

        # Find the best content source — rewrite > seo > write
        article_title = ""
        article_content = ""
        article_excerpt = ""
        meta_desc = ""
        quality_score = 0
        approved = False
        is_rewrite = "rewrite" in final

        # Rewrite workflow output
        rewrite_data = final.get("rewrite", {})
        if isinstance(rewrite_data, dict) and rewrite_data.get("content"):
            article_title = rewrite_data.get("title", "")
            article_content = rewrite_data.get("content", "")
            article_excerpt = rewrite_data.get("excerpt", "")
            meta_desc = rewrite_data.get("meta_description", "")

        # Standard SEO workflow output
        for step_key in ("seo", "write", "writer"):
            data = final.get(step_key, {})
            if isinstance(data, dict):
                article_title = article_title or data.get("meta_title") or data.get("title", "")
                article_content = article_content or data.get("optimized_content") or data.get("content", "")
                article_excerpt = article_excerpt or data.get("excerpt", "")
                meta_desc = meta_desc or data.get("meta_description", "")

        review_data = final.get("review", {})
        if isinstance(review_data, dict):
            quality_score = review_data.get("quality_score", 0)
            approved = review_data.get("approved", False)

        # ── Print rewrite diagnosis if available ──────────────────────
        if is_rewrite and isinstance(rewrite_data, dict):
            diag = rewrite_data.get("diagnosis", {})
            src_diag = diag.get("source_diagnosis", {})
            aeo_before = rewrite_data.get("aeo_readiness_score_before", 0)
            if src_diag or aeo_before:
                print("\n" + "─" * 60)
                print("DIAGNOSIS ARTIKEL SUMBER")
                print("─" * 60)
                if aeo_before:
                    print(f"  AEO Readiness Score (sebelum): {aeo_before}/100")
                weaknesses = src_diag.get("top_weaknesses", [])
                if weaknesses:
                    print("  Kelemahan yang diperbaiki:")
                    for i, w in enumerate(weaknesses[:5], 1):
                        print(f"    {i}. {w}")
                rw_diag = diag.get("rewrite_diagnosis", {})
                angle = rw_diag.get("reframe_angle", "")
                if angle:
                    print(f"  Angle baru: {angle}")
                print("─" * 60)

        # ── Print article to terminal ────────────────────────────────
        if article_content:
            print("\n" + "=" * 60)
            print("ARTIKEL YANG DIHASILKAN")
            print("=" * 60)
            if article_title:
                print(f"JUDUL: {article_title}")
                print("-" * 60)
            print(article_content)
            if article_excerpt:
                print("\n" + "-" * 60)
                print(f"EXCERPT: {article_excerpt}")
            if meta_desc:
                print(f"META DESC: {meta_desc}")
            if quality_score:
                print(f"\nQUALITY SCORE: {quality_score}/100  |  "
                      f"APPROVED: {'✓ Yes' if approved else '✗ No'}")

            # ── Print SEO metadata block for rewrite ─────────────────
            if is_rewrite and isinstance(rewrite_data, dict):
                seo_meta = rewrite_data.get("seo_metadata", {})
                int_links = rewrite_data.get("internal_links", {})
                if seo_meta:
                    print("\n" + "─" * 60)
                    print("SEO METADATA")
                    print("─" * 60)
                    priority_keys = [
                        "meta_title", "meta_description", "focus_keyword",
                        "secondary_keywords", "slug", "estimated_read_time",
                        "word_count", "featured_snippet_target", "schema_markup"
                    ]
                    for k in priority_keys:
                        v = seo_meta.get(k)
                        if v:
                            print(f"  {k}: {str(v)[:120]}")
                if int_links:
                    print("\n" + "─" * 60)
                    print("INTERNAL LINK RECOMMENDATIONS")
                    print("─" * 60)
                    inbound = int_links.get("inbound_recommendations", [])
                    if inbound:
                        print("  Inbound (artikel lain → artikel ini):")
                        for l in inbound[:3]:
                            print(f"    - {l.get('topic','')} | anchor: {l.get('anchor_text','')}")
                    outbound = int_links.get("outbound_recommendations", [])
                    if outbound:
                        print("  Outbound (artikel ini → artikel lain):")
                        for l in outbound[:3]:
                            print(f"    - {l.get('topic','')} | anchor: {l.get('anchor_text','')}")

            print("=" * 60)

            # ── Save article to file ─────────────────────────────────
            import re as _re
            # For rewrite, use source URL domain as filename prefix
            if is_rewrite:
                src_url = final.get("fetch", {}).get("url", args.keyword)
                domain = _re.sub(r"https?://(www\.)?", "", src_url).split("/")[0]
                safe_kw = _re.sub(r"[^\w-]", "_", domain)[:30]
            else:
                safe_kw = _re.sub(r"[^\w\s-]", "", args.keyword).strip().replace(" ", "_")[:40]

            out_dir = os.path.join(ROOT, "output")
            os.makedirs(out_dir, exist_ok=True)
            out_file = os.path.join(out_dir, f"{safe_kw}_{result['workflow_id']}.md")

            with open(out_file, "w", encoding="utf-8") as f:
                if article_title:
                    f.write(f"# {article_title}\n\n")
                if meta_desc:
                    f.write(f"**Meta:** {meta_desc}\n\n")
                if article_excerpt:
                    f.write(f"**Excerpt:** {article_excerpt}\n\n")
                f.write("---\n\n")
                f.write(article_content)

                # Append SEO metadata & internal links for rewrite
                if is_rewrite and isinstance(rewrite_data, dict):
                    seo_meta = rewrite_data.get("seo_metadata", {})
                    int_links = rewrite_data.get("internal_links", {})
                    if seo_meta:
                        f.write("\n\n---\n\n## SEO Metadata\n\n")
                        for k, v in seo_meta.items():
                            if v:
                                f.write(f"- **{k}**: {v}\n")
                    if int_links:
                        f.write("\n\n---\n\n## Internal Link Recommendations\n\n")
                        f.write(json.dumps(int_links, ensure_ascii=False, indent=2))

                f.write(f"\n\n---\n")
                f.write(f"*Quality: {quality_score}/100 | Workflow: {result['workflow_id']}*\n")

            print(f"\nArtikel disimpan: {out_file}")
        else:
            print("\n[INFO] Tidak ada konten artikel dalam output workflow.")


if __name__ == "__main__":
    main()
