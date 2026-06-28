#!/usr/bin/env python3
"""
Mad Automation Platform v3 — CLI flow runner.

Usage:
  python run_flow.py --flow-id beverly_hills_photo_permit --profile-id <id>
  python run_flow.py --flow-id beverly_hills_photo_permit --profile-id <id> --validate
  python run_flow.py --flow-id beverly_hills_photo_permit --profile-id <id> --show-browser
  python run_flow.py --resume-run <run_id>
  python run_flow.py --list-flows
"""
import argparse
import asyncio
import queue
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main() -> None:
    p = argparse.ArgumentParser(description="Mad Automation Platform v3")
    p.add_argument("--flow-id",     help="Flow ID to run (YAML filename without extension)")
    p.add_argument("--profile-id",  help="Profile ID to use (from data/profiles/)")
    p.add_argument("--validate",    action="store_true",
                   help="Dry-run: validate flow + context without executing steps")
    p.add_argument("--show-browser",action="store_true",
                   help="Show browser window instead of running headless")
    p.add_argument("--resume-run",  help="Resume a failed run from its last checkpoint")
    p.add_argument("--list-flows",  action="store_true",
                   help="Print available flow IDs and exit")
    p.add_argument("--run-id",       help="Pre-assigned run ID (allows UI to poll before subprocess starts)")
    p.add_argument("--log-events",  action="store_true",
                   help="Stream SSE events to stdout during execution")
    args = p.parse_args()

    if args.list_flows:
        _list_flows(); return

    if args.resume_run:
        asyncio.run(_resume(args.resume_run)); return

    if not args.flow_id:
        p.error("--flow-id is required")
    if not args.profile_id and not args.validate:
        p.error("--profile-id is required (or use --validate for a no-profile check)")

    asyncio.run(_run(args))


# ── Flow listing ──────────────────────────────────────────────────────────────

def _list_flows() -> None:
    flows_dir = Path(__file__).parent / "sources" / "flows"
    yamls = sorted(flows_dir.glob("*.yaml")) if flows_dir.exists() else []
    if not yamls:
        print("No flows found in sources/flows/")
        return
    for f in yamls:
        print(f.stem)


# ── Main run ──────────────────────────────────────────────────────────────────

async def _run(args) -> None:
    from engine.db import Store
    from engine.registry import ActionRegistry
    from engine.pipeline import Pipeline
    from engine.context import RunContext
    from engine.v3_models import Run, utc_now, new_run_id
    from engine.block_registry import BlockRegistry

    registry       = ActionRegistry()
    block_registry = BlockRegistry()
    _register_actions(registry)

    flow = _load_flow(args.flow_id)
    print(f"Flow : {flow.name}  (v{flow.version})")
    print(f"Steps: {[s.step_id for s in flow.steps]}")

    if args.validate:
        _validate(flow, registry, block_registry)
        print("\nValidation passed — no steps executed.")
        return

    import engine.store as v2_store
    profile = v2_store.get_profile(args.profile_id)
    if not profile:
        print(f"ERROR: profile {args.profile_id!r} not found", file=sys.stderr)
        sys.exit(1)

    db     = Store()
    sse_q  = queue.Queue()
    run_id = args.run_id if args.run_id else new_run_id()

    run = Run(
        run_id=run_id,
        flow_id=flow.id,
        trigger_type="manual",
        profile_id=args.profile_id,
        started_at=utc_now(),
    )
    db.insert_run(run)

    ctx = RunContext(
        flow_id=flow.id,
        flow_name=flow.name,
        run_id=run_id,
        log_dir=f"data/logs/{run_id}",
        profile=profile,
    )
    ctx.resources["_headless"]        = not args.show_browser
    ctx.resources["_block_registry"]  = block_registry

    pipeline = Pipeline(flow=flow, run=run, db=db,
                        registry=registry, sse_queue=sse_q)

    if args.log_events:
        t = threading.Thread(target=_stream_events, args=(sse_q,), daemon=True)
        t.start()

    print(f"\nRun ID : {run_id}")
    print("Running...\n")

    status = await pipeline.run_flow(ctx)

    print(f"\n{'='*50}")
    print(f"Status : {status}")
    print(f"Run ID : {run_id}")
    print(f"Logs   : python run_flow.py --resume-run {run_id}  (if needed)")

    # Print run summary
    summary = db.get_run_summary(run_id)
    if summary:
        print(f"Steps  : {summary.get('steps_completed', 0)} completed, "
              f"{summary.get('steps_failed', 0)} failed")
        if summary.get("decision_chain"):
            print(f"Decisions: {summary['decision_chain']}")


async def _resume(run_id: str) -> None:
    import json
    from engine.db import Store
    from engine.registry import ActionRegistry
    from engine.pipeline import Pipeline
    from engine.context import RunContext
    from engine.v3_models import Run
    from engine.block_registry import BlockRegistry

    db       = Store()
    run_data = db.get_run(run_id)
    if not run_data:
        print(f"ERROR: run {run_id!r} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Run    : {run_id}")
    print(f"Status : {run_data['status']}")
    print(f"Flow   : {run_data['flow_id']}")

    if run_data["status"] not in ("cancelled", "aborted", "failed"):
        print("Run is not in a failed/cancelled state — no resume needed.")
        return

    flow = _load_flow(run_data["flow_id"])

    import engine.store as v2_store
    profile = v2_store.get_profile(run_data["profile_id"])
    if not profile:
        print(f"ERROR: profile {run_data['profile_id']!r} not found", file=sys.stderr)
        sys.exit(1)

    completed = db.get_completed_steps(run_id)
    print(f"Checkpoint: {len(completed)} step(s) already done — will skip them.")

    db.reset_run_for_resume(run_id)

    run = Run(
        run_id=run_id,
        flow_id=run_data["flow_id"],
        trigger_type=run_data["trigger_type"],
        profile_id=run_data["profile_id"],
        started_at=run_data["started_at"],
    )

    ctx = RunContext(
        flow_id=flow.id,
        flow_name=flow.name,
        run_id=run_id,
        log_dir=f"data/logs/{run_id}",
        profile=profile,
    )
    ctx.resources["_headless"]       = True
    ctx.resources["_block_registry"] = BlockRegistry()

    for row in completed:
        result = json.loads(row["result"]) if row.get("result") else {}
        ctx.set_step_result(row["step_id"], result)

    registry = ActionRegistry()
    _register_actions(registry)

    pipeline = Pipeline(flow=flow, run=run, db=db,
                        registry=registry, sse_queue=queue.Queue())

    print(f"\nResuming...\n")
    status = await pipeline.run_flow(ctx)

    print(f"\n{'='*50}")
    print(f"Status : {status}")
    print(f"Run ID : {run_id}")
    summary = db.get_run_summary(run_id)
    if summary:
        print(f"Steps  : {summary.get('steps_completed', 0)} completed, "
              f"{summary.get('steps_failed', 0)} failed")


# ── Flow loading ──────────────────────────────────────────────────────────────

def _load_flow(flow_id: str):
    import yaml
    from engine.v3_models import FlowDef, StepDef, TriggerDef

    flows_dir = Path(__file__).parent / "sources" / "flows"
    candidates = [
        flows_dir / f"{flow_id}.yaml",
        flows_dir / f"booking_{flow_id}.yaml",
    ]
    path = next((c for c in candidates if c.exists()), None)
    if not path:
        print(f"ERROR: flow {flow_id!r} not found in {flows_dir}", file=sys.stderr)
        print(f"       Tried: {[str(c) for c in candidates]}", file=sys.stderr)
        sys.exit(1)

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    trigger = TriggerDef(
        type=raw.get("trigger", {}).get("type", "manual"),
        params=raw.get("trigger", {}).get("params", {}),
    )

    steps = []
    for s in raw.get("steps", []):
        block_ref = s.get("block")
        step_type = s["type"]
        params    = s.get("params", {})
        # Shorthand: "block: my_block_id" sets type=block and injects block_id
        if block_ref and step_type != "block":
            step_type       = "block"
            params          = {**params, "block_id": block_ref}
        elif block_ref:
            params.setdefault("block_id", block_ref)
        steps.append(StepDef(
            step_id=             s["step_id"],
            type=                step_type,
            params=              params,
            mode=                s.get("mode", "dom"),
            max_retries=         s.get("max_retries", 0),
            retry_delay_seconds= s.get("retry_delay_seconds", 1.0),
            idempotent=          s.get("idempotent", True),
            on_choice=           s.get("on_choice", {}),
            on_timeout=          s.get("on_timeout"),
            on_error=            s.get("on_error"),
            on_error_mode=       s.get("on_error_mode", "blocking"),
            enabled=             s.get("enabled", True),
            block_ref=           block_ref,
        ))

    return FlowDef(
        id=          raw["id"],
        name=        raw["name"],
        version=     raw.get("version", 1),
        trigger=     trigger,
        steps=       steps,
        context=     raw.get("context", {}),
        concurrency= raw.get("concurrency", "serial"),
        on_error=    raw.get("on_error"),
    )


def _validate(flow, registry=None, block_registry=None) -> None:
    """Check on_choice targets and run contract chain validation."""
    from engine.contracts import ChainValidator, BUILTIN_CONTRACTS

    step_ids = {s.step_id for s in flow.steps}
    errors:   list[str] = []
    warnings: list[str] = []

    # ── Structural checks (on_choice / on_timeout / on_error targets) ─────────
    for step in flow.steps:
        for choice, target in step.on_choice.items():
            clean = target.replace("skip_to:", "").strip()
            if clean not in ("__end__",) and clean not in step_ids:
                errors.append(
                    f"Step {step.step_id!r}: on_choice[{choice!r}] → "
                    f"{clean!r} not found in flow"
                )
        if step.on_timeout and step.on_timeout not in step_ids:
            errors.append(
                f"Step {step.step_id!r}: on_timeout → "
                f"{step.on_timeout!r} not found in flow"
            )
        if step.on_error and step.on_error not in step_ids:
            errors.append(
                f"Step {step.step_id!r}: on_error → "
                f"{step.on_error!r} not found in flow"
            )

    # ── Contract chain validation ─────────────────────────────────────────────
    if registry is not None:
        registry.apply_contracts(BUILTIN_CONTRACTS)
        violations = ChainValidator(registry, block_registry).validate(flow)
        for v in violations:
            msg = f"[{v.step_id}] {v.kind}: {v.message}"
            if v.severity == "error":
                errors.append(msg)
            else:
                warnings.append(msg)

    for w in warnings:
        print(f"CONTRACT WARNING: {w}", file=sys.stderr)
    for e in errors:
        print(f"VALIDATION ERROR: {e}", file=sys.stderr)

    if errors:
        sys.exit(1)


# ── Action registration ───────────────────────────────────────────────────────

def _register_actions(registry) -> None:
    from engine.actions import (
        browser, email, flow_control, notification,
        http, file as file_actions, script, storage,
        llm, block as block_actions, captcha,
    )
    browser.register(registry)
    email.register(registry)
    flow_control.register(registry)
    notification.register(registry)
    http.register(registry)
    file_actions.register(registry)
    script.register(registry)
    storage.register(registry)
    llm.register(registry)
    block_actions.register(registry)
    captcha.register(registry)

    try:
        from engine.actions import vision
        vision.register(registry)
    except ImportError as exc:
        print(f"[warn] vision actions not loaded: {exc}", file=sys.stderr)

    try:
        from sources.actions import bh_actions
        bh_actions.register(registry)
    except ImportError as exc:
        print(f"[warn] bh_actions not loaded: {exc}", file=sys.stderr)


# ── SSE log streaming ─────────────────────────────────────────────────────────

_COLORS = {
    "ERROR": "\033[91m",
    "WARN":  "\033[93m",
    "INFO":  "\033[0m",
    "DEBUG": "\033[90m",
}
_RESET = "\033[0m"


def _stream_events(q: queue.Queue) -> None:
    while True:
        try:
            ev    = q.get(timeout=0.5)
            color = _COLORS.get(ev.get("level", "INFO"), "")
            print(f"{color}{ev.get('message', '')}{_RESET}", flush=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
