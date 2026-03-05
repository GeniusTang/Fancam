import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from core.job_store import job_store
from models.job import Job, JobStatus

router = APIRouter()


@router.get("/sse/{job_id}")
async def sse_stream(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")

    return StreamingResponse(
        _event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def _event_generator(job_id: str) -> AsyncGenerator[str, None]:
    q = job_store.subscribe(job_id)
    try:
        # Send current state immediately
        job = job_store.get(job_id)
        if job:
            yield _format(job)

        # Stream updates
        while True:
            try:
                job: Job = await asyncio.wait_for(q.get(), timeout=30.0)
                yield _format(job)
                if job.status in (JobStatus.COMPLETE, JobStatus.ERROR, JobStatus.READY_FOR_SELECTION):
                    # Keep connection open but stop blocking so client can reconnect
                    if job.status == JobStatus.COMPLETE or job.status == JobStatus.ERROR:
                        break
            except asyncio.TimeoutError:
                yield "event: ping\ndata: {}\n\n"
    finally:
        job_store.unsubscribe(job_id, q)


def _format(job: Job) -> str:
    data = {
        "status": job.status,
        "stage": job.stage,
        "progress": round(job.progress, 3),
    }
    if job.error:
        data["error"] = job.error
    if job.eta is not None:
        data["eta"] = job.eta
    return f"data: {json.dumps(data)}\n\n"
