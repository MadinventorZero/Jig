"""Notification actions — email and OS system notification (macOS + Windows)."""
import platform
import subprocess

from engine.context import RunContext

_OS = platform.system()


async def handle_notify_email(ctx: RunContext, params: dict) -> dict:
    from engine import gmail as gmail_mod
    svc  = gmail_mod.get_service()
    sent = gmail_mod.send_message(
        svc,
        to=params["to"],
        subject=params["subject"],
        body=params.get("body", ""),
    )
    return {"ok": True, "message_id": sent.get("id"), "choice": "ok"}


async def handle_notify_system(ctx: RunContext, params: dict) -> dict:
    title = params.get("title", "Mad Automation Platform")
    body  = params.get("body", "")
    if _OS == "Darwin":
        return _notify_mac(title, body)
    if _OS == "Windows":
        return _notify_windows(title, body)
    return {"ok": False, "error": f"System notifications not supported on {_OS}", "choice": "error"}


def _notify_mac(title: str, body: str) -> dict:
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{body}" with title "{title}"'],
            check=True, capture_output=True,
        )
        return {"ok": True, "choice": "ok"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "choice": "error"}


def _notify_windows(title: str, body: str) -> dict:
    try:
        from winotify import Notification, audio
        toast = Notification(
            app_id="Mad Automation Platform",
            title=title,
            msg=body,
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        return {"ok": True, "choice": "ok"}
    except ImportError:
        return {"ok": False, "error": "winotify not installed", "choice": "error"}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "choice": "error"}


def register(registry) -> None:
    registry.register("notify_email",  handle_notify_email,
                       "Send a notification email via Gmail")
    registry.register("notify_system", handle_notify_system,
                       "OS system notification (macOS + Windows)")
