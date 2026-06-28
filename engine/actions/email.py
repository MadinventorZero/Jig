"""Email actions — Gmail send / watch / search, wrapping engine/gmail.py."""
import asyncio
import time as time_mod

from engine.context import RunContext


def _svc(ctx: RunContext):
    if "gmail_service" not in ctx.resources:
        from engine import gmail as gmail_mod
        ctx.resources["gmail_service"] = gmail_mod.get_service()
    return ctx.resources["gmail_service"]


async def handle_gmail_send(ctx: RunContext, params: dict) -> dict:
    from engine import gmail as gmail_mod
    svc  = _svc(ctx)
    sent = gmail_mod.send_message(
        svc,
        to=params["to"],
        subject=params["subject"],
        body=params.get("body", ""),
        in_reply_to=params.get("in_reply_to"),
        thread_id=params.get("thread_id"),
    )
    return {"message_id": sent.get("id"), "thread_id": sent.get("threadId"),
            "ok": True, "choice": "ok"}


async def handle_gmail_watch(ctx: RunContext, params: dict) -> dict:
    """
    Poll Gmail until a non-skipped email arrives from sender, or timeout.
    Returns {email_type, subject, body, thread_id, message_id, choice}.
    On timeout: {choice: 'timeout'}.

    skip_email_types: list of email_type values to silently ignore and
    keep polling (default: ['confirmation_receipt']).
    """
    from engine import gmail as gmail_mod, parser as parser_mod

    svc           = _svc(ctx)
    sender        = params["sender"]
    timeout_secs  = int(params.get("timeout_seconds", 10800))
    poll_interval = int(params.get("poll_interval_seconds", 30))
    skip_types    = set(params.get("skip_email_types", ["confirmation_receipt"]))

    start_ts    = int(time_mod.time())
    deadline    = start_ts + timeout_secs
    after_epoch = start_ts - 60
    attempt     = 0
    max_attempts = max(timeout_secs // max(poll_interval, 1), 1)

    while time_mod.time() < deadline:
        attempt += 1
        msgs = await asyncio.to_thread(
            gmail_mod.list_messages,
            svc, sender=sender, after_epoch=after_epoch, max_results=5
        )

        for m in msgs:
            subj, body, thread_id, msg_id_hdr = await asyncio.to_thread(
                gmail_mod.get_message, svc, m["id"]
            )
            email_type = parser_mod.classify_email(body)
            await asyncio.to_thread(gmail_mod.mark_read, svc, m["id"])

            if email_type in skip_types:
                after_epoch = int(time_mod.time())
                continue

            return {
                "email_type": email_type,
                "subject":    subj,
                "body":       body,
                "thread_id":  thread_id,
                "message_id": msg_id_hdr,
                "choice":     email_type,
            }

        await asyncio.sleep(poll_interval)

    return {"choice": "timeout", "email_type": "timeout"}


async def handle_gmail_search(ctx: RunContext, params: dict) -> dict:
    from engine import gmail as gmail_mod
    svc  = _svc(ctx)
    msgs = gmail_mod.list_messages(
        svc,
        sender=params.get("sender"),
        subject_contains=params.get("subject_contains"),
        after_epoch=params.get("after_epoch"),
        max_results=params.get("max_results", 20),
    )
    return {"messages": msgs, "count": len(msgs), "choice": "ok"}


def register(registry) -> None:
    registry.register("gmail_send",   handle_gmail_send,
                       "Send a Gmail message")
    registry.register("gmail_watch",  handle_gmail_watch,
                       "Poll Gmail until a matching message arrives")
    registry.register("gmail_search", handle_gmail_search,
                       "Search Gmail messages")
