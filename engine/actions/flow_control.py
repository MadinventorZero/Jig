"""Flow control actions — condition, wait, human_pause, set_variable."""
import asyncio

from engine.context import RunContext


async def handle_condition(ctx: RunContext, params: dict) -> dict:
    """Return a value as choice for on_choice branching."""
    value = str(params.get("value", ""))
    return {"choice": value, "value": value}


async def handle_set_variable(ctx: RunContext, params: dict) -> dict:
    """Write key/value pairs into the run context vars dict."""
    for k, v in params.items():
        if not k.startswith("_"):
            ctx._data["vars"][k] = v
    return {"ok": True, "set": list(params.keys()), "choice": "ok"}


async def handle_wait(ctx: RunContext, params: dict) -> dict:
    seconds = float(params.get("seconds", 1))
    await asyncio.sleep(seconds)
    return {"waited_seconds": seconds, "choice": "ok"}


async def handle_human_pause(ctx: RunContext, params: dict) -> dict:
    """Suspend the flow for human intervention. Resume/abort via v3 KV store."""
    run_id      = ctx._data["run"]["id"]
    step_id     = params.get("step_id", "human_pause")
    description = params.get("description", "Awaiting human input")
    timeout     = int(params.get("timeout_seconds", 300))

    db = ctx.resources.get("_db")
    db.kv_set(f"halt:{run_id}", {
        "step_id":     step_id,
        "description": description,
        "data":        params.get("data", {}),
    })

    elapsed = 0
    while elapsed < timeout:
        resume = db.kv_get(f"resume:{run_id}")
        if resume:
            action = resume.get("action")
            db.kv_set(f"halt:{run_id}", None)
            db.kv_set(f"resume:{run_id}", None)
            if action == "abort":
                from engine.pipeline import FlowCancelledError
                raise FlowCancelledError("User aborted at human_pause")
            return {"resumed": True, "action": action,
                    "waited_seconds": elapsed, "choice": "ok"}
        await asyncio.sleep(1)
        elapsed += 1

    db.kv_set(f"halt:{run_id}", None)
    return {"choice": "timeout", "waited_seconds": elapsed}


async def handle_loop(ctx: RunContext, params: dict) -> dict:
    """Iterate over items or a count range, running a block for each item."""
    block_id             = params.get("block_id")
    items                = params.get("items", [])
    count                = params.get("count")
    block_params_tmpl    = params.get("block_params", {})

    if count is not None:
        items = list(range(int(count)))
    if isinstance(items, str):
        import json as _json
        try:
            items = _json.loads(items)
        except Exception:
            items = [items]

    block_registry = ctx.resources.get("_block_registry")
    results: list  = []

    for idx, item in enumerate(items):
        ctx._data["vars"]["loop_index"] = idx
        ctx._data["vars"]["loop_item"]  = item

        if block_id and block_registry:
            from engine.actions.block import handle_block
            resolved = ctx.resolve_params(block_params_tmpl)
            result   = await handle_block(ctx, {"block_id": block_id, **resolved})
            results.append(result)

    return {"iterations": len(items), "results": results, "choice": "ok"}


def register(registry) -> None:
    registry.register("condition",    handle_condition,
                       "Branch on a resolved value")
    registry.register("set_variable", handle_set_variable,
                       "Write values into run context vars")
    registry.register("wait",         handle_wait,
                       "Sleep for N seconds")
    registry.register("human_pause",  handle_human_pause,
                       "Pause for human intervention, resume via UI")
    registry.register("loop",         handle_loop,
                       "Iterate over items or count, running a block per iteration")
