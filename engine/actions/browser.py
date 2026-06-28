"""Browser actions — Playwright DOM automation wrapping engine/browser.py."""
import asyncio
import random
from pathlib import Path

from engine.context import RunContext


async def _page(ctx: RunContext):
    """Return the shared Playwright page for this run, creating it if needed."""
    if "browser" not in ctx.resources:
        from engine.browser import BookingBrowser
        headless = ctx.resources.get("_headless", True)
        b = BookingBrowser(headless=headless)
        await b.start()
        ctx.resources["browser"] = b
    return ctx.resources["browser"].page


async def handle_browser_navigate(ctx: RunContext, params: dict) -> dict:
    page = await _page(ctx)
    url = params["url"]
    await page.goto(url, wait_until=params.get("wait_until", "networkidle"))
    await asyncio.sleep(random.uniform(1.0, 2.0))
    return {"url": url, "ok": True}


async def handle_browser_fill(ctx: RunContext, params: dict) -> dict:
    from engine.browser import human_type
    page = await _page(ctx)
    await human_type(page, params["selector"], str(params["value"]))
    return {"ok": True, "selector": params["selector"]}


async def handle_browser_click(ctx: RunContext, params: dict) -> dict:
    from engine.browser import human_click
    page = await _page(ctx)
    await human_click(page, params["selector"])
    if params.get("wait_after") == "networkidle":
        await page.wait_for_load_state("networkidle")
    return {"ok": True, "selector": params["selector"]}


async def handle_browser_screenshot(ctx: RunContext, params: dict) -> dict:
    page = await _page(ctx)
    run_id  = ctx._data["run"]["id"]
    save_to = params.get("save_to", f"data/logs/{run_id}/screenshot.png")
    path    = Path(save_to)
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)
    return {"path": str(path), "ok": True}


async def handle_browser_extract(ctx: RunContext, params: dict) -> dict:
    page      = await _page(ctx)
    selector  = params["selector"]
    attribute = params.get("attribute", "textContent")
    element   = await page.query_selector(selector)
    if not element:
        return {"value": None, "found": False}
    if attribute == "textContent":
        value = await element.text_content()
    else:
        value = await element.get_attribute(attribute)
    return {"value": value, "found": True}


def register(registry) -> None:
    registry.register("browser_navigate",   handle_browser_navigate,
                       "Navigate browser to URL")
    registry.register("browser_fill",       handle_browser_fill,
                       "Fill a form field (human-emulated typing)")
    registry.register("browser_click",      handle_browser_click,
                       "Click an element (human-emulated)")
    registry.register("browser_screenshot", handle_browser_screenshot,
                       "Take a full-page screenshot")
    registry.register("browser_extract",    handle_browser_extract,
                       "Extract a value from a DOM element")
