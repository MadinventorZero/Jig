"""LLM actions — llm_decide, claude_complete, claude_extract."""
import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path

from engine.context import RunContext
from engine.v3_models import Decision, utc_now


_DECIDE_TOOL = {
    "name": "report_decision",
    "description": "Report the decision made based on the prompt",
    "input_schema": {
        "type": "object",
        "properties": {
            "choice": {
                "type": "string",
                "description": "The chosen option from the list of valid choices",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief reasoning for the decision",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence level from 0.0 to 1.0",
            },
        },
        "required": ["choice", "reasoning"],
    },
}


def _get_client(ctx: RunContext):
    client = ctx.resources.get("_anthropic_client")
    if client is None:
        import anthropic
        client = anthropic.Anthropic()
        ctx.resources["_anthropic_client"] = client
    return client


async def handle_llm_decide(ctx: RunContext, params: dict) -> dict:
    """
    Make a structured decision using Claude. Returns choice as routing key.
    Stores a Decision record in SQLite for audit trail.
    """
    prompt          = params["prompt"]
    choices         = params.get("choices", [])
    model           = params.get("model", "claude-sonnet-4-6")
    context_text    = params.get("context", "")
    screenshot_path = params.get("screenshot_path")

    client  = _get_client(ctx)
    content: list = []

    if screenshot_path:
        import base64
        img_bytes = Path(screenshot_path).read_bytes()
        b64       = base64.standard_b64encode(img_bytes).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })

    full_prompt = prompt
    if choices:
        full_prompt += f"\n\nValid choices: {', '.join(choices)}"
    if context_text:
        full_prompt = f"Context: {context_text}\n\n{full_prompt}"

    content.append({"type": "text", "text": full_prompt})

    prompt_hash      = hashlib.sha256(full_prompt.encode()).hexdigest()[:16]
    screenshot_hash  = (
        hashlib.sha256(Path(screenshot_path).read_bytes()).hexdigest()[:16]
        if screenshot_path else None
    )

    t0       = time.monotonic()
    response = await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=512,
        temperature=0,
        tools=[_DECIDE_TOOL],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": content}],
    )
    latency_ms = int((time.monotonic() - t0) * 1000)

    choice     = None
    reasoning  = ""
    confidence = None

    for block in response.content:
        if block.type == "tool_use" and block.name == "report_decision":
            d          = block.input
            choice     = d.get("choice", "")
            reasoning  = d.get("reasoning", "")
            confidence = d.get("confidence")
            break

    if not choice:
        raise RuntimeError("llm_decide: no decision returned by model")

    decision_id  = str(uuid.uuid4())
    step_id      = ctx._data.get("_current_step_id", "unknown")
    decision     = Decision(
        decision_id=decision_id,
        run_id=ctx._data["run"]["id"],
        step_id=step_id,
        model=model,
        prompt_hash=prompt_hash,
        screenshot_hash=screenshot_hash,
        choice=choice,
        reasoning=reasoning,
        confidence=confidence,
        latency_ms=latency_ms,
        created_at=utc_now(),
    )

    db = ctx.resources.get("_db")
    if db:
        db.insert_decision(decision)

    emit = ctx.resources.get("_emit")
    if emit:
        emit(
            "llm.decided",
            step_id=step_id,
            message=f"llm_decide → {choice} ({reasoning[:80]})",
            choice=choice,
            reasoning=reasoning,
            confidence=confidence,
            latency_ms=latency_ms,
            prompt_hash=prompt_hash,
            decision_id=decision_id,
        )

    return {
        "choice":      choice,
        "reasoning":   reasoning,
        "confidence":  confidence,
        "latency_ms":  latency_ms,
        "decision_id": decision_id,
    }


async def handle_claude_complete(ctx: RunContext, params: dict) -> dict:
    prompt     = params["prompt"]
    model      = params.get("model", "claude-sonnet-4-6")
    max_tokens = int(params.get("max_tokens", 1024))
    system     = params.get("system", "")

    client = _get_client(ctx)
    kwargs: dict = dict(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system

    response = await asyncio.to_thread(client.messages.create, **kwargs)
    text     = response.content[0].text if response.content else ""

    return {"text": text, "ok": True, "choice": "ok"}


async def handle_claude_extract(ctx: RunContext, params: dict) -> dict:
    """Extract structured fields from text using Claude."""
    text   = params["text"]
    fields = params["fields"]  # list of str or list of {name, description}
    model  = params.get("model", "claude-haiku-4-5-20251001")

    client      = _get_client(ctx)
    field_lines = []
    for f in fields:
        if isinstance(f, str):
            field_lines.append(f"- {f}")
        else:
            field_lines.append(f"- {f['name']}: {f.get('description', '')}")

    prompt = (
        "Extract the following fields from the text below.\n"
        "Return ONLY a JSON object with exactly these keys.\n\n"
        "Fields:\n" + "\n".join(field_lines) +
        f"\n\nText:\n{text}"
    )

    response  = await asyncio.to_thread(
        client.messages.create,
        model=model,
        max_tokens=1024,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.content[0].text if response.content else "{}"

    try:
        extracted = json.loads(raw)
    except json.JSONDecodeError:
        import re
        m         = re.search(r"\{.*\}", raw, re.DOTALL)
        extracted = json.loads(m.group()) if m else {}

    return {"extracted": extracted, "ok": True, "choice": "ok"}


def register(registry) -> None:
    registry.register("llm_decide",      handle_llm_decide,
                       "Structured decision via Claude tool use (temperature=0, audited)")
    registry.register("claude_complete", handle_claude_complete,
                       "Free-form text completion via Claude")
    registry.register("claude_extract",  handle_claude_extract,
                       "Extract structured fields from text using Claude")
