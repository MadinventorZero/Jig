"""RunContext — live variable bag for a single flow execution."""
import os
from typing import Any, Optional

import jinja2


class RunContext:
    def __init__(self, *, flow_id: str, flow_name: str, run_id: str,
                 log_dir: str, profile: dict, site: dict = None):
        self._data: dict[str, Any] = {
            "flow":    {"id": flow_id, "name": flow_name},
            "run":     {"id": run_id, "log_dir": log_dir},
            "profile": profile,
            "site":    site or {},
            "steps":   {},
            "vars":    {},
            "env":     dict(os.environ),
        }
        self._block_stack:  list[str]  = []
        self._block_params: list[dict] = []
        self.resources: dict[str, Any] = {}  # browser, gmail_service, etc.

    # ── Block stack ───────────────────────────────────────────────────────────

    @property
    def block_path(self) -> list[str]:
        return list(self._block_stack)

    def push_block(self, block_id: str, params: dict) -> None:
        self._block_stack.append(block_id)
        self._block_params.append(params)
        self._data["block"] = params

    def pop_block(self) -> None:
        self._block_stack.pop()
        self._block_params.pop()
        self._data["block"] = self._block_params[-1] if self._block_params else {}

    # ── Step results ──────────────────────────────────────────────────────────

    def set_step_result(self, step_id: str, result: dict,
                        block_path: list = None) -> None:
        self._data["steps"][step_id] = {"result": result}

    def get_step_result(self, step_id: str) -> Optional[dict]:
        return self._data.get("steps", {}).get(step_id, {}).get("result")

    # ── Variable resolution ───────────────────────────────────────────────────

    def resolve(self, template: Any) -> Any:
        if not isinstance(template, str) or "{{" not in template:
            return template
        env = jinja2.Environment(undefined=jinja2.Undefined)
        try:
            return env.from_string(template).render(**self._data)
        except Exception:
            return template

    def resolve_params(self, params: dict) -> dict:
        return {k: self._resolve_value(v) for k, v in params.items()}

    def _resolve_value(self, v: Any) -> Any:
        if isinstance(v, str):
            return self.resolve(v)
        if isinstance(v, dict):
            return self.resolve_params(v)
        if isinstance(v, list):
            return [self._resolve_value(item) for item in v]
        return v
