from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class QueueBusyError(RuntimeError):
    pass


class QueueStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueuedTask:
    id: str
    job_id: str
    task_type: str
    phase: str | None
    payload: dict[str, Any]
    attempts: int


class DurableTaskQueue:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    phase TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    finished_at REAL,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_task_runs_claim
                    ON task_runs(status, created_at);
                """
            )
            connection.execute("BEGIN EXCLUSIVE")
            try:
                connection.execute("DROP INDEX IF EXISTS uq_task_runs_active_job")
                connection.execute(
                    """
                    CREATE UNIQUE INDEX uq_task_runs_active_job
                        ON task_runs(job_id)
                        WHERE status IN ('PREPARING', 'QUEUED', 'RUNNING')
                    """
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def prepare(
        self,
        job_id: str,
        task_type: str,
        *,
        phase: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        run_id = uuid.uuid4().hex
        try:
            with closing(self._connect()) as connection:
                connection.execute(
                    """
                    INSERT INTO task_runs(id, job_id, task_type, phase, payload_json, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'PREPARING', ?)
                    """,
                    (run_id, job_id, task_type, phase, json.dumps(payload or {}, ensure_ascii=False), time.time()),
                )
        except sqlite3.IntegrityError as exc:
            raise QueueBusyError(f"job already has a preparing, queued or running task: {job_id}") from exc
        return run_id

    def activate(self, run_id: str) -> None:
        with closing(self._connect()) as connection:
            updated = connection.execute(
                "UPDATE task_runs SET status = 'QUEUED' WHERE id = ? AND status = 'PREPARING'",
                (run_id,),
            ).rowcount
        if updated != 1:
            raise QueueStateError(f"prepared task cannot be activated: {run_id}")

    def cancel_prepared(self, run_id: str, reason: str) -> bool:
        with closing(self._connect()) as connection:
            updated = connection.execute(
                """
                UPDATE task_runs
                SET status = 'CANCELLED', finished_at = ?, error = ?
                WHERE id = ? AND status = 'PREPARING'
                """,
                (time.time(), reason, run_id),
            ).rowcount
        return updated == 1

    def enqueue(
        self,
        job_id: str,
        task_type: str,
        *,
        phase: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        run_id = self.prepare(job_id, task_type, phase=phase, payload=payload)
        try:
            self.activate(run_id)
        except Exception:
            self.cancel_prepared(run_id, "task activation failed")
            raise
        return run_id

    def claim_next(self, worker_id: str, *, lease_seconds: int = 120) -> QueuedTask | None:
        now = time.time()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM task_runs
                WHERE status = 'QUEUED'
                ORDER BY created_at, id
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                connection.execute("COMMIT")
                return None
            updated = connection.execute(
                """
                UPDATE task_runs
                SET status = 'RUNNING', attempts = attempts + 1,
                    started_at = COALESCE(started_at, ?), lease_owner = ?, lease_expires_at = ?, error = NULL
                WHERE id = ? AND status = 'QUEUED'
                """,
                (now, worker_id, now + lease_seconds, row["id"]),
            ).rowcount
            connection.execute("COMMIT")
            if updated != 1:
                return None
        return QueuedTask(
            id=str(row["id"]),
            job_id=str(row["job_id"]),
            task_type=str(row["task_type"]),
            phase=str(row["phase"]) if row["phase"] is not None else None,
            payload=json.loads(str(row["payload_json"] or "{}")),
            attempts=int(row["attempts"]) + 1,
        )

    def heartbeat(self, run_id: str, worker_id: str, *, lease_seconds: int = 120) -> bool:
        with closing(self._connect()) as connection:
            updated = connection.execute(
                """
                UPDATE task_runs SET lease_expires_at = ?
                WHERE id = ? AND status = 'RUNNING' AND lease_owner = ?
                """,
                (time.time() + lease_seconds, run_id, worker_id),
            ).rowcount
        return updated == 1

    def complete(self, run_id: str, worker_id: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE task_runs
                SET status = 'COMPLETED', finished_at = ?, lease_owner = NULL, lease_expires_at = NULL
                WHERE id = ? AND status = 'RUNNING' AND lease_owner = ?
                """,
                (time.time(), run_id, worker_id),
            )

    def fail(self, run_id: str, worker_id: str, error: str) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE task_runs
                SET status = 'FAILED', finished_at = ?, error = ?, lease_owner = NULL, lease_expires_at = NULL
                WHERE id = ? AND status = 'RUNNING' AND lease_owner = ?
                """,
                (time.time(), error, run_id, worker_id),
            )

    def recover_expired(
        self,
        *,
        max_attempts: int = 3,
        preparing_timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        now = time.time()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            abandoned_preparing = connection.execute(
                """
                SELECT id, job_id FROM task_runs
                WHERE status = 'PREPARING' AND created_at < ?
                """,
                (now - max(0, preparing_timeout_seconds),),
            ).fetchall()
            for row in abandoned_preparing:
                connection.execute(
                    """
                    UPDATE task_runs SET status = 'FAILED', finished_at = ?,
                        error = 'task preparation was interrupted before activation'
                    WHERE id = ? AND status = 'PREPARING'
                    """,
                    (now, row["id"]),
                )
            expired = connection.execute(
                "SELECT id, job_id, attempts FROM task_runs WHERE status = 'RUNNING' AND lease_expires_at < ?",
                (now,),
            ).fetchall()
            requeued = []
            failed_job_ids = []
            for row in expired:
                if int(row["attempts"]) >= max_attempts:
                    connection.execute(
                        """
                        UPDATE task_runs SET status = 'FAILED', finished_at = ?,
                            error = 'worker lease expired too many times', lease_owner = NULL, lease_expires_at = NULL
                        WHERE id = ?
                        """,
                        (now, row["id"]),
                    )
                    failed_job_ids.append(str(row["job_id"]))
                else:
                    connection.execute(
                        """
                        UPDATE task_runs SET status = 'QUEUED', lease_owner = NULL, lease_expires_at = NULL,
                            error = 'worker lease expired; task requeued'
                        WHERE id = ?
                        """,
                        (row["id"],),
                    )
                    requeued.append(str(row["id"]))
            connection.execute("COMMIT")
        return {
            "requeued": requeued,
            "failed_job_ids": failed_job_ids,
            "abandoned_preparing_run_ids": [str(row["id"]) for row in abandoned_preparing],
            "abandoned_preparing_job_ids": [str(row["job_id"]) for row in abandoned_preparing],
        }

    def has_active(self, job_id: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM task_runs WHERE job_id = ? AND status IN ('PREPARING', 'QUEUED', 'RUNNING') LIMIT 1",
                (job_id,),
            ).fetchone()
        return row is not None

    def active_job_ids(self) -> set[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT job_id FROM task_runs WHERE status IN ('PREPARING', 'QUEUED', 'RUNNING')"
            ).fetchall()
        return {str(row["job_id"]) for row in rows}

    def active_run_ids(self) -> set[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT id FROM task_runs WHERE status IN ('PREPARING', 'QUEUED', 'RUNNING')"
            ).fetchall()
        return {str(row["id"]) for row in rows}

    def get(self, run_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM task_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def list_for_job(self, job_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM task_runs WHERE job_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (job_id, max(1, min(limit, 200))),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(str(item.pop("payload_json") or "{}"))
            results.append(item)
        return results


class DurableTaskWorker:
    def __init__(
        self,
        queue: DurableTaskQueue,
        handler: Callable[[QueuedTask], None],
        *,
        lease_seconds: int = 120,
        heartbeat_seconds: int = 30,
        recovery_failure_handler: Callable[[str], None] | None = None,
        terminal_handler: Callable[[QueuedTask, str, str | None], None] | None = None,
    ) -> None:
        self.queue = queue
        self.handler = handler
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.recovery_failure_handler = recovery_failure_handler
        self.terminal_handler = terminal_handler
        self.worker_id = f"worker-{uuid.uuid4().hex}"
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=self.worker_id, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def notify(self) -> None:
        self._wake.set()

    def _run(self) -> None:
        last_recovery = 0.0
        while not self._stop.is_set():
            if time.time() - last_recovery >= self.heartbeat_seconds:
                recovery = self.queue.recover_expired()
                if self.recovery_failure_handler:
                    for job_id in [*recovery["failed_job_ids"], *recovery["abandoned_preparing_job_ids"]]:
                        self.recovery_failure_handler(job_id)
                last_recovery = time.time()
            task = self.queue.claim_next(self.worker_id, lease_seconds=self.lease_seconds)
            if task is None:
                self._wake.wait(timeout=1)
                self._wake.clear()
                continue
            heartbeat_stop = threading.Event()
            heartbeat = threading.Thread(
                target=self._heartbeat_loop,
                args=(task.id, heartbeat_stop),
                name=f"heartbeat-{task.id[:8]}",
                daemon=True,
            )
            heartbeat.start()
            try:
                self.handler(task)
            except Exception as exc:
                terminal_status = "FAILED"
                terminal_error = str(exc)
                self.queue.fail(task.id, self.worker_id, terminal_error)
            else:
                terminal_status = "COMPLETED"
                terminal_error = None
                self.queue.complete(task.id, self.worker_id)
            finally:
                heartbeat_stop.set()
                heartbeat.join(timeout=2)
            if self.terminal_handler:
                try:
                    self.terminal_handler(task, terminal_status, terminal_error)
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Task terminal handler failed: run_id=%s job_id=%s status=%s",
                        task.id,
                        task.job_id,
                        terminal_status,
                    )

    def _heartbeat_loop(self, run_id: str, stop: threading.Event) -> None:
        while not stop.wait(self.heartbeat_seconds):
            if not self.queue.heartbeat(run_id, self.worker_id, lease_seconds=self.lease_seconds):
                return
