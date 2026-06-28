"""Captcha actions — detect, extract tiles, execute, parse_reply."""
import asyncio
import base64
import os
import tempfile
from pathlib import Path

from engine.context import RunContext


_CAPTCHA_TOOL = {
    "name": "report_captcha_analysis",
    "description": "Report analysis of the CAPTCHA image",
    "input_schema": {
        "type": "object",
        "properties": {
            "captcha_type": {
                "type": "string",
                "enum": ["checkbox", "image_grid", "text", "audio", "slider", "none"],
            },
            "is_present": {
                "type": "boolean",
                "description": "Whether an unsolved CAPTCHA challenge is visible",
            },
            "instructions": {
                "type": "string",
                "description": "The CAPTCHA instruction text",
            },
            "tile_positions": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "0-indexed tile positions to click (image_grid type)",
            },
            "reasoning": {"type": "string"},
        },
        "required": ["is_present", "captcha_type"],
    },
}


def _get_client(ctx: RunContext):
    client = ctx.resources.get("_anthropic_client")
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
        ctx.resources["_anthropic_client"] = client
    return client


async def _screenshot_bytes(ctx: RunContext, screenshot_path: str | None) -> bytes | None:
    if screenshot_path:
        return Path(screenshot_path).read_bytes()
    page = ctx.resources.get("browser")
    if page:
        tmp = tempfile.mktemp(suffix=".jpeg")
        await page.screenshot(path=tmp)
        data = Path(tmp).read_bytes()
        os.unlink(tmp)
        return data
    return None


async def handle_captcha_detect(ctx: RunContext, params: dict) -> dict:
    model = params.get("model", "claude-sonnet-4-6")
    img   = await _screenshot_bytes(ctx, params.get("screenshot_path"))
    if img is None:
        return {"is_present": False, "captcha_type": "none", "choice": "no_captcha"}

    b64      = base64.standard_b64encode(img).decode()
    client   = _get_client(ctx)
    response = await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=512,
        temperature=0,
        tools=[_CAPTCHA_TOOL],
        tool_choice={"type": "any"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text",
                 "text": "Is there an unsolved CAPTCHA challenge in this screenshot? "
                         "Use the report_captcha_analysis tool."},
            ],
        }],
    )

    result = {"is_present": False, "captcha_type": "none"}
    for block in response.content:
        if block.type == "tool_use" and block.name == "report_captcha_analysis":
            result.update(block.input)
            break

    return {**result, "choice": "captcha" if result.get("is_present") else "no_captcha"}


async def handle_captcha_extract_tiles(ctx: RunContext, params: dict) -> dict:
    model        = params.get("model", "claude-sonnet-4-6")
    instructions = params.get("instructions", "")
    grid_size    = int(params.get("grid_size", 9))
    img          = await _screenshot_bytes(ctx, params.get("screenshot_path"))
    if img is None:
        return {"tile_positions": [], "count": 0, "choice": "ok"}

    side   = int(grid_size ** 0.5)
    b64    = base64.standard_b64encode(img).decode()
    client = _get_client(ctx)

    response = await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=512,
        temperature=0,
        tools=[_CAPTCHA_TOOL],
        tool_choice={"type": "any"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text",
                 "text": f"This is a {side}×{side} CAPTCHA image grid. "
                         f"Instruction: '{instructions}'. "
                         f"Which tiles match? Report 0-indexed positions "
                         f"(left-to-right, top-to-bottom). "
                         f"Use the report_captcha_analysis tool."},
            ],
        }],
    )

    tiles = []
    for block in response.content:
        if block.type == "tool_use" and block.name == "report_captcha_analysis":
            tiles = block.input.get("tile_positions", [])
            break

    return {"tile_positions": tiles, "count": len(tiles), "choice": "ok"}


async def handle_captcha_execute(ctx: RunContext, params: dict) -> dict:
    tile_positions  = params["tile_positions"]
    grid_selector   = params.get("grid_selector", ".rc-imageselect-table")
    submit_selector = params.get("submit_selector", "#recaptcha-verify-button")

    page = ctx.resources.get("browser")
    if not page:
        raise RuntimeError("captcha_execute requires browser in ctx.resources")

    tiles = await page.query_selector_all(f"{grid_selector} td")
    for pos in tile_positions:
        if pos < len(tiles):
            await tiles[pos].click()
            await asyncio.sleep(0.3)

    await asyncio.sleep(0.8)
    submit_btn = await page.query_selector(submit_selector)
    if submit_btn:
        await submit_btn.click()

    return {"clicked": len(tile_positions), "choice": "ok"}


async def handle_captcha_parse_reply(ctx: RunContext, params: dict) -> dict:
    model  = params.get("model", "claude-haiku-4-5-20251001")
    img    = await _screenshot_bytes(ctx, params.get("screenshot_path"))
    if img is None:
        return {"solved": False, "choice": "unsolved"}

    b64      = base64.standard_b64encode(img).decode()
    client   = _get_client(ctx)
    response = await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=256,
        temperature=0,
        tools=[_CAPTCHA_TOOL],
        tool_choice={"type": "any"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text",
                 "text": "Is a CAPTCHA challenge still present and unsolved? "
                         "Use the report_captcha_analysis tool."},
            ],
        }],
    )

    is_present = True
    for block in response.content:
        if block.type == "tool_use" and block.name == "report_captcha_analysis":
            is_present = block.input.get("is_present", True)
            break

    solved = not is_present
    return {"solved": solved, "choice": "solved" if solved else "unsolved"}


def register(registry) -> None:
    registry.register("captcha_detect",        handle_captcha_detect,
                       "Detect if a CAPTCHA challenge is present on screen")
    registry.register("captcha_extract_tiles", handle_captcha_extract_tiles,
                       "Identify CAPTCHA grid tile positions to click")
    registry.register("captcha_execute",       handle_captcha_execute,
                       "Click CAPTCHA tiles and submit the challenge")
    registry.register("captcha_parse_reply",   handle_captcha_parse_reply,
                       "Check if CAPTCHA was successfully solved")
