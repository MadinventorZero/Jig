"""Human-readable error messages for step failures."""
from __future__ import annotations


def humanize_exception(exc: Exception) -> str:
    """Map a raw exception to a plain-English explanation a non-developer can act on."""
    cls = type(exc).__name__
    msg = str(exc)
    low = msg.lower()

    # ── Playwright timeout ─────────────────────────────────────────────────────
    if "TimeoutError" in cls or ("timeout" in low and "exceeded" in low):
        if any(x in low for x in ["navigation", "goto", "waitfornavigation", "load"]):
            return (
                "Page didn't finish loading — the site may be slow or the URL "
                "may have changed."
            )
        return "Timed out waiting for an element or page state to appear."

    # ── Playwright element not found ───────────────────────────────────────────
    if any(x in low for x in [
        "no element found", "element not found",
        "strict mode violation", "found 0 elements",
        "locator resolved to", "unable to find",
    ]):
        return (
            "Couldn't find the element — it may have moved or the page loaded "
            "differently. The screenshot shows what was visible."
        )

    # ── CAPTCHA ────────────────────────────────────────────────────────────────
    if "captcha" in low or "recaptcha" in low:
        return "A CAPTCHA appeared. Manual intervention required before continuing."

    # ── Gmail / Google API ─────────────────────────────────────────────────────
    if any(x in low for x in ["gmail", "googleapis", "oauth", "credentials.json", "token.json"]):
        return "Gmail connection issue — check that API credentials are still valid in Settings."

    # ── Network / connection ───────────────────────────────────────────────────
    if any(x in low for x in [
        "connection refused", "err_connection_refused",
        "net::err_", "name or service not known",
        "connection reset", "remotely closed",
    ]):
        return "Could not connect to the target page — the site may be unavailable or the network is down."

    # ── Screenshot ────────────────────────────────────────────────────────────
    if "screenshot" in low and ("fail" in low or "error" in low):
        return "Screenshot failed — the browser window may have lost focus or closed."

    # ── Contract errors (already well-formatted) ───────────────────────────────
    if "ContractError" in cls or "contract" in cls.lower():
        return msg

    # ── Block not found ────────────────────────────────────────────────────────
    if "block" in low and "not found" in low:
        return f"Block not found in registry — check that the block YAML exists in sources/blocks/. ({msg})"

    # ── Generic fallback — trim noise but keep the message ────────────────────
    clean = msg.strip()
    if len(clean) > 240:
        clean = clean[:240] + "…"
    return clean
