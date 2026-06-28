"""File I/O actions — read, write, csv_parse, json_extract."""
import csv
import json
from pathlib import Path

from engine.context import RunContext


async def handle_file_read(ctx: RunContext, params: dict) -> dict:
    path     = Path(params["path"])
    encoding = params.get("encoding", "utf-8")
    content  = path.read_text(encoding=encoding)
    return {"content": content, "path": str(path), "ok": True, "choice": "ok"}


async def handle_file_write(ctx: RunContext, params: dict) -> dict:
    path = Path(params["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(params["content"], encoding=params.get("encoding", "utf-8"))
    return {"path": str(path), "ok": True, "choice": "ok"}


async def handle_csv_parse(ctx: RunContext, params: dict) -> dict:
    path      = Path(params["path"])
    delimiter = params.get("delimiter", ",")
    with path.open(encoding=params.get("encoding", "utf-8")) as f:
        rows = list(csv.DictReader(f, delimiter=delimiter))
    return {"rows": rows, "count": len(rows), "ok": True, "choice": "ok"}


async def handle_json_extract(ctx: RunContext, params: dict) -> dict:
    """
    Extract a value from a JSON string or dict via dot-notation path.
    e.g. path='data.items.0.name'
    """
    data     = params.get("data")
    dot_path = params.get("path", "")
    if isinstance(data, str):
        data = json.loads(data)
    for key in (dot_path.split(".") if dot_path else []):
        if data is None:
            break
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list):
            try:
                data = data[int(key)]
            except (IndexError, ValueError):
                data = None
    return {"value": data, "ok": True, "choice": "ok"}


def register(registry) -> None:
    registry.register("file_read",    handle_file_read,    "Read a file's text content")
    registry.register("file_write",   handle_file_write,   "Write text to a file")
    registry.register("csv_parse",    handle_csv_parse,    "Parse a CSV file into rows")
    registry.register("json_extract", handle_json_extract, "Extract a value via dot-notation path")
