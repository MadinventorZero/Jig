"""Structured email intervention loop — pause for user input on blocked states."""
import time
from typing import Optional


INTERVENTION_TIMEOUT_HOURS = 24
POLL_INTERVAL_SECONDS = 60


def build_intervention_email(situation: str, options: list[dict]) -> str:
    """
    Build a plain-text structured email for user action.
    options: [{"key": "A", "label": "..."}, ...]
    User replies with just the option letter.
    """
    lines = [
        "Jig — Action Required",
        "=" * 40,
        "",
        situation,
        "",
        "Please reply with one of the following options:",
        "",
    ]
    for opt in options:
        lines.append(f"  {opt['key']}) {opt['label']}")
    lines += [
        "",
        "Reply to this email with just the option letter (e.g., 'A') to proceed.",
        "",
        "— Jig",
    ]
    return "\n".join(lines)


def parse_reply(reply_text: str, valid_keys: list[str]) -> Optional[str]:
    """Extract the user's choice from the first few lines of a reply."""
    import re
    valid_upper = [k.upper() for k in valid_keys]
    for line in reply_text.strip().splitlines()[:5]:
        line = line.strip().upper()
        m = re.match(r'^([A-Z])\b', line)
        if m and m.group(1) in valid_upper:
            return m.group(1)
    return None


def poll_for_reply(gmail_service, thread_id: str, sent_message_id: str,
                   valid_keys: list[str],
                   timeout_hours: int = INTERVENTION_TIMEOUT_HOURS,
                   poll_interval: int = POLL_INTERVAL_SECONDS) -> Optional[str]:
    """
    Poll Gmail thread for a reply from ourselves (self-email intervention pattern).
    Returns the parsed option key, or None on timeout.
    """
    from engine.gmail import _extract_body

    deadline = time.time() + timeout_hours * 3600

    while time.time() < deadline:
        thread = gmail_service.users().threads().get(
            userId='me', id=thread_id, format='full'
        ).execute()

        for msg in thread.get('messages', []):
            if msg['id'] == sent_message_id:
                continue
            headers  = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
            from_hdr = headers.get('From', '')
            # Accept replies from our own account
            if 'me' in from_hdr or '@gmail.com' in from_hdr.lower():
                body = _extract_body(msg['payload'])
                key = parse_reply(body, valid_keys)
                if key:
                    return key

        time.sleep(poll_interval)

    return None


def send_captcha_intervention(gmail_service, to: str, booking_id: str,
                               site_label: str) -> Optional[dict]:
    """Send a CAPTCHA intervention email and return the sent message info."""
    from engine.gmail import send_message

    situation = (
        f"A CAPTCHA was detected while attempting to book: {site_label}\n"
        f"Booking ID: {booking_id}\n\n"
        "The agent cannot proceed automatically. Please choose:"
    )
    options = [
        {"key": "A", "label": "Skip this attempt and mark as failed"},
        {"key": "B", "label": "I will complete the form manually — mark as done"},
        {"key": "C", "label": "Retry the booking attempt"},
    ]
    body = build_intervention_email(situation, options)
    return send_message(
        gmail_service,
        to=to,
        subject=f"[Jig] CAPTCHA — action required ({booking_id})",
        body=body,
    )


def send_no_slots_intervention(gmail_service, to: str, booking_id: str,
                                target_date: str, site_label: str) -> Optional[dict]:
    """Send an intervention email when no suitable fallback slot is found."""
    from engine.gmail import send_message

    situation = (
        f"No available slots were found for {target_date} at {site_label}.\n"
        f"Booking ID: {booking_id}\n\n"
        "The rejection email listed no viable times on your target date."
    )
    options = [
        {"key": "A", "label": "Mark as failed and stop"},
        {"key": "B", "label": "I will rebook manually — mark as done"},
    ]
    body = build_intervention_email(situation, options)
    return send_message(
        gmail_service,
        to=to,
        subject=f"[Jig] No slots available — {target_date} ({booking_id})",
        body=body,
    )
