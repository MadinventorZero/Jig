"""Block action — execute a reusable block as a nested step sequence."""
from engine.context import RunContext


async def handle_block(ctx: RunContext, params: dict) -> dict:
    """
    Run a named block as a nested step sequence with push_block/pop_block isolation.
    """
    block_id     = params["block_id"]
    block_params = {k: v for k, v in params.items() if k != "block_id"}

    block_registry = ctx.resources.get("_block_registry")
    if not block_registry:
        raise RuntimeError("block action requires _block_registry in ctx.resources")

    block = block_registry.get(block_id)
    if not block:
        raise RuntimeError(f"Block {block_id!r} not found in registry "
                           f"(available: {block_registry.list()})")

    emit     = ctx.resources.get("_emit") or (lambda *a, **k: None)
    registry = ctx.resources.get("_registry")
    db       = ctx.resources.get("_db")
    run_id   = ctx.resources.get("_run_id", "")

    emit(
        "block.started",
        step_id=ctx._data.get("_current_step_id"),
        message=f"[block:{block_id}] starting",
        block_id=block_id,
        param_keys=list(block_params.keys()),
    )

    ctx.push_block(block_id, block_params)
    last_result: dict = {}
    try:
        from engine.executor import StepExecutor, StepError

        executor   = StepExecutor(registry, db)
        step_index = {s.step_id: s for s in block.steps}
        step_order = [s.step_id for s in block.steps]
        n = len(step_order)
        i = 0

        while i < n:
            step = step_index[step_order[i]]
            if not step.enabled:
                i += 1
                continue

            try:
                _, result = await executor.execute(step, ctx, run_id, emit)
                last_result = result
            except TimeoutError:
                if step.on_timeout and step.on_timeout in step_index:
                    i = step_order.index(step.on_timeout)
                    continue
                raise
            except StepError:
                if step.on_error and step.on_error in step_index:
                    i = step_order.index(step.on_error)
                    continue
                raise

            choice = result.get("choice")
            if choice and step.on_choice:
                raw = step.on_choice.get(str(choice))
                if raw:
                    target = raw.replace("skip_to:", "").strip()
                    if target == "__end__":
                        break
                    if target in step_index:
                        i = step_order.index(target)
                        continue
            i += 1

    finally:
        ctx.pop_block()

    emit(
        "block.completed",
        step_id=ctx._data.get("_current_step_id"),
        message=f"[block:{block_id}] done",
        block_id=block_id,
    )

    return {"block_id": block_id, "result": last_result, "choice": "ok"}


def register(registry) -> None:
    registry.register("block", handle_block,
                       "Execute a reusable block by ID as a nested sequence")
