"""HTTP actions — http_request, webhook_send."""
import httpx

from engine.context import RunContext


async def handle_http_request(ctx: RunContext, params: dict) -> dict:
    method   = params.get("method", "GET").upper()
    url      = params["url"]
    headers  = params.get("headers", {})
    timeout  = float(params.get("timeout_seconds", 30))
    body     = params.get("body")

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method, url,
            headers=headers,
            json=body if isinstance(body, dict) else None,
            content=body.encode() if isinstance(body, str) else None,
            timeout=timeout,
        )

    is_json = "application/json" in resp.headers.get("content-type", "")
    return {
        "status_code": resp.status_code,
        "ok":          resp.is_success,
        "body":        resp.text,
        "json":        resp.json() if is_json else None,
        "headers":     dict(resp.headers),
        "choice":      "ok" if resp.is_success else "error",
    }


async def handle_webhook_send(ctx: RunContext, params: dict) -> dict:
    return await handle_http_request(ctx, {**params, "method": "POST"})


def register(registry) -> None:
    registry.register("http_request",  handle_http_request,
                       "HTTP GET/POST/etc. request via httpx")
    registry.register("webhook_send",  handle_webhook_send,
                       "POST JSON payload to a webhook URL")
