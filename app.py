#!/usr/bin/env python3
"""Jig — pywebview entry point and Python API bridge."""
from pathlib import Path

import webview

import engine.store as store
from engine.scheduler import compute_fire_datetime, fire_datetime_iso
from engine.scheduler import enable_schedule, disable_schedule, remove_plist
from audit.classifier import list_sites
import engine.gmail as gmail

ROOT     = Path(__file__).parent
UI_INDEX = ROOT / "ui" / "index.html"


def _serial(obj):
    """Recursively make an object JSON-safe."""
    if hasattr(obj, '__dataclass_fields__'):
        return {k: _serial(v) for k, v in vars(obj).items()}
    if isinstance(obj, list):
        return [_serial(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serial(v) for k, v in obj.items()}
    return obj


class Api:
    """All public methods are callable from JS via window.pywebview.api.<method>()."""

    # ── Profiles ──────────────────────────────────────────────────────────────

    def list_profiles(self):
        return store.list_profiles()

    def get_profile(self, profile_id: str):
        return store.get_profile(profile_id)

    def save_profile(self, data: dict):
        profile_id = store.save_profile(data)
        return {"ok": True, "profile_id": profile_id}

    def delete_profile(self, profile_id: str):
        store.delete_profile(profile_id)
        return {"ok": True}

    def new_profile_id(self):
        return store.new_id()

    # ── Bookings ──────────────────────────────────────────────────────────────

    def list_bookings(self):
        return store.list_bookings()

    def get_booking(self, booking_id: str):
        return store.get_booking(booking_id)

    def get_booking_logs(self, booking_id: str):
        return store.get_logs(booking_id)

    def trigger_booking(self, profile_id: str, site_id: str, target_date: str):
        """Manually fire a production booking run immediately."""
        import subprocess
        booking_id = store.save_booking({
            "profile_id":   profile_id,
            "site_id":      site_id,
            "target_date":  target_date,
            "status":       "idle",
            "step_results": {},
            "trial":        False,
        })
        proc = subprocess.Popen(
            [str(ROOT / '.venv' / 'bin' / 'python'), str(ROOT / 'run_booking.py'),
             '--booking-id', booking_id],
            cwd=str(ROOT),
        )
        store.update_booking_status(booking_id, "idle", pid=proc.pid)
        return {"ok": True, "booking_id": booking_id}

    def trigger_trial_run(self, profile_id: str, site_id: str,
                          target_date: str, trial_config: dict):
        """Start a trial run with per-step action configuration."""
        import subprocess, json
        booking_id = store.save_booking({
            "profile_id":   profile_id,
            "site_id":      site_id,
            "target_date":  target_date,
            "status":       "idle",
            "step_results": {},
            "trial":        True,
            "trial_config": trial_config,
        })
        proc = subprocess.Popen(
            [str(ROOT / '.venv' / 'bin' / 'python'), str(ROOT / 'run_booking.py'),
             '--booking-id', booking_id,
             '--trial-config', json.dumps(trial_config)],
            cwd=str(ROOT),
        )
        store.update_booking_status(booking_id, "idle", pid=proc.pid)
        return {"ok": True, "booking_id": booking_id}

    def cancel_booking(self, booking_id: str):
        """Kill the subprocess for an active booking and mark it cancelled."""
        import os, signal
        from engine.models import BookingStatus
        booking = store.get_booking(booking_id)
        if not booking:
            return {"ok": False, "error": "Booking not found"}
        pid = booking.get('pid')
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # already exited
            except Exception as e:
                return {"ok": False, "error": str(e)}
        store.update_booking_status(booking_id, BookingStatus.CANCELLED)
        return {"ok": True}

    def resume_booking(self, booking_id: str, action: str):
        """Signal a halted trial run to continue or abort. action: 'continue'|'abort'"""
        if action not in ('continue', 'abort'):
            return {"ok": False, "error": "action must be 'continue' or 'abort'"}
        store.signal_resume(booking_id, action)
        return {"ok": True}

    # ── Schedules ─────────────────────────────────────────────────────────────

    def list_schedules(self):
        return store.list_schedules()

    def get_schedule(self, schedule_id: str):
        return store.get_schedule(schedule_id)

    def preview_fire_time(self, target_date: str):
        """Return the computed fire datetime for a given target date."""
        try:
            dt = compute_fire_datetime(target_date)
            return {"ok": True, "fire_at": dt.isoformat(), "display": dt.strftime("%b %-d, %Y at %-I:%M %p %Z")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def save_schedule(self, data: dict):
        if data.get('target_date') and not data.get('fire_at'):
            data['fire_at'] = fire_datetime_iso(data['target_date'])
        schedule_id = store.save_schedule(data)
        return {"ok": True, "schedule_id": schedule_id}

    def delete_schedule(self, schedule_id: str):
        remove_plist(schedule_id)
        store.delete_schedule(schedule_id)
        return {"ok": True}

    def toggle_schedule(self, schedule_id: str, enabled: bool):
        schedule = store.get_schedule(schedule_id)
        if not schedule:
            return {"ok": False, "error": "Schedule not found"}
        schedule['enabled'] = enabled
        if enabled:
            result = enable_schedule(schedule)
            if result.get('ok'):
                schedule['launchd_label'] = result.get('launchd_label')
        else:
            result = disable_schedule(schedule_id)
        store.save_schedule(schedule)
        return {"ok": result.get('ok', False)}

    # ── Trial run support ─────────────────────────────────────────────────────

    def get_trial_steps(self):
        from engine.trial import STEPS
        return STEPS

    def get_default_trial_config(self):
        from engine.trial import DEFAULT_TRIAL_CONFIG
        return DEFAULT_TRIAL_CONFIG

    def get_sample_rejection_email(self):
        from engine.trial import SAMPLE_REJECTION_EMAIL
        return SAMPLE_REJECTION_EMAIL

    # ── Sources / Sites ───────────────────────────────────────────────────────

    def list_sources(self):
        return list_sites()

    def get_source_schema(self, site_id: str):
        if site_id == "beverly_hills":
            from sources.beverly_hills import get_config_schema
            return get_config_schema()
        return []

    # ── Gmail / Settings ──────────────────────────────────────────────────────

    def get_gmail_status(self):
        configured    = gmail.is_configured()
        authenticated = gmail.is_authenticated()
        email_addr    = None
        if authenticated:
            try:
                svc        = gmail.get_service()
                email_addr = gmail.get_authenticated_email(svc)
            except Exception:
                authenticated = False
        return {
            "configured":    configured,
            "authenticated": authenticated,
            "email":         email_addr,
            "credentials_path": str(gmail.CREDENTIALS_FILE),
        }

    def start_gmail_oauth(self):
        try:
            svc   = gmail.get_service()
            email = gmail.get_authenticated_email(svc)
            return {"ok": True, "email": email}
        except FileNotFoundError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def revoke_gmail(self):
        gmail.revoke_token()
        return {"ok": True}

    # ── V3 Flows ──────────────────────────────────────────────────────────────

    def list_flows(self):
        import yaml
        from engine.db import Store
        flows_dir = ROOT / "sources" / "flows"
        db = Store()
        result = []
        yamls = sorted(flows_dir.glob("*.yaml")) if flows_dir.exists() else []
        for path in yamls:
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                flow_id = path.stem
                runs = db.list_runs(flow_id=flow_id, limit=1)
                last = runs[0] if runs else None
                result.append({
                    "id":              flow_id,
                    "name":            raw.get("name", flow_id),
                    "version":         raw.get("version", 1),
                    "step_count":      len(raw.get("steps", [])),
                    "last_run_status": last["status"] if last else None,
                    "last_run_at":     last["started_at"] if last else None,
                    "last_run_id":     last["run_id"] if last else None,
                })
            except Exception as e:
                result.append({"id": path.stem, "error": str(e)})
        return result

    def get_flow(self, flow_id: str):
        import yaml
        from engine.graph import FlowGraphBuilder
        from engine.v3_models import FlowDef, StepDef, TriggerDef
        flows_dir = ROOT / "sources" / "flows"
        candidates = [
            flows_dir / f"{flow_id}.yaml",
            flows_dir / f"booking_{flow_id}.yaml",
        ]
        path = next((c for c in candidates if c.exists()), None)
        if not path:
            return {"error": f"Flow {flow_id!r} not found"}
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        trigger = TriggerDef(
            type=raw.get("trigger", {}).get("type", "manual"),
            params=raw.get("trigger", {}).get("params", {}),
        )
        steps = []
        for s in raw.get("steps", []):
            steps.append(StepDef(
                step_id=s["step_id"], type=s["type"],
                params=s.get("params", {}), mode=s.get("mode", "dom"),
                max_retries=s.get("max_retries", 0),
                retry_delay_seconds=s.get("retry_delay_seconds", 1.0),
                idempotent=s.get("idempotent", True),
                on_choice=s.get("on_choice", {}),
                on_timeout=s.get("on_timeout"),
                on_error=s.get("on_error"),
                on_error_mode=s.get("on_error_mode", "blocking"),
                enabled=s.get("enabled", True),
                block_ref=s.get("block"),
            ))
        flow = FlowDef(
            id=raw["id"], name=raw["name"], version=raw.get("version", 1),
            trigger=trigger, steps=steps,
            context=raw.get("context", {}),
            concurrency=raw.get("concurrency", "serial"),
            on_error=raw.get("on_error"),
        )
        mermaid = FlowGraphBuilder(flow).to_mermaid()
        return {
            "id":       raw["id"],
            "name":     raw["name"],
            "version":  raw.get("version", 1),
            "steps":    [{"step_id": s.step_id, "type": s.type, "params": s.params,
                          "on_choice": s.on_choice, "on_timeout": s.on_timeout,
                          "on_error": s.on_error, "enabled": s.enabled}
                         for s in steps],
            "mermaid":  mermaid,
            "raw":      raw,
        }

    def run_flow(self, flow_id: str, profile_id: str, show_browser: bool = False):
        import subprocess, uuid, platform as _plat
        run_id = str(uuid.uuid4())
        py = "Scripts/python.exe" if _plat.system() == "Windows" else "bin/python"
        python = str(ROOT / ".venv" / py)
        cmd = [python, str(ROOT / "run_flow.py"),
               "--flow-id", flow_id, "--profile-id", profile_id, "--run-id", run_id]
        if show_browser:
            cmd.append("--show-browser")
        subprocess.Popen(cmd, cwd=str(ROOT))
        return {"ok": True, "run_id": run_id}

    def validate_flow(self, flow_id: str, profile_id: str = None):
        import subprocess, platform as _plat
        py = "Scripts/python.exe" if _plat.system() == "Windows" else "bin/python"
        python = str(ROOT / ".venv" / py)
        cmd = [python, str(ROOT / "run_flow.py"), "--flow-id", flow_id, "--validate"]
        if profile_id:
            cmd.extend(["--profile-id", profile_id])
        try:
            r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=30)
            return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "Validation timed out after 30s"}
        except Exception as e:
            return {"ok": False, "output": str(e)}

    def get_action_contracts(self):
        """Return declared input/output schemas for all built-in action types."""
        from engine.contracts import BUILTIN_CONTRACTS
        return {name: c.to_dict() for name, c in BUILTIN_CONTRACTS.items()}

    def list_blocks(self):
        """Return all block definitions from sources/blocks/."""
        import yaml
        blocks_dir = ROOT / "sources" / "blocks"
        result = []
        for path in sorted(blocks_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                result.append({
                    "id":          raw.get("id", path.stem),
                    "name":        raw.get("name", path.stem),
                    "description": raw.get("description", ""),
                    "version":     raw.get("version", 1),
                    "params":      raw.get("params", {}),
                    "step_count":  len(raw.get("steps", [])),
                    "steps":       [{"step_id": s.get("step_id"), "type": s.get("type")}
                                    for s in raw.get("steps", [])],
                })
            except Exception as e:
                result.append({"id": path.stem, "error": str(e)})
        return result

    def save_block(self, data: dict):
        """Create or update a block YAML in sources/blocks/. Preserves existing steps."""
        import re, yaml
        block_id = (data.get("id") or "").strip()
        if not block_id or not re.match(r'^[a-z][a-z0-9_]*$', block_id):
            return {"ok": False, "error": "id must be lowercase letters, digits, underscores; start with a letter"}
        name = (data.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "name is required"}

        blocks_dir = ROOT / "sources" / "blocks"
        blocks_dir.mkdir(parents=True, exist_ok=True)
        path = blocks_dir / f"{block_id}.yaml"

        existing = {}
        if path.exists():
            try:
                existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                pass

        def _to_schema_dict(fields):
            result = {}
            for f in (fields or []):
                result[f["name"]] = {
                    "type":     f.get("type", "str"),
                    "required": bool(f.get("required", True)),
                }
            return result

        doc = {
            "id":          block_id,
            "name":        name,
            "version":     existing.get("version", 1),
            "description": data.get("description", ""),
        }
        if data.get("input_schema"):
            doc["input_schema"] = _to_schema_dict(data["input_schema"])
        if data.get("output_schema"):
            doc["output_schema"] = _to_schema_dict(data["output_schema"])
        doc["params"] = existing.get("params", {})
        doc["steps"]  = existing.get("steps", [])

        path.write_text(
            yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return {"ok": True, "block_id": block_id}

    def search_palette(self, query: str = "", mode: str = "all"):
        """Return all palette items. Client does the filtering and ranking."""
        import yaml
        from engine.db import Store

        items = []

        # ── Step types ────────────────────────────────────────────────────────
        STEP_GROUPS = {
            "browser": ["browser_navigate", "browser_click", "browser_fill",
                        "browser_submit", "browser_screenshot", "browser_extract_text",
                        "browser_wait", "browser_select"],
            "llm":     ["llm_decide", "llm_extract", "claude_complete"],
            "email":   ["gmail_watch", "gmail_send", "gmail_reply"],
            "vision":  ["vision_describe", "vision_find_element"],
            "http":    ["http_request"],
            "script":  ["script_run"],
            "storage": ["storage_get", "storage_set"],
            "notify":  ["notify"],
            "control": ["human_pause", "delay", "block", "condition",
                        "set_variable", "loop", "skip_to"],
        }
        for group, types in STEP_GROUPS.items():
            for st in types:
                items.append({
                    "category": "step",
                    "id":       st,
                    "label":    st.replace("_", " "),
                    "subtitle": group,
                    "action":   {"type": "insert_step", "step_type": st},
                })

        # ── Blocks ────────────────────────────────────────────────────────────
        blocks_dir = ROOT / "sources" / "blocks"
        for path in sorted(blocks_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                block_id = raw.get("id", path.stem)
                desc = raw.get("description", "")
                step_count = len(raw.get("steps", []))
                has_in  = bool(raw.get("input_schema"))
                has_out = bool(raw.get("output_schema"))
                if has_in and has_out:
                    compat = "green"
                elif has_in or has_out:
                    compat = "yellow"
                else:
                    compat = "none"
                items.append({
                    "category": "block",
                    "id":       block_id,
                    "label":    raw.get("name", path.stem),
                    "subtitle": desc or f"{step_count} steps",
                    "compat":   compat,
                    "action":   {"type": "insert_block", "block_id": block_id},
                })
            except Exception:
                pass

        # ── Flows ─────────────────────────────────────────────────────────────
        for f in self.list_flows():
            if "error" not in f:
                items.append({
                    "category": "flow",
                    "id":       f["id"],
                    "label":    f["name"],
                    "subtitle": f"v{f.get('version', 1)} · {f.get('step_count', 0)} steps",
                    "action":   {"type": "navigate_flow", "flow_id": f["id"]},
                })

        # ── History (last 10 runs) ─────────────────────────────────────────────
        for r in Store().list_runs(limit=10):
            ts = (r.get("started_at") or "")[:16]
            items.append({
                "category": "history",
                "id":       r["run_id"],
                "label":    r.get("flow_id", "unknown"),
                "subtitle": f"{ts} · {r.get('status', '?')}",
                "status":   r.get("status"),
                "action":   {"type": "open_run", "run_id": r["run_id"],
                              "flow_id": r.get("flow_id")},
            })

        # ── Commands ──────────────────────────────────────────────────────────
        COMMANDS = [
            {"id": "nav_flows",     "label": "Open Flows",     "subtitle": "Navigate · Flows view",
             "action": {"type": "navigate", "view": "flows"}},
            {"id": "nav_blocks",    "label": "Block Library",  "subtitle": "Browse all blocks",
             "action": {"type": "navigate", "view": "blocks"}},
            {"id": "nav_schedules", "label": "Open Schedules", "subtitle": "Navigate · Schedules view",
             "action": {"type": "navigate", "view": "schedules"}},
            {"id": "nav_profiles",  "label": "Open Profiles",  "subtitle": "Navigate · Profiles view",
             "action": {"type": "navigate", "view": "profiles"}},
            {"id": "nav_dashboard", "label": "Open Dashboard", "subtitle": "Navigate · Dashboard view",
             "action": {"type": "navigate", "view": "dashboard"}},
            {"id": "mode_editor",   "label": "Editor Mode",    "subtitle": "Switch workspace to Editor",
             "action": {"type": "set_mode", "mode": "editor"}},
            {"id": "mode_run",      "label": "Run Mode",       "subtitle": "Switch workspace to Run",
             "action": {"type": "set_mode", "mode": "run"}},
            {"id": "mode_history",  "label": "History Mode",   "subtitle": "Switch workspace to History",
             "action": {"type": "set_mode", "mode": "history"}},
            {"id": "cmd_validate",  "label": "Validate Flow",  "subtitle": "Validate the current flow",
             "action": {"type": "command", "cmd": "validate"}},
            {"id": "nav_planner",   "label": "Process Planner", "subtitle": "Record a new automation flow",
             "action": {"type": "navigate", "view": "planner"}},
        ]
        items.extend({"category": "command", **c} for c in COMMANDS)

        return items

    def get_flow_violations(self, flow_id: str):
        """Run contract chain validation in-process; return structured violations."""
        import yaml
        from engine.registry import ActionRegistry
        from engine.block_registry import BlockRegistry
        from engine.contracts import ChainValidator, BUILTIN_CONTRACTS
        from engine.v3_models import FlowDef, StepDef, TriggerDef
        from engine.actions import (
            browser, email as _email, flow_control, notification,
            http, file as _file, script, storage, llm, block as _block,
        )

        flows_dir  = ROOT / "sources" / "flows"
        candidates = [flows_dir / f"{flow_id}.yaml",
                      flows_dir / f"booking_{flow_id}.yaml"]
        path = next((c for c in candidates if c.exists()), None)
        if not path:
            return {"ok": False, "error": f"Flow {flow_id!r} not found",
                    "violations": [], "error_count": 0, "warning_count": 0}

        try:
            raw     = yaml.safe_load(path.read_text(encoding="utf-8"))
            trigger = TriggerDef(
                type=raw.get("trigger", {}).get("type", "manual"),
                params=raw.get("trigger", {}).get("params", {}),
            )
            steps = [StepDef(
                step_id=s["step_id"], type=s["type"],
                params=s.get("params", {}), mode=s.get("mode", "dom"),
                max_retries=s.get("max_retries", 0),
                retry_delay_seconds=s.get("retry_delay_seconds", 1.0),
                idempotent=s.get("idempotent", True),
                on_choice=s.get("on_choice", {}), on_timeout=s.get("on_timeout"),
                on_error=s.get("on_error"),
                on_error_mode=s.get("on_error_mode", "blocking"),
                enabled=s.get("enabled", True),
                block_ref=s.get("block"),
            ) for s in raw.get("steps", [])]
            flow = FlowDef(
                id=raw["id"], name=raw["name"], version=raw.get("version", 1),
                trigger=trigger, steps=steps,
                context=raw.get("context", {}),
                concurrency=raw.get("concurrency", "serial"),
                on_error=raw.get("on_error"),
            )

            registry = ActionRegistry()
            for mod in [browser, _email, flow_control, notification, http,
                        _file, script, storage, llm, _block]:
                mod.register(registry)
            registry.apply_contracts(BUILTIN_CONTRACTS)

            violations = ChainValidator(registry, BlockRegistry()).validate(flow)
            return {
                "ok":            not any(v.severity == "error" for v in violations),
                "violations":    [v.to_dict() for v in violations],
                "error_count":   sum(1 for v in violations if v.severity == "error"),
                "warning_count": sum(1 for v in violations if v.severity == "warning"),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "violations": [],
                    "error_count": 1, "warning_count": 0}

    def cancel_run(self, run_id: str):
        from engine.db import Store
        Store().kv_set(f"cancel:{run_id}", True)
        return {"ok": True}

    def resume_run(self, run_id: str, action: str):
        if action not in ("continue", "abort"):
            return {"ok": False, "error": "action must be 'continue' or 'abort'"}
        from engine.db import Store
        Store().kv_set(f"resume:{run_id}", {"action": action})
        return {"ok": True}

    def start_debug_run(self, flow_id: str, profile_id: str):
        import subprocess, uuid, platform as _plat
        run_id = str(uuid.uuid4())
        py = "Scripts/python.exe" if _plat.system() == "Windows" else "bin/python"
        python = str(ROOT / ".venv" / py)
        from engine.db import Store
        Store().kv_set(f"debug:{run_id}", True)
        cmd = [python, str(ROOT / "run_flow.py"),
               "--flow-id", flow_id, "--profile-id", profile_id, "--run-id", run_id]
        subprocess.Popen(cmd, cwd=str(ROOT))
        return {"ok": True, "run_id": run_id}

    def debug_continue(self, run_id: str):
        from engine.db import Store
        Store().kv_set(f"debug_continue:{run_id}", "continue")
        return {"ok": True}

    def debug_skip(self, run_id: str):
        from engine.db import Store
        Store().kv_set(f"debug_continue:{run_id}", "skip")
        return {"ok": True}

    # ── V3 Run History ────────────────────────────────────────────────────────

    def list_runs(self, flow_id: str = None, limit: int = 50):
        from engine.db import Store
        db = Store()
        runs = db.list_runs(flow_id=flow_id, limit=int(limit))
        result = []
        for r in runs:
            s = db.get_run_summary(r["run_id"]) or {}
            result.append({**r, **s})
        return result

    def get_run(self, run_id: str):
        from engine.db import Store
        db = Store()
        run = db.get_run(run_id)
        if not run:
            return None
        summary = db.get_run_summary(run_id) or {}
        return {**run, **summary}

    def get_run_events(self, run_id: str):
        from engine.db import Store
        return Store().get_run_events(run_id)

    def get_run_decisions(self, run_id: str):
        from engine.db import Store
        return Store().get_run_decisions(run_id)

    def get_run_failures(self, run_id: str):
        from engine.db import Store
        return Store().get_run_failures(run_id)

    def get_flow_graph(self, flow_id: str):
        d = self.get_flow(flow_id)
        return d.get("mermaid", "")

    def get_run_events_since(self, run_id: str, after_id: int = 0):
        from engine.db import Store
        return Store().get_run_events_since(run_id, int(after_id))

    def get_step_result(self, run_id: str, step_id: str):
        """Return all attempt records for a step (last entry is the final outcome)."""
        from engine.db import Store
        import json
        rows = Store().get_step_result(run_id, step_id)
        # Deserialise JSON fields so JS receives plain objects
        out = []
        for r in rows:
            row = dict(r)
            for key in ("result", "error"):
                if isinstance(row.get(key), str):
                    try:
                        row[key] = json.loads(row[key])
                    except Exception:
                        pass
            out.append(row)
        return out

    def get_screenshot(self, screenshot_path: str):
        """Read a screenshot file and return it as a base64 string."""
        import base64
        try:
            path = ROOT / screenshot_path if not screenshot_path.startswith("/") else \
                   __import__("pathlib").Path(screenshot_path)
            if not path.exists():
                return {"b64": None, "error": "File not found"}
            b64 = base64.b64encode(path.read_bytes()).decode()
            return {"b64": b64}
        except Exception as exc:
            return {"b64": None, "error": str(exc)}

    # ── V3 Schedules ──────────────────────────────────────────────────────────

    def schedule_flow(self, flow_id: str, profile_id: str, trigger: dict):
        import uuid
        from engine.db import Store
        from engine.scheduler import schedule_flow as _sched
        schedule_id = str(uuid.uuid4())
        db = Store()
        db.insert_schedule_v3(schedule_id, flow_id, profile_id,
                               trigger.get("type", "manual"), trigger)
        try:
            label = _sched(schedule_id, flow_id, profile_id, trigger)
            db.update_schedule_v3(schedule_id, enabled=True, launchd_label=label)
        except Exception as e:
            return {"ok": False, "schedule_id": schedule_id, "error": str(e)}
        return {"ok": True, "schedule_id": schedule_id}

    def list_schedules_v3(self):
        from engine.db import Store
        return Store().list_schedules_v3()

    def toggle_schedule_v3(self, schedule_id: str, enabled: bool):
        from engine.db import Store
        from engine.scheduler import schedule_flow as _sched, unschedule_flow as _unsched
        db = Store()
        sched = db.get_schedule_v3(schedule_id)
        if not sched:
            return {"ok": False, "error": "Schedule not found"}
        try:
            if enabled:
                label = _sched(schedule_id, sched["flow_id"], sched["profile_id"],
                                sched["trigger_params"])
                db.update_schedule_v3(schedule_id, enabled=True, launchd_label=label)
            else:
                _unsched(schedule_id)
                db.update_schedule_v3(schedule_id, enabled=False)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def delete_schedule_v3(self, schedule_id: str):
        from engine.db import Store
        from engine.scheduler import unschedule_flow as _unsched
        db = Store()
        try:
            _unsched(schedule_id)
        except Exception:
            pass
        db.delete_schedule_v3(schedule_id)
        return {"ok": True}

    # ── V3 Process Planner ────────────────────────────────────────────────────

    def start_planner_session(self, flow_id: str = None) -> dict:
        from engine.planner import create_session
        try:
            session = create_session()
            return {"ok": True, "session_id": session.session_id}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def get_planner_state(self, session_id: str) -> dict:
        from engine.planner import get_session
        session = get_session(session_id)
        if not session:
            return {"ok": False, "error": "Session not found"}
        return {"ok": True, **session.get_state()}

    def confirm_planner_intent(self, session_id: str, capture_index: int,
                                edits: dict = None) -> dict:
        from engine.planner import get_session
        session = get_session(session_id)
        if not session:
            return {"ok": False, "error": "Session not found"}
        try:
            session.confirm(int(capture_index), edits or None)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def discard_planner_intent(self, session_id: str, capture_index: int) -> dict:
        from engine.planner import get_session
        session = get_session(session_id)
        if not session:
            return {"ok": False, "error": "Session not found"}
        try:
            session.discard(int(capture_index))
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def add_manual_planner_intent(self, session_id: str, intent: dict) -> dict:
        from engine.planner import get_session
        session = get_session(session_id)
        if not session:
            return {"ok": False, "error": "Session not found"}
        try:
            session.add_manual(intent)
            return {"ok": True, "confirmed_count": len(session.intents)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def capture_planner_screenshot(self, session_id: str) -> dict:
        from engine.planner import get_session
        session = get_session(session_id)
        if not session:
            return {"ok": False, "error": "Session not found"}
        try:
            path = session.capture_screenshot()
            return {"ok": True, "screenshot_path": path}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def finish_planner_session(self, session_id: str, flow_id: str = None,
                                parameterized: list = None) -> dict:
        import yaml as _yaml
        from engine.planner import get_session, close_session
        session = get_session(session_id)
        if not session:
            return {"ok": False, "error": "Session not found"}
        try:
            if parameterized:
                session.intents = parameterized
            steps    = session.to_yaml_steps()
            yaml_str = _yaml.dump(steps, default_flow_style=False,
                                   allow_unicode=True, sort_keys=False)
            close_session(session_id)
            return {"ok": True, "steps": steps, "yaml": yaml_str}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def cancel_planner_session(self, session_id: str) -> dict:
        from engine.planner import close_session
        try:
            close_session(session_id)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ── Window reference ──────────────────────────────────────────────────────

    def set_window(self, window):
        self._window = window


def main() -> None:
    import platform as _platform
    api    = Api()
    window = webview.create_window(
        title="Mad Automation Platform",
        url=UI_INDEX.as_uri(),
        js_api=api,
        width=1280,
        height=820,
        min_size=(1024, 640),
        resizable=True,
        hidden=True,
    )
    api.set_window(window)

    _os = _platform.system()
    if _os == "Darwin":
        _start_mac(api, window)
    elif _os == "Windows":
        _start_windows(api, window)
    else:
        window.show()
        webview.start(debug=False)


def _start_mac(api, window) -> None:
    """macOS: rumps menu bar app + webview in background thread."""
    import threading
    try:
        import rumps
    except ImportError:
        # rumps not installed — show window and run plain (dev fallback)
        window.show()
        webview.start(debug=False)
        return

    _ICON = ROOT / "ui" / "assets" / "menubar_icon.png"

    class _App(rumps.App):
        def __init__(self):
            super().__init__(
                name="Mad Automation Platform",
                icon=str(_ICON) if _ICON.exists() else None,
                quit_button="Quit",
            )
            self._win = window
            self._api = api
            self.menu = [
                rumps.MenuItem("Open Dashboard",         callback=self.toggle),
                rumps.separator,
                rumps.MenuItem("Run Beverly Hills Flow", callback=self.run_bh),
            ]

        @rumps.clicked("Open Dashboard")
        def toggle(self, _=None):
            if self._win.shown:
                self._win.hide()
            else:
                self._win.show()

        def run_bh(self, _):
            self._api.run_flow("booking_bh", "default")

        def set_status(self, status: str) -> None:
            icons = {
                "idle":    "menubar_icon.png",
                "running": "menubar_running.png",
                "error":   "menubar_error.png",
            }
            p = ROOT / "ui" / "assets" / icons.get(status, "menubar_icon.png")
            if p.exists():
                self.icon = str(p)

    t = threading.Thread(target=webview.start, kwargs={"debug": False}, daemon=True)
    t.start()
    _App().run()


def _start_windows(api, window) -> None:
    """Windows: pystray system tray + webview in background thread."""
    import threading
    try:
        import pystray
        from PIL import Image as _PILImage
    except ImportError:
        window.show()
        webview.start(debug=False)
        return

    _ICON = ROOT / "ui" / "assets" / "tray_icon.png"
    icon_img = (
        _PILImage.open(str(_ICON))
        if _ICON.exists()
        else _PILImage.new("RGB", (64, 64), color=(30, 30, 30))
    )

    def _open(icon, _):
        window.show()

    def _quit(icon, _):
        icon.stop()
        window.destroy()

    tray = pystray.Icon(
        name="Mad Automation Platform",
        icon=icon_img,
        title="Mad Automation Platform",
        menu=pystray.Menu(
            pystray.MenuItem("Open Dashboard", _open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", _quit),
        ),
    )

    t = threading.Thread(target=webview.start, kwargs={"debug": False}, daemon=True)
    t.start()
    tray.run()


if __name__ == "__main__":
    main()
