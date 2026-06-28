"""V3 platform data models — Flow, Step, Run, RunEvent, StepResult, Decision."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return str(uuid.uuid4())


class StepStatus:
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"
    WARNING   = "warning"   # non-blocking failure — step continued


class RunStatus:
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"
    ABORTED   = "aborted"


@dataclass
class StepDef:
    step_id:             str
    type:                str
    params:              dict             = field(default_factory=dict)
    mode:                str              = "dom"
    max_retries:         int              = 0
    retry_delay_seconds: float            = 1.0
    idempotent:          bool             = True
    on_choice:           dict             = field(default_factory=dict)
    on_timeout:          Optional[str]    = None
    on_error:            Optional[str]    = None
    on_error_mode:       str              = "blocking"  # blocking | non_blocking
    enabled:             bool             = True
    block_ref:           Optional[str]    = None


@dataclass
class BlockDef:
    id:            str
    name:          str
    version:       int
    steps:         list
    params:        dict           = field(default_factory=dict)
    input_schema:  list           = field(default_factory=list)
    output_schema: list           = field(default_factory=list)
    on_error:      Optional[dict] = None


@dataclass
class TriggerDef:
    type:   str
    params: dict = field(default_factory=dict)


@dataclass
class FlowDef:
    id:          str
    name:        str
    version:     int
    trigger:     TriggerDef
    steps:       list
    context:     dict           = field(default_factory=dict)
    concurrency: str            = "serial"
    on_error:    Optional[dict] = None


@dataclass
class Run:
    run_id:       str
    flow_id:      str
    trigger_type: str
    profile_id:   Optional[str]
    started_at:   str
    status:       str           = RunStatus.RUNNING
    completed_at: Optional[str] = None
    error:        Optional[str] = None


@dataclass
class StepResult:
    run_id:       str
    step_id:      str
    block_path:   list
    attempt:      int
    started_at:   str
    status:       str
    completed_at: Optional[str]  = None
    result:       Optional[dict] = None
    error:        Optional[dict] = None


@dataclass
class RunEvent:
    run_id:     str
    ts:         str
    event:      str
    level:      str
    message:    str
    step_id:    Optional[str] = None
    block_path: list          = field(default_factory=list)
    data:       dict          = field(default_factory=dict)


@dataclass
class Decision:
    decision_id:     str
    run_id:          str
    step_id:         str
    model:           str
    prompt_hash:     str
    screenshot_hash: Optional[str]
    choice:          str
    reasoning:       str
    confidence:      Optional[float]
    latency_ms:      int
    created_at:      str
