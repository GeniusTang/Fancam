import asyncio
from typing import Dict, List, Optional
from models.job import Job, JobStatus
from models.person import Person


class JobStore:
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._persons: Dict[str, List[Person]] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    def create(self, job: Job) -> Job:
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> Optional[Job]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        updated = job.model_copy(update=kwargs)
        self._jobs[job_id] = updated
        asyncio.create_task(self._notify(job_id, updated))
        return updated

    def set_persons(self, job_id: str, persons: List[Person]):
        self._persons[job_id] = persons

    def get_persons(self, job_id: str) -> List[Person]:
        return self._persons.get(job_id, [])

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue):
        subs = self._subscribers.get(job_id, [])
        if q in subs:
            subs.remove(q)

    async def _notify(self, job_id: str, job: Job):
        for q in list(self._subscribers.get(job_id, [])):
            try:
                q.put_nowait(job)
            except asyncio.QueueFull:
                pass


job_store = JobStore()
