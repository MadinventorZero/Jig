"""Storage actions — store_get, store_set backed by SQLite KV table."""
from engine.context import RunContext


async def handle_store_set(ctx: RunContext, params: dict) -> dict:
    db  = ctx.resources.get("_db")
    key = str(params["key"])
    val = params["value"]
    if db:
        db.kv_set(key, val)
    ctx._data["vars"][key] = val
    return {"key": key, "ok": True, "choice": "ok"}


async def handle_store_get(ctx: RunContext, params: dict) -> dict:
    db      = ctx.resources.get("_db")
    key     = str(params["key"])
    default = params.get("default")
    value   = ctx._data["vars"].get(key, default)
    if db:
        stored = db.kv_get(key)
        if stored is not None:
            value = stored
    return {"key": key, "value": value, "ok": True, "choice": "ok"}


def register(registry) -> None:
    registry.register("store_set", handle_store_set,
                       "Persist a value to the run KV store")
    registry.register("store_get", handle_store_get,
                       "Read a persisted value from the run KV store")
