"""Dedicated PostgreSQL-backed background worker for Phase 4 simulation jobs."""

from __future__ import annotations

import logging
import os
import signal
import socket
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal
from app.integrations.spice.kernel_manager import SpiceCoverageError, SpiceKernelError
from app.models.operations import BackgroundJob
from app.repositories import simulation_repo
from app.services.simulation_service import (
    SimulationCancelledError,
    execute_simulation_run,
)

logger = logging.getLogger("clps.worker")


def default_worker_id() -> str:
    """Construct a unique identifier for this worker process."""
    return f"sim-worker-{socket.gethostname()}-{os.getpid()}"


def process_claimed_job(
    job_id: uuid.UUID,
    simulation_id: uuid.UUID,
    *,
    worker_id: str,
    lease_seconds: int,
) -> str:
    """Execute one claimed simulation job in an isolated DB session."""
    with SessionLocal() as db:
        try:
            outcome = execute_simulation_run(
                db,
                simulation_id=simulation_id,
                job_id=job_id,
                lease_seconds=lease_seconds,
            )
            logger.info(
                "Worker %s finished simulation=%s job=%s outcome=%s",
                worker_id,
                simulation_id,
                job_id,
                outcome,
            )
            return outcome
        except SimulationCancelledError:
            logger.info("Simulation=%s cancelled cleanly on worker %s", simulation_id, worker_id)
            simulation_repo.cancel_simulation_run(db, simulation_id)
            return "cancelled"
        except SpiceCoverageError as exc:
            logger.warning("SPICE coverage failure for simulation=%s: %s", simulation_id, exc)
            simulation_repo.mark_simulation_failed(
                db,
                simulation_id=simulation_id,
                job_id=job_id,
                quality_state="kernel_coverage_error",
                error_summary=str(exc),
                retryable=False,
            )
            return "failed"
        except SpiceKernelError as exc:
            logger.error("SPICE kernel failure for simulation=%s: %s", simulation_id, exc)
            simulation_repo.mark_simulation_failed(
                db,
                simulation_id=simulation_id,
                job_id=job_id,
                quality_state="kernel_coverage_error",
                error_summary="Required SPICE kernels are missing or failed integrity checks.",
                retryable=True,
            )
            return "failed"
        except Exception:
            logger.exception("Unhandled simulation worker failure for %s", simulation_id)
            simulation_repo.mark_simulation_failed(
                db,
                simulation_id=simulation_id,
                job_id=job_id,
                quality_state="failed",
                error_summary="Simulation processing failed due to an internal computation error.",
                retryable=True,
            )
            return "failed"


def _mark_job_failed(job_id: uuid.UUID, summary: str) -> None:
    """Persist FAILED status for a claimed job whose payload cannot be executed."""
    with SessionLocal() as err_db:
        db_job = err_db.get(BackgroundJob, job_id)
        if db_job is not None:
            db_job.status = "FAILED"
            db_job.error_summary = summary
            err_db.commit()


def run_once(
    db: Session | None = None,
    *,
    worker_id: str | None = None,
    lease_seconds: int | None = None,
) -> tuple[bool, str | None]:
    """Attempt to claim and execute a single queued simulation job.

    Returns ``(processed_any, outcome)``.
    """
    wid = worker_id or default_worker_id()
    lease = lease_seconds or settings.SIM_WORKER_LEASE_SECONDS

    if db is not None:
        job = simulation_repo.claim_next_simulation_job(db, wid, lease_seconds=lease)
    else:
        with SessionLocal() as own_db:
            job = simulation_repo.claim_next_simulation_job(own_db, wid, lease_seconds=lease)

    if job is None:
        return False, None

    sim_id_raw = job.payload.get("simulation_id") if isinstance(job.payload, dict) else None
    if not sim_id_raw:
        _mark_job_failed(job.job_id, "Job payload missing simulation_id")
        return True, "failed"

    outcome = process_claimed_job(
        job.job_id,
        uuid.UUID(str(sim_id_raw)),
        worker_id=wid,
        lease_seconds=lease,
    )
    return True, outcome


def drain_queue(
    *,
    worker_id: str | None = None,
    max_jobs: int = 20,
) -> list[str]:
    """Synchronously claim and process queued simulation jobs up to ``max_jobs``."""
    wid = worker_id or default_worker_id()
    outcomes: list[str] = []
    for _ in range(max_jobs):
        processed, outcome = run_once(worker_id=wid)
        if not processed:
            break
        if outcome is not None:
            outcomes.append(outcome)
    return outcomes


class SimulationWorkerLoop:
    """Long-running PostgreSQL SKIP LOCKED polling loop with bounded thread concurrency."""

    def __init__(
        self,
        *,
        worker_id: str | None = None,
        max_concurrent: int | None = None,
        poll_interval_seconds: float | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        self.worker_id = worker_id or default_worker_id()
        self.max_concurrent = max_concurrent or settings.SIM_WORKER_MAX_CONCURRENT
        self.poll_interval_seconds = (
            poll_interval_seconds or settings.SIM_WORKER_POLL_INTERVAL_SECONDS
        )
        self.lease_seconds = lease_seconds or settings.SIM_WORKER_LEASE_SECONDS
        self._stop_requested = False

    def stop(self) -> None:
        """Signal loop to terminate cleanly after active jobs finish."""
        self._stop_requested = True

    def run_forever(self) -> None:
        """Poll background_jobs until stopped via SIGINT/SIGTERM."""
        logger.info(
            "Starting simulation worker id=%s max_concurrent=%d poll=%.2fs",
            self.worker_id,
            self.max_concurrent,
            self.poll_interval_seconds,
        )
        active: list[Future[str]] = []
        with ThreadPoolExecutor(max_workers=self.max_concurrent) as pool:
            while not self._stop_requested:
                # Reap completed futures
                active = [f for f in active if not f.done()]

                slots = self.max_concurrent - len(active)
                claimed_any = False
                for _ in range(slots):
                    with SessionLocal() as db:
                        job = simulation_repo.claim_next_simulation_job(
                            db, self.worker_id, lease_seconds=self.lease_seconds
                        )
                    if job is None:
                        break
                    sim_id_raw = (
                        job.payload.get("simulation_id") if isinstance(job.payload, dict) else None
                    )
                    if not sim_id_raw:
                        _mark_job_failed(job.job_id, "Job payload missing simulation_id")
                        claimed_any = True
                        continue
                    claimed_any = True
                    fut = pool.submit(
                        process_claimed_job,
                        job.job_id,
                        uuid.UUID(str(sim_id_raw)),
                        worker_id=f"{self.worker_id}-t{len(active) + 1}",
                        lease_seconds=self.lease_seconds,
                    )
                    active.append(fut)

                if not claimed_any:
                    time.sleep(self.poll_interval_seconds)

        logger.info("Worker %s shutdown complete.", self.worker_id)


def main() -> None:
    """CLI entrypoint for dedicated simulation worker process."""
    setup_logging(debug=settings.DEBUG)
    loop = SimulationWorkerLoop()

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Received signal %s; stopping worker loop cleanly...", signum)
        loop.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    loop.run_forever()


if __name__ == "__main__":
    main()
