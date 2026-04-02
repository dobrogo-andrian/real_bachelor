from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import threading
import uuid


class InMemoryJobQueue:
    def __init__(self, max_workers=2):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="comment-lab-job",
        )
        self._jobs = {}
        self._lock = threading.Lock()

    def submit(self, func, *args, **kwargs):
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "created_at": self._utcnow(),
                "started_at": None,
                "finished_at": None,
                "result": None,
                "error": None,
            }
        self._executor.submit(self._run_job, job_id, func, args, kwargs)
        return job_id

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _run_job(self, job_id, func, args, kwargs):
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "running"
            job["started_at"] = self._utcnow()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job["status"] = "failed"
                job["finished_at"] = self._utcnow()
                job["error"] = str(exc)
            return

        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "completed"
            job["finished_at"] = self._utcnow()
            job["result"] = result

    @staticmethod
    def _utcnow():
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


job_queue = InMemoryJobQueue()
