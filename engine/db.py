"""SQLite store for v3 — run_events, step_results, runs, decisions."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from engine.v3_models import Run, StepResult, Decision, RunStatus, utc_now

DB_PATH = Path(__file__).parent.parent / "data" / "platform.db"


def _json(obj) -> Optional[str]:
    return json.dumps(obj, default=str) if obj is not None else None


class Store:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id        TEXT PRIMARY KEY,
                    flow_id       TEXT NOT NULL,
                    trigger_type  TEXT NOT NULL,
                    profile_id    TEXT,
                    started_at    TEXT NOT NULL,
                    completed_at  TEXT,
                    status        TEXT NOT NULL DEFAULT 'running',
                    error         TEXT
                );

                CREATE TABLE IF NOT EXISTS run_events (
                    id         INTEGER PRIMARY KEY,
                    run_id     TEXT NOT NULL,
                    ts         TEXT NOT NULL,
                    event      TEXT NOT NULL,
                    level      TEXT NOT NULL DEFAULT 'INFO',
                    step_id    TEXT,
                    block_path TEXT NOT NULL DEFAULT '[]',
                    message    TEXT NOT NULL,
                    data       TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_run_events_run_id
                    ON run_events(run_id);
                CREATE INDEX IF NOT EXISTS idx_run_events_event
                    ON run_events(run_id, event);

                CREATE TABLE IF NOT EXISTS step_results (
                    id           INTEGER PRIMARY KEY,
                    run_id       TEXT NOT NULL,
                    step_id      TEXT NOT NULL,
                    block_path   TEXT NOT NULL DEFAULT '[]',
                    attempt      INTEGER NOT NULL DEFAULT 1,
                    started_at   TEXT NOT NULL,
                    completed_at TEXT,
                    status       TEXT NOT NULL,
                    result       TEXT,
                    error        TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_step_results_pk
                    ON step_results(run_id, step_id, block_path, attempt);
                CREATE INDEX IF NOT EXISTS idx_step_results_run
                    ON step_results(run_id);

                CREATE TABLE IF NOT EXISTS decisions (
                    decision_id     TEXT PRIMARY KEY,
                    run_id          TEXT NOT NULL,
                    step_id         TEXT NOT NULL,
                    model           TEXT NOT NULL,
                    prompt_hash     TEXT NOT NULL,
                    screenshot_hash TEXT,
                    choice          TEXT NOT NULL,
                    reasoning       TEXT,
                    confidence      REAL,
                    latency_ms      INTEGER,
                    created_at      TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_decisions_run ON decisions(run_id);

                CREATE TABLE IF NOT EXISTS kv_store (
                    key        TEXT PRIMARY KEY,
                    value      TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS schedules (
                    schedule_id    TEXT PRIMARY KEY,
                    flow_id        TEXT NOT NULL,
                    profile_id     TEXT NOT NULL,
                    trigger_type   TEXT NOT NULL,
                    trigger_params TEXT NOT NULL,
                    enabled        INTEGER NOT NULL DEFAULT 0,
                    launchd_label  TEXT,
                    created_at     TEXT NOT NULL,
                    last_run_at    TEXT,
                    last_run_id    TEXT
                );
            """)

    # ── Runs ──────────────────────────────────────────────────────────────────

    def insert_run(self, run: Run) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, flow_id, trigger_type, profile_id, "
                "started_at, status) VALUES (?, ?, ?, ?, ?, ?)",
                (run.run_id, run.flow_id, run.trigger_type,
                 run.profile_id, run.started_at, run.status),
            )

    def update_run_status(self, run_id: str, status: str,
                          error: str = None) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE runs SET status=?, completed_at=?, error=? WHERE run_id=?",
                (status, utc_now(), error, run_id),
            )

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            return dict(row) if row else None

    # ── Run events ────────────────────────────────────────────────────────────

    def insert_run_event(self, record: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO run_events "
                "(run_id, ts, event, level, step_id, block_path, message, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record["run_id"],
                    record["ts"],
                    record["event"],
                    record.get("level", "INFO"),
                    record.get("step_id"),
                    json.dumps(record.get("block_path", [])),
                    record["message"],
                    _json(record.get("data")),
                ),
            )

    def get_run_events(self, run_id: str, *, event: str = None,
                       step_id: str = None) -> list[dict]:
        with self._conn() as conn:
            q    = "SELECT * FROM run_events WHERE run_id=?"
            args = [run_id]
            if event:
                q += " AND event=?"; args.append(event)
            if step_id:
                q += " AND step_id=?"; args.append(step_id)
            q += " ORDER BY ts ASC"
            return [dict(r) for r in conn.execute(q, args).fetchall()]

    # ── Step results ──────────────────────────────────────────────────────────

    def insert_step_result(self, sr: StepResult) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO step_results "
                "(run_id, step_id, block_path, attempt, started_at, "
                "completed_at, status, result, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sr.run_id, sr.step_id,
                    json.dumps(sr.block_path),
                    sr.attempt, sr.started_at, sr.completed_at,
                    sr.status,
                    _json(sr.result),
                    _json(sr.error),
                ),
            )

    def get_step_result(self, run_id: str, step_id: str,
                        block_path: list = None) -> list[dict]:
        bp = json.dumps(block_path or [])
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM step_results "
                "WHERE run_id=? AND step_id=? AND block_path=? ORDER BY attempt ASC",
                (run_id, step_id, bp),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_run_failures(self, run_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT e.ts, e.step_id, e.block_path, e.message,
                       json_extract(e.data, '$.attempt')        AS attempt,
                       json_extract(e.data, '$.failure_reason') AS failure_reason,
                       r.error
                FROM run_events e
                LEFT JOIN step_results r
                  ON  r.run_id     = e.run_id
                  AND r.step_id    = e.step_id
                  AND r.block_path = e.block_path
                  AND r.attempt    = json_extract(e.data, '$.attempt')
                WHERE e.run_id=? AND e.event='step.failed'
                ORDER BY e.ts ASC
            """, (run_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_run_decisions(self, run_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT ts, step_id, block_path,
                       json_extract(data, '$.choice')      AS choice,
                       json_extract(data, '$.reasoning')   AS reasoning,
                       json_extract(data, '$.latency_ms')  AS latency_ms,
                       json_extract(data, '$.prompt_hash') AS prompt_hash,
                       json_extract(data, '$.decision_id') AS decision_id
                FROM run_events
                WHERE run_id=? AND event='llm.decided'
                ORDER BY ts ASC
            """, (run_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_decision_history(self, flow_id: str, step_id: str,
                             limit: int = 20) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT e.step_id, e.block_path,
                       json_extract(e.data, '$.choice')      AS choice,
                       json_extract(e.data, '$.prompt_hash') AS prompt_hash,
                       r.started_at
                FROM run_events e
                JOIN runs r ON r.run_id = e.run_id
                WHERE r.flow_id=? AND e.event='llm.decided' AND e.step_id=?
                ORDER BY r.started_at DESC
                LIMIT ?
            """, (flow_id, step_id, limit)).fetchall()
            return [dict(r) for r in rows]

    def get_vision_diagnostics(self, run_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT ts, step_id, block_path, event,
                       json_extract(data, '$.template')   AS template,
                       json_extract(data, '$.confidence') AS confidence,
                       json_extract(data, '$.threshold')  AS threshold,
                       json_extract(data, '$.region')     AS region
                FROM run_events
                WHERE run_id=? AND event IN ('vision.found', 'vision.not_found')
                ORDER BY ts ASC
            """, (run_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_poll_history(self, run_id: str, step_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT ts, event,
                       json_extract(data, '$.attempt')      AS attempt,
                       json_extract(data, '$.max_attempts') AS max_attempts,
                       json_extract(data, '$.elapsed_ms')   AS elapsed_ms,
                       json_extract(data, '$.condition')    AS condition
                FROM run_events
                WHERE run_id=? AND step_id=?
                  AND event IN ('poll.check', 'poll.resolved', 'poll.timeout')
                ORDER BY ts ASC
            """, (run_id, step_id)).fetchall()
            return [dict(r) for r in rows]

    def get_run_summary(self, run_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("""
                SELECT
                    e.run_id,
                    MIN(CASE WHEN e.event='run.started' THEN e.ts END) AS started_at,
                    MIN(CASE WHEN e.event IN ('run.completed','run.failed',
                                             'run.cancelled','run.aborted')
                             THEN e.ts END)                            AS ended_at,
                    MIN(CASE WHEN e.event IN ('run.completed','run.failed',
                                             'run.cancelled','run.aborted')
                             THEN e.event END)                         AS final_status,
                    COUNT(CASE WHEN e.event='step.completed' THEN 1 END) AS steps_completed,
                    COUNT(CASE WHEN e.event='step.failed'    THEN 1 END) AS steps_failed,
                    GROUP_CONCAT(
                        CASE WHEN e.event='llm.decided'
                             THEN e.step_id || ':' || json_extract(e.data, '$.choice')
                        END, ' → '
                    )                                                  AS decision_chain
                FROM run_events e
                WHERE e.run_id=?
                GROUP BY e.run_id
            """, (run_id,)).fetchone()
            return dict(row) if row else None

    # ── Active run check (for concurrency) ───────────────────────────────────

    def get_active_run(self, flow_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE flow_id=? AND status='running' "
                "ORDER BY started_at DESC LIMIT 1",
                (flow_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_completed_steps(self, run_id: str) -> list[dict]:
        """Return top-level (non-block) steps that completed successfully, in order."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT step_id, result FROM step_results "
                "WHERE run_id=? AND status='completed' AND block_path='[]' "
                "ORDER BY id ASC",
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def reset_run_for_resume(self, run_id: str) -> None:
        """Clear completed_at and reset status to running for a checkpoint resume."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE runs SET status='running', completed_at=NULL, error=NULL "
                "WHERE run_id=?",
                (run_id,),
            )

    def list_runs(self, flow_id: str = None, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            if flow_id:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE flow_id=? ORDER BY started_at DESC LIMIT ?",
                    (flow_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_run_events_since(self, run_id: str, after_id: int = 0) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM run_events WHERE run_id=? AND id>? ORDER BY id ASC",
                (run_id, after_id),
            ).fetchall()
            return [dict(r) for r in rows]

    def insert_schedule_v3(self, schedule_id: str, flow_id: str, profile_id: str,
                            trigger_type: str, trigger_params: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO schedules (schedule_id, flow_id, profile_id, trigger_type, "
                "trigger_params, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (schedule_id, flow_id, profile_id, trigger_type,
                 json.dumps(trigger_params), utc_now()),
            )

    def get_schedule_v3(self, schedule_id: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM schedules WHERE schedule_id=?", (schedule_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("trigger_params"):
                d["trigger_params"] = json.loads(d["trigger_params"])
            return d

    def list_schedules_v3(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY created_at DESC"
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get("trigger_params"):
                    d["trigger_params"] = json.loads(d["trigger_params"])
                result.append(d)
            return result

    def update_schedule_v3(self, schedule_id: str, **kwargs) -> None:
        allowed = {"enabled", "launchd_label", "last_run_at", "last_run_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        cols = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [schedule_id]
        with self._conn() as conn:
            conn.execute(f"UPDATE schedules SET {cols} WHERE schedule_id=?", vals)

    def delete_schedule_v3(self, schedule_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM schedules WHERE schedule_id=?", (schedule_id,))

    # ── KV store ──────────────────────────────────────────────────────────────

    def kv_set(self, key: str, value) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv_store (key, value, updated_at) "
                "VALUES (?, ?, ?)",
                (key, _json(value), utc_now()),
            )

    def kv_get(self, key: str):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM kv_store WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                return None
            raw = row["value"]
            return json.loads(raw) if raw is not None else None

    # ── Decisions ─────────────────────────────────────────────────────────────

    def insert_decision(self, d: Decision) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO decisions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (d.decision_id, d.run_id, d.step_id, d.model,
                 d.prompt_hash, d.screenshot_hash, d.choice,
                 d.reasoning, d.confidence, d.latency_ms, d.created_at),
            )
