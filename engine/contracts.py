"""
Block contract model — typed input/output schemas for Jig chain validation.

Every built-in action declares what it PRODUCES (output_schema).
The ChainValidator walks a FlowDef in step order and checks:
  1. All step types are registered.
  2. block steps reference block_ids that exist.
  3. {{ steps.X.result.Y }} references point to steps that exist in the flow.
  4. Those references point to steps that come BEFORE the current step.
  5. Referenced fields Y exist in the producing step's declared output_schema
     (warning only — schemas may be partial for dynamic results).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


VALID_TYPES = frozenset({"str", "bool", "int", "float", "dict", "list", "any"})

_STEP_FIELD_RE = re.compile(r"\{\{\s*steps\.(\w+)\.result\.(\w+)")
_STEP_LOOSE_RE = re.compile(r"\{\{\s*steps\.(\w+)")


# ── Schema primitives ─────────────────────────────────────────────────────────

@dataclass
class FieldSchema:
    name:        str
    type:        str  = "any"
    required:    bool = True
    description: str  = ""

    def __post_init__(self):
        if self.type not in VALID_TYPES:
            self.type = "any"

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type,
                "required": self.required, "description": self.description}


@dataclass
class BlockContract:
    """Declares what a block/action type consumes and produces."""
    input_schema:  list[FieldSchema] = field(default_factory=list)
    output_schema: list[FieldSchema] = field(default_factory=list)

    def output_field_names(self) -> set[str]:
        return {f.name for f in self.output_schema}

    def to_dict(self) -> dict:
        return {
            "input_schema":  [f.to_dict() for f in self.input_schema],
            "output_schema": [f.to_dict() for f in self.output_schema],
        }


@dataclass
class ContractViolation:
    step_id:  str
    field:    str
    kind:     str       # missing_step_ref | ordering_violation | missing_field
                        # | unknown_type | unresolvable_block
    message:  str
    severity: str = "error"   # error | warning

    def to_dict(self) -> dict:
        return {"step_id": self.step_id, "field": self.field,
                "kind": self.kind, "message": self.message,
                "severity": self.severity}


# ── Built-in action contracts ─────────────────────────────────────────────────

def _f(*fields: tuple) -> list[FieldSchema]:
    """Shorthand: _f(('name',), ('name', 'type'), ('name', 'type', False)) ..."""
    result = []
    for f in fields:
        name = f[0]
        typ  = f[1] if len(f) > 1 else "any"
        req  = f[2] if len(f) > 2 else True
        desc = f[3] if len(f) > 3 else ""
        result.append(FieldSchema(name=name, type=typ, required=req, description=desc))
    return result


BUILTIN_CONTRACTS: dict[str, BlockContract] = {
    # ── Browser ──────────────────────────────────────────────────────────────
    "browser_navigate": BlockContract(output_schema=_f(
        ("url",             "str"),
        ("title",           "str"),
        ("screenshot_path", "str", False),
    )),
    "browser_click": BlockContract(output_schema=_f(
        ("clicked",         "bool"),
        ("screenshot_path", "str", False),
    )),
    "browser_fill": BlockContract(output_schema=_f(
        ("filled", "bool"),
    )),
    "browser_submit": BlockContract(output_schema=_f(
        ("submitted",       "bool"),
        ("screenshot_path", "str", False),
    )),
    "browser_screenshot": BlockContract(output_schema=_f(
        ("screenshot_path", "str"),
    )),
    "browser_extract_text": BlockContract(output_schema=_f(
        ("text",  "str"),
        ("found", "bool"),
    )),
    "browser_wait": BlockContract(output_schema=_f(
        ("elapsed_ms", "int"),
    )),
    "browser_select": BlockContract(output_schema=_f(
        ("selected", "bool"),
    )),
    # ── LLM ──────────────────────────────────────────────────────────────────
    "llm_decide": BlockContract(output_schema=_f(
        ("choice",     "str"),
        ("reasoning",  "str"),
        ("confidence", "float", False),
    )),
    "llm_extract": BlockContract(output_schema=_f(
        ("result", "dict"),
        ("raw",    "str"),
    )),
    "claude_complete": BlockContract(output_schema=_f(
        ("text", "str"),
    )),
    # ── Gmail ─────────────────────────────────────────────────────────────────
    "gmail_watch": BlockContract(output_schema=_f(
        ("subject",   "str"),
        ("body",      "str"),
        ("thread_id", "str"),
        ("msg_id",    "str"),
        ("sender",    "str"),
    )),
    "gmail_send": BlockContract(output_schema=_f(
        ("message_id", "str"),
        ("thread_id",  "str"),
    )),
    "gmail_reply": BlockContract(output_schema=_f(
        ("message_id", "str"),
    )),
    # ── Storage ───────────────────────────────────────────────────────────────
    "storage_get": BlockContract(output_schema=_f(
        ("value", "any"),
        ("found", "bool"),
    )),
    "storage_set": BlockContract(output_schema=_f(
        ("key", "str"),
    )),
    # ── Script / HTTP ─────────────────────────────────────────────────────────
    "script_run": BlockContract(output_schema=_f(
        ("stdout",     "str"),
        ("stderr",     "str"),
        ("returncode", "int"),
    )),
    "http_request": BlockContract(output_schema=_f(
        ("status_code", "int"),
        ("body",        "str"),
        ("headers",     "dict"),
        ("json",        "dict", False),
    )),
    # ── Flow control ──────────────────────────────────────────────────────────
    "human_pause": BlockContract(output_schema=_f(
        ("resumed",        "bool"),
        ("action",         "str"),
        ("waited_seconds", "float"),
        ("choice",         "str"),
    )),
    "delay": BlockContract(output_schema=_f(
        ("elapsed_seconds", "float"),
    )),
    # ── Block execution ───────────────────────────────────────────────────────
    "block": BlockContract(output_schema=_f(
        ("block_id", "str"),
        ("result",   "dict"),
        ("choice",   "str"),
    )),
    # ── Vision ───────────────────────────────────────────────────────────────
    "vision_describe": BlockContract(output_schema=_f(
        ("description",     "str"),
        ("screenshot_path", "str"),
    )),
    "vision_find_element": BlockContract(output_schema=_f(
        ("found",    "bool"),
        ("selector", "str",  False),
        ("bbox",     "dict", False),
    )),
    # ── Notification ─────────────────────────────────────────────────────────
    "notify": BlockContract(output_schema=_f(
        ("sent", "bool"),
    )),
}


# ── Chain Validator ───────────────────────────────────────────────────────────

def _collect_step_refs(value: Any) -> list[tuple[str, str]]:
    """Return (step_id, field_name) pairs from {{ steps.X.result.Y }} templates."""
    refs: list[tuple[str, str]] = []
    if isinstance(value, str):
        precise: set[str] = set()
        for m in _STEP_FIELD_RE.finditer(value):
            refs.append((m.group(1), m.group(2)))
            precise.add(m.group(1))
        for m in _STEP_LOOSE_RE.finditer(value):
            sid = m.group(1)
            if sid not in precise:
                refs.append((sid, ""))
    elif isinstance(value, dict):
        for v in value.values():
            refs.extend(_collect_step_refs(v))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_collect_step_refs(item))
    return refs


class ChainValidator:
    def __init__(self, action_registry, block_registry=None):
        self._actions = action_registry
        self._blocks  = block_registry

    def validate(self, flow) -> list[ContractViolation]:
        violations: list[ContractViolation] = []
        steps            = flow.steps or []
        step_ids_ordered = [s.step_id for s in steps]
        step_by_id       = {s.step_id: s for s in steps}

        # step_id → set of declared output field names (empty set = unknown/dynamic)
        produced: dict[str, set[str]] = {}

        for pos, step in enumerate(steps):
            sid = step.step_id

            # 1. Type registered?
            if not self._actions.is_registered(step.type):
                violations.append(ContractViolation(
                    step_id=sid, field="type", kind="unknown_type",
                    message=f"Step type '{step.type}' is not registered.",
                    severity="error",
                ))
                produced[sid] = set()
                continue

            # 2. block type → block_id resolves?
            if step.type == "block" and self._blocks:
                block_id = step.params.get("block_id", "")
                if block_id and not self._blocks.get(block_id):
                    violations.append(ContractViolation(
                        step_id=sid, field="block_id", kind="unresolvable_block",
                        message=f"Block '{block_id}' not found in block registry.",
                        severity="error",
                    ))

            # 3–5. Template reference checks
            before_ids = set(step_ids_ordered[:pos])
            for ref_sid, ref_field in _collect_step_refs(step.params):
                if ref_sid not in step_by_id:
                    violations.append(ContractViolation(
                        step_id=sid,
                        field=f"steps.{ref_sid}",
                        kind="missing_step_ref",
                        message=(f"References '{{{{ steps.{ref_sid} }}}}' but no step "
                                 f"with that ID exists in this flow."),
                        severity="error",
                    ))
                    continue

                if ref_sid not in before_ids:
                    violations.append(ContractViolation(
                        step_id=sid,
                        field=f"steps.{ref_sid}",
                        kind="ordering_violation",
                        message=(f"References '{{{{ steps.{ref_sid} }}}}' which "
                                 f"comes AFTER this step in the flow."),
                        severity="error",
                    ))
                    continue

                if ref_field:
                    prod_fields = produced.get(ref_sid, set())
                    if prod_fields and ref_field not in prod_fields:
                        violations.append(ContractViolation(
                            step_id=sid,
                            field=f"steps.{ref_sid}.result.{ref_field}",
                            kind="missing_field",
                            message=(
                                f"'{ref_sid}' does not declare output field '{ref_field}'. "
                                f"Declared: {sorted(prod_fields) or 'none'}."
                            ),
                            severity="warning",
                        ))

            # Record what this step produces
            action_def = self._actions._actions.get(step.type)
            if action_def and action_def.contract:
                produced[sid] = action_def.contract.output_field_names()
            else:
                produced[sid] = set()

        return violations
