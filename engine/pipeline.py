"""Pipeline — executes a FlowDef, manages RunContext, emits SSE events."""
import asyncio
import queue
import traceback as tb
from typing import Callable, Optional

from engine.context import RunContext
from engine.db import Store
from engine.executor import StepExecutor, StepError
from engine.registry import ActionRegistry
from engine.v3_models import FlowDef, Run, RunStatus, StepDef, utc_now


class FlowCancelledError(Exception):
    pass


class FlowAbortedError(Exception):
    pass


class Pipeline:
    def __init__(self, flow: FlowDef, run: Run, db: Store,
                 registry: ActionRegistry,
                 sse_queue: queue.Queue = None):
        self.flow      = flow
        self.run       = run
        self.db        = db
        self._sse      = sse_queue or queue.Queue()
        self._executor = StepExecutor(registry, db)

        self._block_stack: list[str] = []
        self._cancel = False
        self._abort  = False

    def cancel(self) -> None:
        """Graceful stop — halt after the current step finishes."""
        self._cancel = True

    def abort(self) -> None:
        """Hard stop — interrupt at the next step boundary."""
        self._abort = True

    # ── Public entry point ────────────────────────────────────────────────────

    async def run_flow(self, ctx: RunContext) -> str:
        # Inject engine references so actions (llm_decide, block, etc.) can reach back
        ctx.resources.setdefault("_emit",     self.emit)
        ctx.resources.setdefault("_registry", self._executor.registry)
        ctx.resources.setdefault("_db",       self.db)
        ctx.resources.setdefault("_run_id",   self.run.run_id)

        # Concurrency guard
        if self.flow.concurrency == "skip-if-running":
            active = self.db.get_active_run(self.flow.id)
            if active and active["run_id"] != self.run.run_id:
                self.db.update_run_status(self.run.run_id, RunStatus.CANCELLED,
                                          "skip-if-running: another run is active")
                return RunStatus.CANCELLED

        self.emit(
            "run.started",
            message=f"[{self.flow.name}] started",
            flow_id=self.flow.id,
            trigger_type=self.run.trigger_type,
            profile_id=self.run.profile_id,
        )

        heartbeat_task = asyncio.create_task(self._heartbeat())
        final_status   = RunStatus.COMPLETED
        try:
            await self._execute_steps(self.flow.steps, ctx)
        except FlowCancelledError:
            final_status = RunStatus.CANCELLED
            self.emit("run.cancelled",
                      message=f"[{self.flow.name}] cancelled by user")
        except FlowAbortedError:
            final_status = RunStatus.ABORTED
            self.emit("run.aborted",
                      message=f"[{self.flow.name}] aborted")
        except Exception as exc:
            final_status = RunStatus.FAILED
            self.emit(
                "run.failed", level="ERROR",
                message=f"[{self.flow.name}] failed: {exc}",
                error=str(exc), traceback=tb.format_exc(),
            )
            await self._run_on_error(exc, ctx)
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            await self._cleanup(ctx)

        self.db.update_run_status(self.run.run_id, final_status)
        self.emit(f"run.{final_status}",
                  message=f"[{self.flow.name}] {final_status}")
        return final_status

    # ── Step sequencer ────────────────────────────────────────────────────────

    async def _execute_steps(self, steps: list[StepDef],
                              ctx: RunContext) -> None:
        step_index = {s.step_id: s for s in steps}
        step_order = [s.step_id for s in steps]
        n = len(step_order)
        i = 0

        while i < n:
            if self._abort:
                raise FlowAbortedError()
            if self._cancel:
                raise FlowCancelledError()

            # External cancel signal written by UI cancel_run() API call
            if self.db.kv_get(f"cancel:{self.run.run_id}"):
                self.db.kv_set(f"cancel:{self.run.run_id}", None)
                raise FlowCancelledError()

            step = step_index[step_order[i]]

            if not step.enabled:
                self.emit(
                    "step.skipped",
                    step_id=step.step_id,
                    message=f"[{step.step_id}] skipped (disabled)",
                )
                i += 1
                continue

            # Checkpoint resume: step was already completed in a prior run
            existing = ctx.get_step_result(step.step_id)
            if existing is not None:
                self.emit(
                    "step.skipped",
                    step_id=step.step_id,
                    message=f"[{step.step_id}] checkpoint skip",
                )
                choice = existing.get("choice")
                if choice and step.on_choice:
                    raw_target = step.on_choice.get(str(choice))
                    if raw_target:
                        target = raw_target.replace("skip_to:", "").strip()
                        if target == "__end__":
                            return
                        if target in step_index:
                            i = step_order.index(target)
                            continue
                i += 1
                continue

            try:
                _, result = await self._executor.execute(
                    step, ctx, self.run.run_id, self.emit
                )
            except TimeoutError:
                if step.on_timeout and step.on_timeout in step_index:
                    target = step.on_timeout
                    self.emit(
                        "branch.taken",
                        step_id=step.step_id,
                        message=f"[{step.step_id}] timeout → {target}",
                        choice="timeout", to_step_id=target,
                    )
                    i = step_order.index(target)
                    continue
                raise
            except StepError:
                if step.on_error and step.on_error in step_index:
                    target = step.on_error
                    self.emit(
                        "branch.taken",
                        step_id=step.step_id, level="WARN",
                        message=f"[{step.step_id}] error → {target}",
                        choice="error", to_step_id=target,
                    )
                    i = step_order.index(target)
                    continue
                raise

            # Branch on choice (llm_decide, condition, gmail_watch, etc.)
            choice = result.get("choice")
            if choice and step.on_choice:
                raw_target = step.on_choice.get(str(choice))
                if raw_target:
                    target = raw_target.replace("skip_to:", "").strip()
                    self.emit(
                        "branch.taken",
                        step_id=step.step_id,
                        message=(f"[{step.step_id}] → {target} "
                                 f"(choice: {choice})"),
                        choice=choice, to_step_id=target,
                    )
                    if target == "__end__":
                        return
                    if target not in step_index:
                        raise ValueError(
                            f"Branch target {target!r} not in flow. "
                            f"Available: {step_order}"
                        )
                    i = step_order.index(target)
                    continue

            i += 1

    # ── Heartbeat ─────────────────────────────────────────────────────────────

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(30)
            self.emit("run.heartbeat",
                      message=f"[{self.flow.name}] heartbeat",
                      flow_id=self.flow.id)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _run_on_error(self, exc: Exception, ctx: RunContext) -> None:
        if not self.flow.on_error:
            return
        action_type = self.flow.on_error.get("action")
        params = ctx.resolve_params(self.flow.on_error.get("params", {}))
        params["_error"] = str(exc)
        from engine.registry import registry as global_registry
        if global_registry.is_registered(action_type):
            try:
                await global_registry.get(action_type).handler(ctx, params)
            except Exception:
                pass

    async def _cleanup(self, ctx: RunContext) -> None:
        for resource in list(ctx.resources.values()):
            try:
                if hasattr(resource, "stop"):
                    if asyncio.iscoroutinefunction(resource.stop):
                        await resource.stop()
                    else:
                        resource.stop()
                elif hasattr(resource, "close"):
                    if asyncio.iscoroutinefunction(resource.close):
                        await resource.close()
                    else:
                        resource.close()
            except Exception:
                pass

    # ── SSE emitter ───────────────────────────────────────────────────────────

    def emit(self, event: str, *, level: str = "INFO",
             step_id: str = None, message: str, **data) -> None:
        record = {
            "event":      event,
            "run_id":     self.run.run_id,
            "ts":         utc_now(),
            "level":      level,
            "step_id":    step_id,
            "block_path": list(self._block_stack),
            "message":    message,
            "data":       data,
        }
        self.db.insert_run_event(record)
        self._sse.put(record)
