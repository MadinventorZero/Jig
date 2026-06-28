"""Schedule management — fire times, launchd (macOS) and Task Scheduler (Windows)."""
import platform
import plistlib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytz

_OS            = platform.system()
PST            = pytz.timezone("America/Los_Angeles")
ADVANCE_DAYS   = 14
FIRE_HOUR      = 9   # 9am PST — confirmed from BH staff email
PLIST_PREFIX   = "com.madinventor.booking-agent"
LAUNCHD_DIR    = Path.home() / "Library" / "LaunchAgents"
ROOT           = Path(__file__).parent.parent


def compute_fire_datetime(target_date_str: str) -> datetime:
    """Return the fire datetime: 14 days before target at 9:00am PST."""
    from dateutil.parser import parse as parse_date
    target   = parse_date(target_date_str).date()
    fire_day = target - timedelta(days=ADVANCE_DAYS)
    return PST.localize(datetime(fire_day.year, fire_day.month, fire_day.day, FIRE_HOUR, 0, 0))


def fire_datetime_iso(target_date_str: str) -> str:
    return compute_fire_datetime(target_date_str).isoformat()


def write_launchd_plist(schedule: dict) -> Path:
    """Write a launchd plist for the schedule and return its path."""
    label     = f"{PLIST_PREFIX}.{schedule['schedule_id']}"
    plist_path = LAUNCHD_DIR / f"{label}.plist"
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)

    fire_dt = datetime.fromisoformat(schedule['fire_at'])

    plist = {
        'Label': label,
        'ProgramArguments': [
            str(ROOT / '.venv' / 'bin' / 'python'),
            str(ROOT / 'run_booking.py'),
            '--schedule-id', schedule['schedule_id'],
        ],
        'StartCalendarInterval': {
            'Year':   fire_dt.year,
            'Month':  fire_dt.month,
            'Day':    fire_dt.day,
            'Hour':   fire_dt.hour,
            'Minute': fire_dt.minute,
        },
        'StandardOutPath': str(ROOT / 'data' / 'logs' / f"{schedule['schedule_id']}-out.log"),
        'StandardErrorPath': str(ROOT / 'data' / 'logs' / f"{schedule['schedule_id']}-err.log"),
        'RunAtLoad': False,
        'EnvironmentVariables': {
            'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin',
        },
    }

    with plist_path.open('wb') as f:
        plistlib.dump(plist, f)

    return plist_path


def load_plist(schedule_id: str) -> bool:
    label     = f"{PLIST_PREFIX}.{schedule_id}"
    plist_path = LAUNCHD_DIR / f"{label}.plist"
    if not plist_path.exists():
        return False
    result = subprocess.run(['launchctl', 'load', str(plist_path)], capture_output=True)
    return result.returncode == 0


def unload_plist(schedule_id: str) -> bool:
    label     = f"{PLIST_PREFIX}.{schedule_id}"
    plist_path = LAUNCHD_DIR / f"{label}.plist"
    if not plist_path.exists():
        return True
    result = subprocess.run(['launchctl', 'unload', str(plist_path)], capture_output=True)
    return result.returncode == 0


def remove_plist(schedule_id: str) -> None:
    unload_plist(schedule_id)
    label     = f"{PLIST_PREFIX}.{schedule_id}"
    plist_path = LAUNCHD_DIR / f"{label}.plist"
    plist_path.unlink(missing_ok=True)


def enable_schedule(schedule: dict) -> dict:
    plist_path = write_launchd_plist(schedule)
    ok = load_plist(schedule['schedule_id'])
    return {"ok": ok, "plist_path": str(plist_path), "launchd_label": f"{PLIST_PREFIX}.{schedule['schedule_id']}"}


def disable_schedule(schedule_id: str) -> dict:
    ok = unload_plist(schedule_id)
    return {"ok": ok}


# ── v3 generalized scheduling ────────────────────────────────────────────────

def write_flow_plist(schedule_id: str, flow_id: str, profile_id: str,
                     trigger: dict) -> Path:
    """
    Write a launchd plist for any v3 flow schedule.

    trigger examples:
      {"type": "one-shot", "fire_at": "2026-06-21T09:00:00-07:00"}
      {"type": "cron", "hour": 9, "minute": 0}            # daily
      {"type": "cron", "weekday": 1, "hour": 8}           # every Monday
    """
    label      = f"{PLIST_PREFIX}.flow.{schedule_id}"
    plist_path = LAUNCHD_DIR / f"{label}.plist"
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)

    runner = ROOT / ".venv" / "bin" / "python"
    prog   = [
        str(runner), str(ROOT / "run_flow.py"),
        "--flow-id",    flow_id,
        "--profile-id", profile_id,
    ]

    cal: dict = {}
    if trigger["type"] == "one-shot":
        dt = datetime.fromisoformat(trigger["fire_at"])
        cal = {"Year": dt.year, "Month": dt.month, "Day": dt.day,
               "Hour": dt.hour, "Minute": dt.minute}
    elif trigger["type"] == "cron":
        cal = {k: trigger[k] for k in ("Month", "Day", "Weekday", "Hour", "Minute")
               if k in trigger}

    plist = {
        "Label":                   label,
        "ProgramArguments":        prog,
        "StartCalendarInterval":   cal,
        "StandardOutPath":         str(ROOT / "data" / "logs" / f"{schedule_id}-out.log"),
        "StandardErrorPath":       str(ROOT / "data" / "logs" / f"{schedule_id}-err.log"),
        "RunAtLoad":               False,
        "EnvironmentVariables":    {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
    }

    with plist_path.open("wb") as f:
        plistlib.dump(plist, f)
    return plist_path


def write_windows_task(schedule_id: str, flow_id: str, profile_id: str,
                       trigger: dict) -> str:
    """
    Register a per-user Task Scheduler task via schtasks.exe.
    Returns the task name string.
    """
    task_name = f"MadAutomation\\{schedule_id}"
    runner    = str(ROOT / ".venv" / "Scripts" / "python.exe")
    cmd_args  = f'"{runner}" "{ROOT / "run_flow.py"}" --flow-id {flow_id} --profile-id {profile_id}'

    sched: list[str] = []
    if trigger["type"] == "one-shot":
        dt    = datetime.fromisoformat(trigger["fire_at"])
        sched = ["/SC", "ONCE",
                 "/SD", dt.strftime("%m/%d/%Y"),
                 "/ST", dt.strftime("%H:%M")]
    elif trigger["type"] == "cron":
        hour   = trigger.get("hour", 9)
        minute = trigger.get("minute", 0)
        if "weekday" in trigger:
            days = ["MON","TUE","WED","THU","FRI","SAT","SUN"]
            sched = ["/SC", "WEEKLY", "/D", days[trigger["weekday"] % 7],
                     "/ST", f"{hour:02d}:{minute:02d}"]
        else:
            sched = ["/SC", "DAILY", "/ST", f"{hour:02d}:{minute:02d}"]

    import os
    subprocess.run(
        ["schtasks", "/Create", "/F",
         "/TN", task_name,
         "/TR", cmd_args,
         "/RU", os.environ.get("USERNAME", ""),
         *sched],
        check=True, capture_output=True,
    )
    return task_name


def schedule_flow(schedule_id: str, flow_id: str, profile_id: str,
                  trigger: dict) -> dict:
    """Platform-dispatching scheduler for v3 flows."""
    if _OS == "Darwin":
        path  = write_flow_plist(schedule_id, flow_id, profile_id, trigger)
        ok    = load_plist(schedule_id)   # reuse existing load helper via label override
        # load_plist uses the v2 label pattern; call launchctl directly for v3 label
        label = f"{PLIST_PREFIX}.flow.{schedule_id}"
        result = subprocess.run(["launchctl", "load", str(path)], capture_output=True)
        return {"ok": result.returncode == 0, "label": label, "path": str(path)}
    if _OS == "Windows":
        task = write_windows_task(schedule_id, flow_id, profile_id, trigger)
        return {"ok": True, "task_name": task}
    return {"ok": False, "error": f"Scheduling not supported on {_OS}"}


def unschedule_flow(schedule_id: str) -> dict:
    """Remove a v3 flow schedule on the current platform."""
    if _OS == "Darwin":
        label      = f"{PLIST_PREFIX}.flow.{schedule_id}"
        plist_path = LAUNCHD_DIR / f"{label}.plist"
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        plist_path.unlink(missing_ok=True)
        return {"ok": True}
    if _OS == "Windows":
        task = f"MadAutomation\\{schedule_id}"
        result = subprocess.run(["schtasks", "/Delete", "/F", "/TN", task],
                                capture_output=True)
        return {"ok": result.returncode == 0}
    return {"ok": False, "error": f"Unscheduling not supported on {_OS}"}
