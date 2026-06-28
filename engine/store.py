"""JSON-based persistence. One file per entity under data/{profiles,bookings,schedules}/."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DATA_DIR      = Path(__file__).parent.parent / "data"
PROFILES_DIR  = DATA_DIR / "profiles"
BOOKINGS_DIR  = DATA_DIR / "bookings"
SCHEDULES_DIR = DATA_DIR / "schedules"
LOGS_DIR      = DATA_DIR / "logs"


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Profiles ─────────────────────────────────────────────────────────────────

def list_profiles() -> list[dict]:
    if not PROFILES_DIR.exists():
        return []
    return sorted(
        [json.loads(f.read_text()) for f in PROFILES_DIR.glob("*.json")],
        key=lambda p: p.get("created_at", ""),
        reverse=True,
    )


def get_profile(profile_id: str) -> Optional[dict]:
    return _read(PROFILES_DIR / f"{profile_id}.json")


def save_profile(data: dict) -> str:
    if not data.get("profile_id"):
        data["profile_id"] = new_id()
    now = now_iso()
    data.setdefault("created_at", now)
    data["updated_at"] = now
    _write(PROFILES_DIR / f"{data['profile_id']}.json", data)
    return data["profile_id"]


def delete_profile(profile_id: str) -> None:
    path = PROFILES_DIR / f"{profile_id}.json"
    path.unlink(missing_ok=True)


# ── Bookings ──────────────────────────────────────────────────────────────────

def list_bookings() -> list[dict]:
    if not BOOKINGS_DIR.exists():
        return []
    return sorted(
        [json.loads(f.read_text()) for f in BOOKINGS_DIR.glob("*.json")],
        key=lambda b: b.get("created_at", ""),
        reverse=True,
    )


def get_booking(booking_id: str) -> Optional[dict]:
    return _read(BOOKINGS_DIR / f"{booking_id}.json")


def save_booking(data: dict) -> str:
    if not data.get("booking_id"):
        data["booking_id"] = new_id()
    now = now_iso()
    data.setdefault("created_at", now)
    data["updated_at"] = now
    data.setdefault("attempts", [])
    _write(BOOKINGS_DIR / f"{data['booking_id']}.json", data)
    return data["booking_id"]


def append_attempt(booking_id: str, attempt: dict) -> None:
    booking = get_booking(booking_id)
    if not booking:
        return
    booking.setdefault("attempts", []).append(attempt)
    booking["updated_at"] = now_iso()
    _write(BOOKINGS_DIR / f"{booking_id}.json", booking)


def update_booking_status(booking_id: str, status: str, **kwargs) -> None:
    booking = get_booking(booking_id)
    if not booking:
        return
    booking["status"] = status
    booking.update(kwargs)
    booking["updated_at"] = now_iso()
    _write(BOOKINGS_DIR / f"{booking_id}.json", booking)


# ── Schedules ─────────────────────────────────────────────────────────────────

def list_schedules() -> list[dict]:
    if not SCHEDULES_DIR.exists():
        return []
    return sorted(
        [json.loads(f.read_text()) for f in SCHEDULES_DIR.glob("*.json")],
        key=lambda s: s.get("fire_at", ""),
    )


def get_schedule(schedule_id: str) -> Optional[dict]:
    return _read(SCHEDULES_DIR / f"{schedule_id}.json")


def save_schedule(data: dict) -> str:
    if not data.get("schedule_id"):
        data["schedule_id"] = new_id()
    now = now_iso()
    data.setdefault("created_at", now)
    _write(SCHEDULES_DIR / f"{data['schedule_id']}.json", data)
    return data["schedule_id"]


def delete_schedule(schedule_id: str) -> None:
    path = SCHEDULES_DIR / f"{schedule_id}.json"
    path.unlink(missing_ok=True)


# ── Step results (trial + production run tracking) ───────────────────────────

def set_step_result(booking_id: str, step_id: str, action: str, detail: str = "") -> None:
    booking = get_booking(booking_id)
    if not booking:
        return
    booking.setdefault("step_results", {})[step_id] = {"action": action, "detail": detail}
    booking["updated_at"] = now_iso()
    _write(BOOKINGS_DIR / f"{booking_id}.json", booking)


# ── Halt / resume (trial run pause points) ───────────────────────────────────

def set_halt_state(booking_id: str, step_id: str, description: str,
                   data: dict = None) -> None:
    booking = get_booking(booking_id)
    if not booking:
        return
    booking["status"]       = f"halted_at_{step_id}"
    booking["halt_data"]    = {"step": step_id, "description": description,
                               "data": data or {}, "ts": now_iso()}
    booking["resume_action"] = None
    booking["updated_at"]   = now_iso()
    _write(BOOKINGS_DIR / f"{booking_id}.json", booking)


def signal_resume(booking_id: str, action: str) -> None:
    """action: 'continue' | 'abort'"""
    booking = get_booking(booking_id)
    if not booking:
        return
    booking["resume_action"] = action
    booking["updated_at"]    = now_iso()
    _write(BOOKINGS_DIR / f"{booking_id}.json", booking)


def get_resume_action(booking_id: str) -> Optional[str]:
    booking = get_booking(booking_id)
    return booking.get("resume_action") if booking else None


def clear_halt_state(booking_id: str) -> None:
    booking = get_booking(booking_id)
    if not booking:
        return
    booking["halt_data"]    = None
    booking["resume_action"] = None
    booking["updated_at"]   = now_iso()
    _write(BOOKINGS_DIR / f"{booking_id}.json", booking)


# ── Logs ──────────────────────────────────────────────────────────────────────

def append_log(booking_id: str, level: str, message: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({"ts": now_iso(), "level": level, "msg": message})
    log_path = LOGS_DIR / f"{booking_id}.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry + "\n")


def get_logs(booking_id: str) -> list[dict]:
    log_path = LOGS_DIR / f"{booking_id}.jsonl"
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
