"""StepExecutor — resolves params, calls handler, handles retries."""
import asyncio
import traceback as tb
from pathlib import Path
from typing import Callable

from engine.context import RunContext
from engine.db import Store
from engine.registry import ActionRegistry
from engine.v3_models import StepDef, StepResult, StepStatus, utc_now


class StepError(Exception):
    pass


class StepExecutor:
    def __init__(self, registry: ActionRegistry, db: Store):
        self.registry = registry
        self.db       = db

    async def execute(self, step: StepDef, ctx: RunContext,
                      run_id: str, emit: Callable) -> tuple[str, dict]:
        """
        Execute a single step with retry support.
        Returns (status, result). Raises StepError on final blocking failure.
        """
        action       = self.registry.get(step.type)
        resolved     = ctx.resolve_params(step.params)
        started_at   = utc_now()
        max_attempts = step.max_retries + 1

        path_label = ".".join(ctx.block_path + [step.step_id])
        emit(
            "step.started",
            step_id=step.step_id,
            level="INFO",
            message=f"[{path_label}] {step.type} → starting",
            step_type=step.type,
            params=list(resolved.keys()),
        )

        ctx._data["_current_step_id"] = step.step_id

        # ── Debug pause (before execution) ────────────────────────────────────
        if self.db.kv_get(f"debug:{run_id}"):
            action = await self._debug_pause(run_id, step, ctx, emit)
            if action == "skip":
                skip_result = {"_debug_skip": True}
                ctx.set_step_result(step.step_id, skip_result, ctx.block_path)
                self.db.insert_step_result(StepResult(
                    run_id=run_id,
                    step_id=step.step_id,
                    block_path=ctx.block_path,
                    attempt=0,
                    started_at=started_at,
                    completed_at=utc_now(),
                    status=StepStatus.SKIPPED,
                    result=skip_result,
                ))
                emit(
                    "step.skipped",
                    step_id=step.step_id,
                    level="INFO",
                    message=f"[{path_label}] {step.type} → skipped by debug",
                )
                return StepStatus.SKIPPED, skip_result

        last_exc   = None
        last_trace = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = await action.handler(ctx, resolved)
                result = result or {}

                ctx.set_step_result(step.step_id, result, ctx.block_path)
                self.db.insert_step_result(StepResult(
                    run_id=run_id,
                    step_id=step.step_id,
                    block_path=ctx.block_path,
                    attempt=attempt,
                    started_at=started_at,
                    completed_at=utc_now(),
                    status=StepStatus.COMPLETED,
                    result=result,
                ))
                emit(
                    "step.completed",
                    step_id=step.step_id,
                    level="INFO",
                    message=f"[{path_label}] {step.type} → ok",
                    result_keys=list(result.keys()),
                )
                return StepStatus.COMPLETED, result

            except Exception as exc:
                last_exc   = exc
                last_trace = tb.format_exc()

                if attempt < max_attempts and step.idempotent:
                    emit(
                        "step.retry",
                        step_id=step.step_id,
                        level="WARN",
                        message=(f"[{path_label}] retry {attempt}/{step.max_retries}"
                                 f": {exc}"),
                        attempt=attempt,
                        max_retries=step.max_retries,
                        failure_reason=str(exc),
                        delay_ms=int(step.retry_delay_seconds * 1000),
                    )
                    await asyncio.sleep(step.retry_delay_seconds)
                    continue

                break  # exhausted retries — fall through to failure path

        # ── Final failure ─────────────────────────────────────────────────────
        from engine.errors import humanize_exception
        humanized       = humanize_exception(last_exc)
        screenshot_path = await self._try_screenshot(ctx, run_id, step.step_id)

        error_dict: dict = {
            "error":     str(last_exc),
            "traceback": last_trace,
            "humanized": humanized,
        }
        if screenshot_path:
            error_dict["screenshot_path"] = screenshot_path

        self.db.insert_step_result(StepResult(
            run_id=run_id,
            step_id=step.step_id,
            block_path=ctx.block_path,
            attempt=max_attempts,
            started_at=started_at,
            completed_at=utc_now(),
            status=StepStatus.FAILED,
            error=error_dict,
        ))

        if step.on_error_mode == "non_blocking":
            soft_result: dict = {
                "error":   True,
                "message": humanized,
                "step_id": step.step_id,
            }
            if screenshot_path:
                soft_result["screenshot_path"] = screenshot_path
            ctx.set_step_result(step.step_id, soft_result, ctx.block_path)
            emit(
                "step.warning",
                step_id=step.step_id,
                level="WARN",
                message=f"[{path_label}] {step.type} → non-blocking failure: {humanized}",
                failure_reason=str(last_exc),
                humanized=humanized,
            )
            return StepStatus.WARNING, soft_result

        emit(
            "step.failed",
            step_id=step.step_id,
            level="ERROR",
            message=f"[{path_label}] {step.type} → FAILED: {humanized}",
            attempt=max_attempts,
            failure_reason=str(last_exc),
            humanized=humanized,
        )
        raise StepError(str(last_exc)) from last_exc

    async def _debug_pause(self, run_id: str, step: StepDef,
                            ctx: RunContext, emit: Callable) -> str:
        """Pause before executing step in debug mode. Returns 'continue' or 'skip'."""
        screenshot_path = await self._try_screenshot(ctx, run_id, f"debug_{step.step_id}")
        emit(
            "step.debug_pause",
            step_id=step.step_id,
            level="INFO",
            message=f"[{step.step_id}] debug pause — waiting",
            step_type=step.type,
            screenshot_path=screenshot_path,
        )
        # Poll up to 30 minutes for user action
        for _ in range(3600):
            await asyncio.sleep(0.5)
            if self.db.kv_get(f"cancel:{run_id}"):
                return "continue"  # let pipeline's cancel check handle it
            action = self.db.kv_get(f"debug_continue:{run_id}")
            if action in ("continue", "skip"):
                self.db.kv_set(f"debug_continue:{run_id}", None)
                return action
        return "continue"

    async def _try_screenshot(self, ctx: RunContext,
                               run_id: str, step_id: str) -> str | None:
        """Silently capture a failure screenshot. Returns path or None."""
        try:
            browser = ctx.resources.get("browser")
            if not browser or not hasattr(browser, "page") or browser.page is None:
                return None
            path = Path(f"data/logs/{run_id}/fail_{step_id}.png")
            path.parent.mkdir(parents=True, exist_ok=True)
            await browser.page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception:
            return None
